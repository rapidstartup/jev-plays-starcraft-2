"""Jev decisions via OpenRouter Decisions SDK, TypeSafe System One, or OpenJev (Codiv/local)."""
import os
import json
import asyncio
import time
from urllib.parse import urlparse
from openrouter import OpenRouter
from openrouter.errors import BadRequestResponseError
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeBadRequestError


class CallBudgetReached(Exception):
    pass


_OPENROUTER_MODELS = {'typesafe/jev-1.13', '~typesafe/jev-latest'}
_TYPESAFE_MODELS = {'jev-1.13.0', 'jev-latest', 'jev-preview'}
_TYPESAFE_MODEL_MAP = {
    'typesafe/jev-1.13': 'jev-1.13.0',
    '~typesafe/jev-latest': 'jev-1.13.0',
}
_OPENJEV_MODELS = {'openjev-latest', 'openjev-0.1'}
_OPENJEV_MODEL_MAP = {
    'openjev': 'openjev-latest',
    'openjev-latest': 'openjev-latest',
    'openjev-0.1': 'openjev-0.1',
}
DEFAULT_OPENJEV_BASE_URL = 'https://api.codiv.ai'
_LOCAL_OPENJEV_HOSTS = frozenset({
    'localhost', '127.0.0.1', '::1', '192.168.0.10',
})


# ---- Compact SystemOne-style state projection --------------------------------
# The full game view is ~7-11k chars (units, explored_map, weapon catalogs,
# recent history). Small-context encoders (jeff/GLiFormer, a DeBERTa with a
# ~512-token window) degrade super-linearly on that and time out, while the
# hosted jev tolerates it. To keep the bench FAIR, every backend receives the
# SAME compact projection built here (single chokepoint in Jev.ask), sized to fit
# the smallest model so no backend is starved or overloaded.

# Fields always dropped (terrain/catalog/history bloat; low per-decision value).
_STATE_DROP = frozenset({
    'explored_map', 'unit_type_facts', 'potential_projects', 'previous_investment_intent',
    'observed_capabilities_by_type', 'units_full', 'memory', 'recent_outcomes_full',
})
# Raw entity lists are aggregated into alliance+type counts.
_ENTITY_LIST_KEYS = ('visible_entities', 'last_known_entities', 'entities')
_ENTITY_AGG_KEYS = {
    'visible_entities': 'visible_entities_by_alliance_and_type',
    'last_known_entities': 'stale_entities_by_alliance_and_type',
    'entities': 'entities_by_alliance_and_type',
}


def _agg_entities(entities):
    from collections import Counter
    counts = Counter(f"{e.get('alliance','?')} {e.get('type','?')}" for e in (entities or []))
    return dict(counts)


def _round_pos(value):
    if isinstance(value, list):
        return [round(v, 1) if isinstance(v, float) else v for v in value]
    return value


def _trim_units(units, limit=24):
    out = []
    for u in (units or [])[:limit]:
        out.append({k: _round_pos(u.get(k)) for k in ('tag', 'type', 'position', 'health_fraction') if k in u})
    return out


def _tail(items, n):
    if not isinstance(items, list):
        return items
    return items[-n:]


def _trim_guide(guide):
    if not isinstance(guide, dict):
        return guide
    out = {}
    for k in ('strategy', 'focus', 'notes'):
        v = guide.get(k)
        if isinstance(v, str):
            out[k] = v[:220]
        elif v is not None:
            out[k] = v
    return out


def _trim_facts(facts, budget_per=180):
    """Keep selection/type facts small: counts + short scalars, drop verbosity."""
    if not isinstance(facts, dict):
        return facts
    out = {}
    for name, f in facts.items():
        if not isinstance(f, dict):
            out[name] = f
            continue
        keep = {}
        for k, v in f.items():
            if isinstance(v, (int, float, bool)) or v is None:
                keep[k] = v
            elif isinstance(v, str):
                keep[k] = v[:80]
            elif isinstance(v, dict):
                keep[k] = dict(list(v.items())[:8])
            elif isinstance(v, list):
                keep[k] = v[:6]
        out[name] = keep
    return out


