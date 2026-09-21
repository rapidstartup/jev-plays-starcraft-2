"""Read a fresh, build-specific campaign ending marker; never use API objective results."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


class OutcomeMonitor:
    def __init__(self, path, started_at, allow_credit=False):
        self.path = Path(path)
        self.started_at = started_at
        self.saw_active = False
        self.allow_credit = allow_credit

    @classmethod
    def for_map(cls, map_path, started_at, bank_directory=None):
        if not map_path:
            return None
        map_path = Path(map_path)
        manifest = map_path.with_suffix('.bridge.json')
        if not manifest.exists():
            return None
        metadata = json.loads(manifest.read_text())
        name = metadata.get('outcome_bank')
        if not name:
            return None
        if not re.fullmatch(r'JevOutcome[a-f0-9]{32}', name):
            raise ValueError('Invalid campaign outcome bank name')
        if hashlib.sha256(map_path.read_bytes()).hexdigest() != metadata['output_sha256']:
            raise ValueError('Campaign map does not match its outcome instrumentation manifest')
        directory = bank_directory or Path.home()/'Library/Application Support/Blizzard/StarCraft II/Banks'
        return cls(Path(directory)/(name+'.SC2Bank'), started_at,
                   allow_credit=metadata.get('campaign_credit') is True)

    def poll(self):
        try:
            if self.path.stat().st_mtime < self.started_at:
                return None
            root = ET.fromstring(self.path.read_bytes())
        except (FileNotFoundError, ET.ParseError):
            return None  # BankSave may be between its write and rename.
        value = root.find("./Section[@name='Outcome']/Key[@name='result']/Value")
        result = value.get('string') if value is not None else None
        if result == 'active':
            self.saw_active = True
            return None
        if not self.saw_active or result not in {'victory','defeat'}:
            return None
        stamp = root.find("./Section[@name='Outcome']/Key[@name='engine_time']/Value")
        return {'status':result, 'source':'campaign ending instrumentation',
                'credit_enabled':self.allow_credit,
                'bank':str(self.path), 'engine_time':stamp.get('int') if stamp is not None else None}


# Liberation Day and similar WoL maps synthesize unanimous Victory when the
# objective building dies. Track last-seen health so we can credit a real win
# without treating every all-Victory as false_api_end.
CRITICAL_OBJECTIVE_HEALTH = 10.0
ALWAYS_TRACK_STRUCTURES = ('LogisticsHeadquarters',)
_NON_STRUCTURE_PHRASES = frozenset({'raynor'})


def objective_structure_names(objective):
    """Names of enemy structures to track from the objective string.

    Always includes LogisticsHeadquarters. Also joins multi-word Title Case
    phrases in the objective (e.g. "Logistics Headquarters" → LogisticsHeadquarters).
    """
    names = set(ALWAYS_TRACK_STRUCTURES)
    if not objective:
        return names
    compact = re.sub(r'[\s_\-]+', '', objective)
    for known in ALWAYS_TRACK_STRUCTURES:
        if known.casefold() in compact.casefold():
            names.add(known)
    for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', objective):
        joined = match.group(1).replace(' ', '')
        if joined.casefold() in _NON_STRUCTURE_PHRASES:
            continue
        names.add(joined)
    for match in re.finditer(r'\b(LogisticsHeadquarters)\b', objective):
        names.add(match.group(1))
    return names


def hero_unit_names(objective):
    """Player-force hero names implied by the objective (Raynor on Liberation Day)."""
    names = set()
    if objective and re.search(r'\bRaynor\b', objective, re.I):
        names.add('Raynor')
    return names


class ObjectiveWinEvidence:
    """Track objective-building health + hero survival for verified API wins."""

    def __init__(self, objective=None, critical_health=CRITICAL_OBJECTIVE_HEALTH):
        self.objective = objective or ''
        self.targets = objective_structure_names(objective)
        self.hero_names = hero_unit_names(objective)
        self.critical_health = float(critical_health)
        self.last_health = {}       # structure name -> last visible health
        self.seen = set()           # structures ever observed (visible)
        self.disappeared = set()    # seen then absent (visible+snapshot)
        self.hero_alive = None      # True / False / None
        self.hero_name_seen = None
        self.last_loop = None

    def update(self, observation, unit_names, unit_catalog=None):
        """Update from a raw ResponseObservation. unit_names: type_id -> name."""
        from s2clientprotocol import raw_pb2 as raw
        from s2clientprotocol import data_pb2 as data_proto

        try:
            units = observation.observation.raw_data.units
            loop = observation.observation.game_loop
        except AttributeError:
            return
        self.last_loop = loop
        present = set()  # target names currently visible or snapshot
        hero_alive = False
        hero_seen = False

        for unit in units:
            name = unit_names.get(unit.unit_type)
            if not name:
                continue
            alliance = unit.alliance
            display = unit.display_type

            if alliance == raw.Self and unit.health > 0:
                is_named_hero = name in self.hero_names or name.startswith('Raynor')
                is_heroic = False
                if unit_catalog and unit.unit_type in unit_catalog:
                    attrs = getattr(unit_catalog[unit.unit_type], 'attributes', ()) or ()
                    is_heroic = data_proto.Heroic in attrs
                if is_named_hero or is_heroic:
                    hero_seen = True
                    hero_alive = True
                    self.hero_name_seen = name

            if name not in self.targets or alliance != raw.Enemy:
                continue
            if display == raw.Visible:
                present.add(name)
                self.seen.add(name)
                self.last_health[name] = float(unit.health)
                self.disappeared.discard(name)
            elif display == raw.Snapshot:
                # Fog memory: still "present", do not refresh health or mark gone.
                present.add(name)

        for name in list(self.seen):
            if name not in present:
                self.disappeared.add(name)

        if hero_seen or self.hero_names:
            # If we expect Raynor and he is missing from Self with health>0, mark dead
            # only after we have previously seen him (avoid cinematic false death).
            if hero_seen:
                self.hero_alive = hero_alive
            elif self.hero_alive is True and not hero_seen:
                # Previously alive hero absent this frame — may be fog/cinematic;
                # keep last True unless we see a dead body (health 0 Self).
                for unit in units:
                    name = unit_names.get(unit.unit_type, '')
                    if unit.alliance == raw.Self and (
                            name in self.hero_names or name.startswith('Raynor')):
                        self.hero_alive = unit.health > 0
                        self.hero_name_seen = name
                        break

    def hq_critically_damaged(self):
        """True if any target was ≤ critical health or vanished after being seen."""
        for name in self.targets:
            if name in self.disappeared:
                return True
            hp = self.last_health.get(name)
            if hp is not None and hp <= self.critical_health:
                return True
        return False

    def is_verified_objective_win(self):
        """All-Victory is a real win when HQ was critically hurt and hero lived."""
        if not self.hq_critically_damaged():
            return False
        if self.hero_alive is False:
            return False
        # Require hero known-alive when objective names one; otherwise allow
        # any Self heroic / previously-alive signal, or no hero constraint.
        if self.hero_names and self.hero_alive is not True:
            return False
        if not self.hero_names and self.hero_alive is False:
            return False
        return True

    def evidence(self):
        return {
            'source': 'objective_building_health',
            'targets': sorted(self.targets),
            'hq_health': {k: self.last_health[k] for k in sorted(self.last_health)},
            'hq_seen': sorted(self.seen),
            'hq_disappeared': sorted(self.disappeared),
            'hero_alive': self.hero_alive,
            'hero_name': self.hero_name_seen,
            'critical_health': self.critical_health,
            'last_loop': self.last_loop,
        }