def compact_model_state(state, budget_chars=None):
    """Project a full game view into a compact, decision-relevant SystemOne state.

    Priority (kept longest): objective/resources/strategy/selection_facts/aggregated
    entities are always retained (they are small and decision-critical); guide and
    recent history are trimmed to the most recent; verbose per-unit and catalog
    fields are dropped. Enforces a total char budget so no backend is overloaded.
    """
    if not isinstance(state, dict):
        return state
    if (os.getenv('JEV_COMPACT_STATE') or '1').strip().lower() in ('0', 'false', 'no'):
        return state
    if budget_chars is None:
        budget_chars = int(os.getenv('JEV_STATE_BUDGET_CHARS', '2600'))
    out = {}
    # Always-keep scalar/small context.
    for k in ('objective', 'resources', 'strategy_chosen_by_jev', 'previous_strategy'):
        if k in state:
            out[k] = state[k]
    # Decision-critical per-cohort / per-type facts (question keys preserved upstream).
    for k in ('selection_facts', 'type_selection_facts'):
        if k in state:
            out[k] = _trim_facts(state[k])
    # Aggregate raw entity lists.
    for src, dst in _ENTITY_AGG_KEYS.items():
        if src in state and isinstance(state[src], list):
            out[dst] = _agg_entities(state[src])
    # Trimmed guidance and recent history (most relevant last).
    if 'guide_oversight' in state:
        out['guide_oversight'] = _trim_guide(state['guide_oversight'])
    for k in ('recent_outcomes', 'recent_action_feedback'):
        if k in state:
            out[k] = _tail(state[k], 2)
    # Trimmed per-unit essentials (position/health for orders), capped.
    if 'units' in state:
        out['units'] = _trim_units(state['units'])
    # completed_upgrades is small but low value per-decision; keep only names.
    if 'completed_upgrades' in state:
        ups = state['completed_upgrades']
        if isinstance(ups, list):
            out['completed_upgrades'] = [u.get('name') if isinstance(u, dict) else u for u in ups][:12]

    # Enforce budget by dropping the least-critical remaining keys (largest first)
    # until it fits. Never drop objective/resources/selection_facts/aggregates.
    protected = {'objective', 'resources', 'selection_facts', 'type_selection_facts',
                 'strategy_chosen_by_jev', 'visible_entities_by_alliance_and_type',
                 'stale_entities_by_alliance_and_type', 'entities_by_alliance_and_type',
                 'guide_oversight'}
    def size():
        return len(json.dumps({'state': out, 'questions': {}}))
    guard = 0
    while size() > budget_chars and guard < 40:
        guard += 1
        droppable = [k for k in out if k not in protected]
        if not droppable:
            break
        # Drop the largest droppable key first.
        victim = max(droppable, key=lambda k: len(json.dumps(out[k])))
        out.pop(victim, None)
    return out


def compact_questions(questions, max_desc_chars=None, max_instructions_chars=320):
    """Shorten SystemOne questions without removing any selectable option.

    Each criterion is a verbose natural-language blurb (repeated boilerplate +
    the concrete action). We keep every criterion KEY (so the action space is
    unchanged) and truncate only the description text, which always names the
    action first. Instructions are trimmed too. This keeps state+questions small
    enough for small-context encoders (jeff) without changing what can be chosen.
    """
    if not isinstance(questions, dict):
        return questions
    if (os.getenv('JEV_COMPACT_STATE') or '1').strip().lower() in ('0', 'false', 'no'):
        return questions
    if max_desc_chars is None:
        max_desc_chars = int(os.getenv('JEV_DESC_CHARS', '110'))
    out = {}
    for name, q in questions.items():
        if not isinstance(q, dict):
            out[name] = q
            continue
        nq = dict(q)
        ins = nq.get('instructions')
        if isinstance(ins, str) and len(ins) > max_instructions_chars:
            nq['instructions'] = ins[:max_instructions_chars].rstrip() + '…'
        crit = nq.get('criteria')
        if isinstance(crit, dict):
            nq['criteria'] = {k: (v[:max_desc_chars].rstrip() + '…' if isinstance(v, str) and len(v) > max_desc_chars else v)
                              for k, v in crit.items()}
        out[name] = nq
    return out


def _resolve_typesafe_model(name):
    mapped = _TYPESAFE_MODEL_MAP.get(name, name)
    if mapped not in _TYPESAFE_MODELS:
        raise ValueError(
            f'This experiment permits Jev only; got {name!r} '
            f'(typesafe models: {sorted(_TYPESAFE_MODELS)})'
        )
    return mapped


def _resolve_openjev_model(name):
    """Map openjev* names; otherwise default to openjev-latest for this via.

    JEV_SYSTEMONE_MODEL overrides verbatim — use it for OpenJev-wire servers that
    publish a different model id (e.g. LocalJev serves 'localjev-latest').
    """
    override = (os.environ.get('JEV_SYSTEMONE_MODEL') or '').strip()
    if override:
        return override
    if not name or not str(name).strip():
        return 'openjev-latest'
    raw = str(name).strip()
    if raw in _OPENJEV_MODEL_MAP:
        return _OPENJEV_MODEL_MAP[raw]
    if raw.startswith('openjev'):
        if raw in _OPENJEV_MODELS:
            return raw
        raise ValueError(
            f'Unknown OpenJev model {raw!r} '
            f'(openjev models: {sorted(_OPENJEV_MODELS)} or aliases openjev)'
        )
    return 'openjev-latest'


def resolve_openjev_base_url():
    """Codiv hosted by default; OPENJEV_BASE_URL / TYPESAFE_BASE_URL override (local later)."""
    for env in ('OPENJEV_BASE_URL', 'TYPESAFE_BASE_URL'):
        value = (os.environ.get(env) or '').strip()
        if value:
            return value.rstrip('/')
    return DEFAULT_OPENJEV_BASE_URL


def openjev_host_only(base_url=None):
    """Hostname (and port if non-default) for control.json — never a key."""
    url = base_url if base_url is not None else resolve_openjev_base_url()
    parsed = urlparse(url if '://' in url else f'https://{url}')
    host = parsed.hostname or url
    if parsed.port:
        return f'{host}:{parsed.port}'
    return host


def openjev_via_label(base_url=None):
    host = (openjev_host_only(base_url) or '').lower()
    # Strip port for local-host check
    host_name = host.split(':')[0]
    if host_name in _LOCAL_OPENJEV_HOSTS or host_name.startswith('192.168.'):
        return 'openjev_local'
    return 'openjev_codiv'


def _normalize_via(raw):
    via = (raw or 'openrouter').strip().lower()
    if via in ('', 'openrouter'):
        return 'openrouter'
    if via == 'typesafe':
        return 'typesafe'
    if via in ('openjev', 'codiv'):
        return 'openjev'
    raise ValueError(
        f'JEV_VIA must be openrouter, typesafe, openjev, or codiv; got {via!r}'
    )


def _openjev_api_key():
    return (
        (os.environ.get('CODIV_API_KEY') or '').strip()
        or (os.environ.get('OPENJEV_API_KEY') or '').strip()
        or (os.environ.get('TYPESAFE_API_KEY') or '').strip()
        or None
    )


class Jev:
    def __init__(self, log, session, max_calls=None):
        via = _normalize_via(os.environ.get('JEV_VIA'))
        self.via = via
        self.timeout_ms = int(os.getenv('JEV_TIMEOUT_MS', '5000'))
        self.log, self.session = log, session
        self.calls = 0
        self.inflight = 0
        # dgemma-small / single-sequence SystemOne: never parallel POSTs
        self._systemone_lock = asyncio.Lock()
        # 0 / None / negative => unlimited (no CallBudgetReached)
        self.max_calls = max_calls if max_calls is not None and max_calls > 0 else None
        self.cost = 0.0
        raw_model = os.getenv('JEV_MODEL', 'typesafe/jev-1.13')
        self.base_url = None

        if via == 'typesafe':
            key = os.environ.get('JEV_API_KEY') or os.environ.get('TYPESAFE_API_KEY')
            if not key:
                raise RuntimeError('Set JEV_API_KEY or TYPESAFE_API_KEY for JEV_VIA=typesafe')
            self.api_key = key
            self.model = _resolve_typesafe_model(raw_model)
            self.via_label = 'typesafe_systemone'
            self.client = None  # created per ask with async with
        elif via == 'openjev':
            key = _openjev_api_key()
            if not key:
                raise RuntimeError(
                    'Set CODIV_API_KEY or OPENJEV_API_KEY or TYPESAFE_API_KEY for JEV_VIA=openjev'
                )
            self.api_key = key
            self.base_url = resolve_openjev_base_url()
            self.model = _resolve_openjev_model(raw_model)
            self.via_label = openjev_via_label(self.base_url)
            self.client = None
        else:
            key = os.environ.get('OPENROUTER_API_KEY')
            if not key:
                raise RuntimeError('Set OPENROUTER_API_KEY in .env')
            if raw_model not in _OPENROUTER_MODELS:
                raise ValueError('This experiment permits Jev only')
            self.model = raw_model
            self.api_key = None
            self.via_label = 'openrouter_decisions'
            self.client = OpenRouter(
                api_key=key, x_open_router_title='Jev StarCraft Lab'
            )

        init_fields = {
            'model': self.model,
            'timeout_ms': self.timeout_ms,
            'via': self.via_label,
        }
        if self.base_url:
            init_fields['base_url_host'] = openjev_host_only(self.base_url)
        self.log('jev_init', **init_fields)

    async def ask(self, state, questions):
        # Concrete-order question names exactly identify job summaries. Reapply
        # projection after every recursive split, retaining all other world facts.
        facts = state.get('selection_facts', {})
        if questions and set(questions) <= set(facts) and set(facts) != set(questions):
            state = {**state, 'selection_facts': {key: facts[key] for key in questions}}
        # Compact SystemOne projection for every backend (fair bench + fits small
        # encoders like jeff/GLiFormer). Applied here, the single shared chokepoint.
        state = compact_model_state(state)
        # Shorten question boilerplate (all option keys kept) and enforce a combined
        # state+questions budget so the TOTAL context fits a small encoder.
        total_budget = int(os.getenv('JEV_CONTEXT_BUDGET_CHARS', '3000'))
        desc = int(os.getenv('JEV_DESC_CHARS', '110'))
        questions = compact_questions(questions, max_desc_chars=desc)
        def _ctx():
            return len(json.dumps([state, questions]))
        # Shrink local desc / state copy until the combined context fits.
        guard = 0
        while _ctx() > total_budget and guard < 30:
            guard += 1
            if desc > 45:
                desc = int(desc * 0.75)
                questions = compact_questions(questions, max_desc_chars=desc)
            else:
                state = compact_model_state(state, budget_chars=max(700, len(json.dumps(state)) // 2))
        # Conservative transport-size heuristic, not a token-count guarantee.
        # Preserve every question/criterion and the identical fair state.
        if len(questions) > 1 and len(json.dumps([state, questions])) > 80000:
            items = list(questions.items())
            middle = len(items) // 2
            self.log(
                'jev_request_split',
                questions=len(items),
                request_chars=len(json.dumps([state, questions])),
            )
            # Sequential halves: SystemOne backends like dgemma-small must not
            # receive concurrent asks (single-sequence decoder).
            left = await self.ask(state, dict(items[:middle]))
            right = await self.ask(state, dict(items[middle:]))
            return {**left, **right}
        if self.max_calls is not None and self.max_calls > 0 and self.calls + self.inflight >= self.max_calls:
            raise CallBudgetReached()
        self.inflight += 1
        try:
            started = time.monotonic()
            if self.via in ('typesafe', 'openjev'):
                result = await self._ask_systemone(state, questions)
            else:
                result = await self._ask_openrouter(state, questions)
            self.log(
                'jev',
                latency_ms=round((time.monotonic() - started) * 1000),
                timeout_ms=self.timeout_ms,
                via=self.via_label,
                state=state,
                questions=questions,
                response=result,
            )
            return result['answers']
        except (BadRequestResponseError, TypeSafeBadRequestError) as exc:
            self.log(
                'jev_request_rejected',
                request_chars=len(json.dumps([state, questions])),
                state_chars=len(json.dumps(state)),
                question_count=len(questions),
                question_chars={k: len(json.dumps(v)) for k, v in questions.items()},
                detail=str(exc)[:200],
            )
            if 'max_tokens_exceeded' not in str(exc) or len(questions) <= 1:
                raise
            # The server is authoritative about token limits. Splitting a rejected
            # batch retains the exact state, choices and criteria for each question.
            # Release this reservation before children reserve their own requests.
            # Serial halves: SystemOne backends (dgemma-small) are single-sequence;
            # concurrent asks cross replies even on the token-limit path.
            self.inflight -= 1
            try:
                items = list(questions.items())
                middle = len(items) // 2
                self.log(
                    'jev_request_split',
                    questions=len(items),
                    reason='server_token_limit',
                )
                left = await self.ask(state, dict(items[:middle]))
                right = await self.ask(state, dict(items[middle:]))
                return {**left, **right}
            finally:
                self.inflight += 1
        finally:
            self.inflight -= 1

    async def _ask_openrouter(self, state, questions):
        response = await self.client.alpha.decisions.create_async(
            model=self.model,
            state=state,
            questions=questions,
            session_id=self.session,
            timeout_ms=self.timeout_ms,
            retries=None,
            # SDK 1.1.158 otherwise appends /api/alpha to /api/v1 (404).
            server_url='https://openrouter.ai',
        )
        self.calls += 1
        self.cost += response.usage.cost or 0
        return response.model_dump(mode='json')

    async def _ask_systemone(self, state, questions):
        """TypeSafe System One path - also used for OpenJev (Codiv or local)."""
        # Single-flight: dgemma-small visual decoder is single-sequence/stateful;
        # concurrent POSTs cross replies (proven with nonce->other client's answer).
        async with self._systemone_lock:
            kwargs = {
                'api_key': self.api_key,
                'timeout': self.timeout_ms / 1000.0,
                'retry': RetryPolicy(max_retries=0),
            }
            if self.base_url:
                # Explicit ctor base_url (TYPESAFE_BASE_URL env also works per SDK).
                kwargs['base_url'] = self.base_url
            async with AsyncTypeSafeClient(**kwargs) as client:
                result = await client.system_one(
                    state=state, questions=questions, model=self.model
                )
            self.calls += 1
            dumped = result.model_dump()
            usage = dumped.get('usage') if isinstance(dumped, dict) else None
            if isinstance(usage, dict) and usage.get('cost') is not None:
                self.cost += usage['cost']
            # else: no cost field - leave cost unchanged (increment 0); don't crash
            return dumped
