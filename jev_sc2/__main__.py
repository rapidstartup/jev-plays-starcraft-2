"""uv run python -m jev_sc2 --map /absolute/path/to/mission.SC2Map"""
from .bookmark import BookmarkRecovery
import argparse
import asyncio
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from openrouter.errors import PaymentRequiredResponseError
from s2clientprotocol import sc2api_pb2 as sc, error_pb2
from .sc2 import SC2, launch, find_executable
from .jev import Jev, CallBudgetReached
from .reload import PlayerLoader
from .view import make_view, validate_commands, validate_commands_with_rejects
from .camera import choose_shot
from .outcome import OutcomeMonitor, ObjectiveWinEvidence
from .controller_log import ControllerLog, unlimited, normalize_budget

ROOT = Path(__file__).resolve().parent.parent
LOOPS_PER_REALTIME_SECOND = 22.4
MINIMUM_DECISION_WAIT = 3.0
MEMORY_MODES = ('none', 'cross_run', 'cross_game')


def default_memory_mode():
    value = (os.getenv('JEV_MEMORY_MODE') or 'none').strip().lower()
    return value if value in MEMORY_MODES else 'none'


def maybe_send_ui_dismiss_key():
    """Windows-only: post Esc to the SC2 client to close Help/Tutorials panels.

    Called only after the game clock has already stalled (no orders progressing),
    rate-limited by the caller to one attempt per stall warning. Sends no clicks
    and no game orders — the equivalent of a human pressing Esc on a help panel.
    Opt out with JEV_UI_DISMISS=0 (a human then closes the panel instead).
    Returns True when the key was posted.
    """
    if os.name != 'nt':
        return False
    if (os.getenv('JEV_UI_DISMISS') or '1').strip().lower() in ('0', 'false', 'no'):
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, 'StarCraft II')
        if not hwnd:
            return False
        WM_KEYDOWN, WM_KEYUP, VK_ESCAPE = 0x0100, 0x0101, 0x1B
        user32.PostMessageW(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
        user32.PostMessageW(hwnd, WM_KEYUP, VK_ESCAPE, 0)
        return True
    except Exception:
        return False


def git_head(root):
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None



def _control_openjev_host(jev_via):
    """Host only for control.json when via is openjev/codiv; else None. Never a key."""
    if jev_via not in ('openjev', 'codiv'):
        return None
    from .jev import openjev_host_only, resolve_openjev_base_url
    return openjev_host_only(resolve_openjev_base_url())


def write_control_json(directory, args, stamp):
    """Record launch knobs for every entry point (single-mission and campaign)."""
    timeout_ms = int(os.getenv('JEV_TIMEOUT_MS', '5000'))
    memory_mode = getattr(args, 'memory_mode', None) or default_memory_mode()
    control = {
        'stamp': stamp,
        'git_head': git_head(ROOT),
        'map': str(args.map) if getattr(args, 'map', None) else None,
        'expected_map': getattr(args, 'expected_map', None),
        'objective': getattr(args, 'objective', None),
        'seconds': getattr(args, 'seconds', None),
        'max_calls': getattr(args, 'max_calls', None),
        'wall_status_seconds': getattr(args, 'wall_status_seconds', 3600),
        'exit_policy': 'win_or_death_only',
        'strict_unit_timeout': bool(getattr(args, 'strict_unit_timeout', False)),
        'retry_stalls': bool(getattr(args, 'retry_stalls', False)),
        'close_sc2': bool(getattr(args, 'close_sc2', False)),
        'follow_camera': bool(getattr(args, 'follow_camera', False)),
        'attach': bool(getattr(args, 'attach', False)),
        'guide_expected': os.getenv('GUIDE_ENABLED', '0') in ('1', 'true', 'True'),
        'guide_model': os.getenv('GUIDE_MODEL'),
        'jev_model': os.getenv('JEV_MODEL', 'typesafe/jev-1.13'),
        'jev_via': (os.getenv('JEV_VIA') or 'openrouter').strip().lower() or 'openrouter',
        'jev_timeout_ms': timeout_ms,
        'memory_mode': memory_mode,
        'memory_enabled': memory_mode != 'none',
        'openrouter_key_present': bool(os.getenv('OPENROUTER_API_KEY')),
        'jev_api_key_present': bool(os.getenv('JEV_API_KEY') or os.getenv('TYPESAFE_API_KEY')),
        'openjev_key_present': bool(
            os.getenv('CODIV_API_KEY')
            or os.getenv('OPENJEV_API_KEY')
            or os.getenv('TYPESAFE_API_KEY')
        ),
        'openjev_base_url': _control_openjev_host(
            (os.getenv('JEV_VIA') or 'openrouter').strip().lower() or 'openrouter'
        ),
        'launched_at': datetime.now(timezone.utc).isoformat(),
    }
    (directory / 'control.json').write_text(json.dumps(control, indent=2) + '\n')
    return control


def decision_wait_and_age_limit(max_age_loops, min_wait=MINIMUM_DECISION_WAIT,
                                loops_per_second=LOOPS_PER_REALTIME_SECOND):
    """Share one realtime budget between waiting for Jev and submitting.

    The outer wait is at least min_wait seconds because multi-stage calls often
    exceed max_age_loops/22.4. Local backends (LocalJev / SemIf-bridge) also need
    the wait to cover JEV_TIMEOUT_MS or every decide dies at the 3s floor.
    """
    env_timeout_s = max(0.0, int(os.getenv('JEV_TIMEOUT_MS', '5000')) / 1000.0)
    wait = max(float(min_wait), env_timeout_s, max_age_loops / loops_per_second)
    return wait, max(int(max_age_loops), int(wait * loops_per_second + 1e-9))


def result_for_player(players, player_id):
    """An ally's win or an ended clock is not proof of our mission result."""
    if len(players)>1 and len({p['result'] for p in players})==1 and players[0]['result'] in {'Victory','Defeat'}:
        return 'incomplete'  # Campaign objective transitions can synthesize these results.
    own = next((p['result'] for p in players if p['player']==player_id),None)
    return {'Victory':'victory','Defeat':'defeat','Tie':'tie'}.get(own,'incomplete')



def uncapped_win_death_only(args):
    """True when budgets are unlimited: exit only on verified win/death."""
    return normalize_budget(getattr(args, 'max_calls', None)) is None and normalize_budget(
        getattr(args, 'seconds', None)) is None


def api_end_is_verified(hint, *, uncapped):
    """Under uncapped win/death, only a clear (non-synthetic) Defeat ends the mission.

    API Victory / Tie / incomplete (all-same synthetic) are unverified without
    OutcomeMonitor credit - campaign maps synthesize unanimous Victory mid-fight.
    """
    if hint == 'defeat':
        return True
    if hint in ('victory', 'tie') and not uncapped:
        return True
    return False


def check_map_identity(info, expected):
    actual = info.local_map_path.replace('\\','/').split('/')[-1]
    if actual.casefold()!=Path(expected).name.casefold():
        raise RuntimeError(f'Resume map mismatch: expected {Path(expected).name}, got {actual!r}')


def action_feedback(actions, results, loop, requested, age, max_age):
    failures = []
    for action, result in zip(actions, results):
        if result != error_pb2.Success:
            cmd = action.action_raw.unit_command
            failures.append({'ability_id':cmd.ability_id,'unit_tags':list(cmd.unit_tags),
                             'result':error_pb2.ActionResult.Name(result)})
    return {'loop':loop,'requested':requested,'submitted':len(actions),
            'accepted':sum(r==error_pb2.Success for r in results),
            'failures':failures,'discarded_as_stale':bool(requested and age>max_age),
            'note':'Accepted means engine accepted the request, not completed the action.'}


async def run(args):
    load_dotenv(ROOT / '.env')
    sc2root = os.getenv('SC2PATH', '/Applications/StarCraft II')
    if args.doctor:
        status = {'key_present':bool(os.getenv('OPENROUTER_API_KEY'))}
        try:
            status['executable'] = str(find_executable(sc2root))
        except FileNotFoundError as exc:
            status['executable'] = None
            status['next_step'] = str(exc)
        print(json.dumps(status,indent=2))
        if not status['key_present'] or not status['executable']:
            raise SystemExit(1)
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory = ROOT / 'runs' / stamp
    directory.mkdir(parents=True)
    control = write_control_json(directory, args, stamp)
    events = (directory/'events.jsonl').open('a',buffering=1)
    controller = ControllerLog(directory)
    outcome = {'status':'incomplete','players':[],'player_id':None,'run':str(directory)}
    def log(event, **fields):
        if event=='result':
            outcome['players'] = fields['players']
            outcome['status'] = result_for_player(fields['players'],outcome['player_id'])
            if outcome['status']=='incomplete':
                outcome['reason']='API result does not verify campaign completion; inspect objective/UI outcome'
        elif event=='campaign_outcome':
            outcome['status'] = fields['status'] if fields.get('credit_enabled') else 'incomplete'
            outcome['verification'] = fields
            if not fields.get('credit_enabled'):
                outcome['reason'] = 'Instrumented mission ending detected; experimental build requires independent UI verification'
        elif event=='verified_objective_win':
            outcome['status'] = 'victory'
            outcome['verification'] = fields
            outcome.pop('false_api_end', None)
            outcome.pop('reason', None)
        elif event=='replay_unavailable':
            outcome['replay_error'] = fields['error']
        elif event=='api_bookmark_restored':
            outcome['api_bookmark_restores'] = outcome.get('api_bookmark_restores',0)+1
        elif event=='stopped':
            outcome['reason'] = fields['reason']
        elif event=='finished':
            outcome.update(calls=fields['calls'],cost=fields['cost'],
                           replay=str(directory/'game.SC2Replay') if (directory/'game.SC2Replay').exists() else None)
            if outcome['status']=='incomplete' and 'reason' not in outcome:
                mc = normalize_budget(args.max_calls)
                sec = normalize_budget(args.seconds)
                if mc is not None and fields['calls'] >= mc:
                    outcome['reason'] = 'call budget reached'
                elif sec is not None:
                    outcome['reason'] = 'time limit reached'
                else:
                    outcome['reason'] = 'run ended without verified win/death'
            (directory/'result.json').write_text(json.dumps(outcome,indent=2)+'\n')
        row = {'time':time.time(), 'event':event, **fields}
        events.write(json.dumps(row)+'\n')
        if event != 'jev':
            print(json.dumps(row),flush=True)
    log = controller.wrap(log)
    loader = PlayerLoader(ROOT)
    loader.refresh()
    memory = {}
    camera_memory = {}
    log('control', **{k: v for k, v in control.items() if k != 'stamp'})
    jev = Jev(log, stamp, max_calls=normalize_budget(args.max_calls))
    proc = None
    if not args.attach:
        if not args.map:
            raise ValueError('--map is required unless --attach is supplied')
        proc = launch(sc2root,args.port,(directory/'sc2.log').open('w'),
                      args.window_size, args.window_position)
    client = await SC2.connect(args.port, process=proc)
    client.log = log
    async def save_replay():
        try:
            replay = await client.request('save_replay',sc.RequestSaveReplay())
            (directory/'game.SC2Replay').write_bytes(replay.data)
        except Exception as exc:
            # QuickLoad can stop replay recording; keep the actual run result.
            log('replay_unavailable',error=str(exc))
    leave_sc2_open = False  # True => NEVER quit/close_sc2 (false/unverified API end)
    try:
        ping = await client.request('ping',sc.RequestPing())
        decision_wait, age_limit = decision_wait_and_age_limit(args.max_age_loops)
        log('connected',version=ping.game_version,revision=loader.revision,
            objective=args.objective,seconds=args.seconds,max_calls=args.max_calls,
            max_age_loops=args.max_age_loops,effective_max_age_loops=age_limit)
        attached_info = None
        outcome_monitor = OutcomeMonitor.for_map(args.map, time.time())
        if args.map:
            log('loading_map',map=Path(args.map).name,opponent=args.opponent)
            joined = await client.start(args.map,args.opponent,getattr(args,'race','terran').capitalize())
            outcome['player_id'] = joined.player_id
            log('joined_game')
        else:
            existing = await client.observe()
            outcome['player_id'] = existing.observation.player_common.player_id or None
            if getattr(args,'expected_map',None):
                attached_info = await client.request('game_info',sc.RequestGameInfo())
                check_map_identity(attached_info,args.expected_map)
            if client.status == sc.ended:
                players=[{'player':r.player_id,'result':sc.Result.Name(r.result)}
                         for r in existing.player_result]
                hint = result_for_player(players, outcome.get('player_id'))
                if not api_end_is_verified(hint, uncapped=uncapped_win_death_only(args)):
                    reason = (
                        'synthetic all-player API result (campaign false Victory/Defeat)'
                        if hint == 'incomplete'
                        else f'API {hint} without OutcomeMonitor credit'
                    )
                    log('false_api_end', players=players,
                        loop=existing.observation.game_loop,
                        api_status=sc.Status.Name(client.status),
                        hint=hint, reason=reason, source='attach_to_ended_game')
                    outcome['reason'] = reason
                    outcome['false_api_end'] = True
                    leave_sc2_open = True
                    print('\n*** API lied / unverified end on attach; SC2 left open. ***\n', flush=True)
                    log('stopped', reason='unverified API end on attach; SC2 left open', hint=hint)
                    await save_replay()
                    log('finished',calls=0,cost=0,run=str(directory))
                    return outcome
                log('result',players=players,source='attach_to_ended_game',
                    loop=existing.observation.game_loop,api_status=sc.Status.Name(client.status))
                await save_replay()
                log('finished',calls=0,cost=0,run=str(directory))
                return outcome
            if client.status != sc.in_game:
                raise RuntimeError('--attach without --map needs an API game already in progress')
        info = attached_info if attached_info is not None else await client.request('game_info',sc.RequestGameInfo())
        outcome.update(map_name=info.map_name,local_map_path=info.local_map_path)
        if not args.map:
            # A reconnect must keep ending telemetry. The current API map name
            # selects a local, hash-checked build; an existing ACTIVE marker may
            # arm the monitor, but an already-terminal bank alone never can.
            local_name = info.local_map_path.replace('\\','/').split('/')[-1]
            outcome_monitor = OutcomeMonitor.for_map(ROOT/'maps'/local_name, 0)
        data = await client.request('data',sc.RequestData(unit_type_id=True,ability_id=True,upgrade_id=True))
        unit_names = {u.unit_id: u.name for u in data.units}
        unit_catalog = {u.unit_id: u for u in data.units}
        objective_evidence = ObjectiveWinEvidence(getattr(args, 'objective', None))
        started = time.monotonic()
        failures = 0
        timeout_errors = 0
        stall_restarts = 0
        uncapped = uncapped_win_death_only(args)
        empty_since = None
        empty_warned_at = None
        last_loop = None
        clock_changed_at = time.monotonic()
        ui_stall_warned_at = None
        seconds_limit = normalize_budget(args.seconds)
        wall_every = float(getattr(args, 'wall_status_seconds', 3600) or 0)
        next_wall_status = started + wall_every if wall_every > 0 else None
        bookmark = BookmarkRecovery(client,data,log,getattr(args,'api_bookmark_recovery',False))
        async def try_restore(observation):
            nonlocal last_loop, empty_since, empty_warned_at, clock_changed_at, failures
            if not await bookmark.recover(observation):
                return False
            # QuickLoad preserves the world but resets API loops; old policy
            # deadlines, tags, action feedback and camera history must be discarded.
            memory.clear()
            camera_memory.clear()
            last_loop = empty_since = empty_warned_at = None
            clock_changed_at = time.monotonic()
            failures = 0
            return True

        async def try_rejoin_same_map(reason):
            """--retry-stalls style recreate for the same map attempt (no campaign advance)."""
            nonlocal stall_restarts, last_loop, empty_since, empty_warned_at, clock_changed_at, failures
            max_stall_restarts = 2  # up to 3 attempts total when --retry-stalls
            if not (getattr(args, 'retry_stalls', False) and args.map
                    and stall_restarts < max_stall_restarts):
                return False
            stall_restarts += 1
            log('stall_recovery', attempt=stall_restarts,
                max_attempts=max_stall_restarts + 1, reason=reason)
            try:
                joined = await client.start(
                    args.map, args.opponent,
                    getattr(args, 'race', 'terran').capitalize())
                outcome['player_id'] = joined.player_id
                memory.clear()
                camera_memory.clear()
                objective_evidence.__init__(getattr(args, 'objective', None))
                last_loop = empty_since = empty_warned_at = None
                clock_changed_at = time.monotonic()
                failures = 0
                return True
            except Exception as exc:
                log('stall_recovery_failed', attempt=stall_restarts,
                    error=type(exc).__name__, detail=str(exc)[:200])
                return False

        async def handle_api_termination(observation, source='observe'):
            """Return 'continue' | 'break' | 'break_leave_open' for player_result/ended."""
            nonlocal leave_sc2_open
            players = [{'player': r.player_id, 'result': sc.Result.Name(r.result)}
                       for r in observation.player_result]
            hint = result_for_player(players, outcome.get('player_id'))
            loop = observation.observation.game_loop
            api_status = sc.Status.Name(client.status)
            # Final frame may still carry HQ/Raynor; refresh before judging.
            objective_evidence.update(observation, unit_names, unit_catalog)
            if await try_restore(observation):
                return 'continue'
            # Real objective win: HQ critically damaged/gone + hero alive, even if
            # the API synthesizes unanimous Victory (result_for_player → incomplete).
            if hint == 'incomplete' and objective_evidence.is_verified_objective_win():
                ev = objective_evidence.evidence()
                log('verified_objective_win', players=players, loop=loop,
                    api_status=api_status, observe_source=source, **ev)
                print('\n*** Verified objective win (HQ destroyed / critical + hero alive). ***\n',
                      flush=True)
                return 'break'
            # incomplete (all-Victory synthesis) without objective evidence is NEVER
            # a verified end — do not close.
            if hint != 'incomplete' and api_end_is_verified(hint, uncapped=uncapped):
                log('result', players=players, loop=loop, api_status=api_status, source=source)
                return 'break'
            # Unverified / incomplete (incl. early all-Victory with HQ still healthy)
            reason = (
                'synthetic all-player API result (campaign false Victory/Defeat)'
                if hint == 'incomplete'
                else f'API {hint} without OutcomeMonitor credit'
            )
            log('false_api_end', players=players, loop=loop, api_status=api_status,
                hint=hint, reason=reason, source=source,
                hq_health=objective_evidence.evidence().get('hq_health'),
                hero_alive=objective_evidence.hero_alive)
            if await try_rejoin_same_map(f'false_api_end:{reason}'):
                return 'continue'
            msg = (
                f'API lied / unverified end (hint={hint}, loop={loop}). '
                'SC2 left open for inspection/grabs; harness exiting without quit.'
            )
            print('\n*** ' + msg + ' ***\n', flush=True)
            outcome['reason'] = reason
            outcome['false_api_end'] = True
            leave_sc2_open = True
            log('stopped', reason=msg, hint=hint, loop=loop)
            return 'break_leave_open'

        def still_running():
            """Hard caps only when positive; 0/None = win/death only."""
            if seconds_limit is not None and time.monotonic() - started >= seconds_limit:
                return False
            return True

        async def maybe_wall_status(observation, view=None):
            nonlocal next_wall_status
            if next_wall_status is None or time.monotonic() < next_wall_status:
                return
            ending = outcome_monitor.poll() if outcome_monitor else None
            own = len(view['self']) if view and view.get('self') is not None else None
            if own is None:
                try:
                    own = sum(1 for u in observation.observation.raw_data.units
                              if u.alliance == 1)  # Self
                except Exception:
                    own = None
            hint = None
            if ending:
                hint = ending.get('status')
            elif observation.player_result or client.status == sc.ended:
                hint = result_for_player(
                    [{'player': r.player_id, 'result': sc.Result.Name(r.result)}
                     for r in observation.player_result],
                    outcome.get('player_id'))
            log('wall_status',
                elapsed_s=round(time.monotonic() - started),
                loop=observation.observation.game_loop,
                own_units=own,
                api_status=sc.Status.Name(client.status),
                outcome_hint=hint,
                player_results=[{'player': r.player_id, 'result': sc.Result.Name(r.result)}
                                for r in observation.player_result],
                monitor=ending)
            next_wall_status = time.monotonic() + wall_every
            # Do not stop solely because the interval elapsed - only on verified win/death
            if ending and ending.get('status') in ('victory', 'defeat'):
                if ending.get('credit_enabled') or not uncapped:
                    log('campaign_outcome', **ending, loop=observation.observation.game_loop)
                    return 'stop'
                return None
            if hint == 'defeat' or (hint == 'victory' and not uncapped):
                return 'stop_result'
            return None

        while still_running():
            try:
                revision = loader.refresh()
                if revision:
                    log('reload',revision=revision)
            except Exception as exc:
                log('reload_error',error=str(exc),retained_revision=loader.revision)
            observation = await client.observe()
            objective_evidence.update(observation, unit_names, unit_catalog)
            if outcome_monitor:
                ending = outcome_monitor.poll()
                if ending:
                    log('campaign_outcome',**ending,loop=observation.observation.game_loop)
                    if ending.get('credit_enabled') or not uncapped:
                        break
                    # Detected but not credited under uncapped win/death - keep playing
                    continue
            wall = await maybe_wall_status(observation)
            if wall == 'stop':
                break
            if wall == 'stop_result':
                log('result',players=[{'player':r.player_id,'result':sc.Result.Name(r.result)}
                                     for r in observation.player_result],
                    loop=observation.observation.game_loop,
                    api_status=sc.Status.Name(client.status), source='wall_status')
                break
            if observation.action_errors:
                log('engine_action_error',errors=[str(e) for e in observation.action_errors])
            if observation.player_result or client.status == sc.ended:
                action = await handle_api_termination(observation, source='observe')
                if action == 'continue':
                    continue
                break
            await bookmark.maybe_save(observation)
            if observation.observation.game_loop == last_loop:
                stalled_for = time.monotonic()-clock_changed_at
                if stalled_for >= 10:
                    # Help/Tutorials (and other pause UI) freeze the game clock. Leave/rejoin
                    # recreates the mission and often reopens Help — a bounce loop. Wait for
                    # a human to CLOSE the panel so the clock advances again.
                    if (ui_stall_warned_at is None
                            or time.monotonic()-ui_stall_warned_at >= 30):
                        ui_stall_warned_at = time.monotonic()
                        dismiss_sent = maybe_send_ui_dismiss_key()
                        log(
                            'awaiting_ui_dismiss',
                            stalled_for_s=round(stalled_for),
                            ui_dismiss_key_sent=dismiss_sent,
                            reason=(
                                'Game clock stalled; close Help/Tutorials/pause if open. '
                                'Not leave/rejoin — that reopens Help and loops.'
                            ),
                        )
                    await asyncio.sleep(0.5)
                    continue
                await asyncio.sleep(0.2)
                continue
            last_loop = observation.observation.game_loop
            clock_changed_at = time.monotonic()
            observe_player = loader.view_module.make_view if loader.view_module else make_view
            view = await observe_player(client,observation,data,info,args.objective)
            if view['self']:
                empty_since = empty_warned_at = None
            else:
                if empty_since is None:
                    empty_since = time.monotonic()
                    log('awaiting_units',reason='No owned units; campaign cinematics can temporarily hide the force')
                empty_for = time.monotonic()-empty_since
                if empty_for >= 90:
                    if getattr(args, 'strict_unit_timeout', False):
                        log('stopped',reason='No owned units observed for ninety seconds; inspect mission UI for outcome')
                        break
                    # Warn-only: mid-campaign cinematics / UI can false-positive
                    if empty_warned_at is None or time.monotonic()-empty_warned_at >= 90:
                        empty_warned_at = time.monotonic()
                        log('checkpoint', kind='no_owned_units',
                            reason='No owned units for 90s+; continuing (win/death only). '
                                   'Pass --strict-unit-timeout to hard-stop.',
                            empty_for_s=round(empty_for))
                await asyncio.sleep(0.2)
                continue
            if args.follow_camera and view['self']:
                director = loader.camera_module.choose_shot if loader.camera_module else choose_shot
                shot = director(view,camera_memory)
                if shot:
                    camera = sc.Action()
                    camera.action_raw.camera_move.center_world_space.x = shot['position'][0]
                    camera.action_raw.camera_move.center_world_space.y = shot['position'][1]
                    await client.request('action',sc.RequestAction(actions=[camera]))
                    log('camera_shot',loop=view['loop'],**shot)
            decision_start = time.monotonic()
            try:
                commands = await asyncio.wait_for(loader.module.decide(view,jev,memory),
                                                  decision_wait)
                failures = 0
            except CallBudgetReached:
                log('stopped',reason='Jev call budget reached')
                break
            except PaymentRequiredResponseError:
                log('stopped',reason='OpenRouter credits unavailable; replenish account credits or check the key cap')
                break
            except (TimeoutError, asyncio.TimeoutError) as exc:
                timeout_errors += 1
                log('decision_error', error='TimeoutError', detail=str(exc)[:200],
                    timeout_count=timeout_errors)
                # Timeouts alone never end the run under win/death; re-enter decide promptly.
                await asyncio.sleep(0.05)
                continue
            except Exception as exc:
                detail = str(exc)[:200]
                log('decision_error',error=type(exc).__name__,detail=detail)
                soft = ('502' in detail or 'no JSON object' in detail
                        or 'InternalServerError' in type(exc).__name__)
                # soft_decision_failure: flaky local SystemOne should not kill LD in ~5s
                if soft:
                    failures += 1
                    log('soft_decision_failure', failures=failures, threshold=25)
                    if failures >= 25:
                        log('stopped',reason='twenty-five consecutive decision failures')
                        break
                    await asyncio.sleep(min(8.0, 1.0 + failures * 0.5))
                    continue
                failures += 1
                if failures >= 5:
                    log('stopped',reason='five consecutive decision failures')
                    break
                await asyncio.sleep(0.5)
                continue
            fresh = await client.observe()
            objective_evidence.update(fresh, unit_names, unit_catalog)
            if fresh.player_result or client.status == sc.ended:
                action = await handle_api_termination(fresh, source='post_decision')
                if action == 'continue':
                    continue
                break
            age = fresh.observation.game_loop-view['loop']
            if age <= age_limit:
                actions, rejects = validate_commands_with_rejects(commands, view, fresh)
            else:
                actions, rejects = [], [
                    {'command': dict(c), 'reason': 'stale_age',
                     'decision_age_loops': age, 'age_limit': age_limit}
                    for c in commands]
            if rejects:
                log('commands_rejected', loop=view['loop'], decision_age_loops=age,
                    age_limit=age_limit, requested=len(commands), submitted=len(actions),
                    rejects=[{k: r[k] for k in ('reason', 'fallback', 'command', 'fallback_command')
                              if k in r} for r in rejects])
            results = []
            if actions:
                response = await client.request('action',sc.RequestAction(actions=actions))
                results = list(response.result)
            feedback = action_feedback(actions,results,view['loop'],len(commands),age,age_limit)
            history = memory.setdefault('action_feedback',[])
            history.append(feedback)
            memory['action_feedback'] = history[-8:]
            log('tick',loop=view['loop'],revision=loader.revision,own_units=len(view['self']),
                units=[{k:u[k] for k in ('tag','type','position','health','health_fraction','build_progress')}
                       for u in view['self']],
                score=fresh.observation.score.score,decision_age_loops=age,
                commands=commands,submitted=len(actions),action_results=results,
                action_errors=[str(e) for e in fresh.action_errors],
                latency_ms=round((time.monotonic()-decision_start)*1000),
                rejects=len(rejects),
                fallbacks=sum(1 for r in rejects if r.get('fallback')))
            wall = await maybe_wall_status(fresh, view)
            if wall == 'stop':
                break
            if wall == 'stop_result':
                log('result',players=[{'player':r.player_id,'result':sc.Result.Name(r.result)}
                                     for r in fresh.player_result],
                    loop=fresh.observation.game_loop,
                    api_status=sc.Status.Name(client.status), source='wall_status')
                break
            # Commands chosen but none submitted: re-observe/re-decide immediately.
            # Slow gemma4 must not leave the army idle for another interval.
            if commands and not actions:
                log('commands_rejected_retry', loop=view['loop'], requested=len(commands))
                continue
            await asyncio.sleep(max(0,args.interval-(time.monotonic()-decision_start)))
        if seconds_limit is not None and time.monotonic()-started >= seconds_limit and outcome.get('status')=='incomplete' and 'reason' not in outcome:
            log('stopped', reason='time limit reached')
        await save_replay()
        log('finished',calls=jev.calls,cost=jev.cost,run=str(directory))
        return outcome
    finally:
        # Airtight: incomplete / false_api_end / leave_sc2_open NEVER quit SC2.
        skip_quit = bool(leave_sc2_open or outcome.get('false_api_end'))
        if getattr(args, 'close_sc2', False) and not skip_quit:
            try:
                from s2clientprotocol import sc2api_pb2 as _sc
                await client.request('quit', _sc.RequestQuit())
                log('close_sc2', status='quit_sent')
            except Exception as exc:
                log('close_sc2', status='quit_failed', error=str(exc)[:200])
        elif getattr(args, 'close_sc2', False) and skip_quit:
            try:
                log('close_sc2', status='skipped_false_api_end',
                    reason='unverified API end; SC2 left open for inspection')
            except Exception:
                pass
        try:
            await client.ws.close()
        except Exception:
            pass
        events.close()
        controller.close()
        # Keep SC2 alive unless --close-sc2: --attach can resume after harness edits.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map',help='Local .SC2Map path; single-player unless --opponent')
    parser.add_argument('--race',choices=('terran','zerg','protoss','random'),default='terran')
    parser.add_argument('--attach',action='store_true',help='Reuse an API-enabled SC2 process')
    parser.add_argument('--opponent',action='store_true',help='Add VeryEasy Zerg AI for a melee map')
    parser.add_argument('--port',type=int,default=5001)
    parser.add_argument('--window-size',type=int,nargs=2,default=(1280,800),metavar=('WIDTH','HEIGHT'))
    parser.add_argument('--window-position',type=int,nargs=2,metavar=('X','Y'))
    parser.add_argument('--api-bookmark-recovery',action='store_true',help='Experimental: save periodically and restore once on anomalous all-player defeat with owned structures')
    parser.add_argument('--follow-camera',action='store_true',help='Center display camera on owned units; does not change raw policy observations')
    parser.add_argument('--seconds',type=float,default=0,
                        help='Wall-clock abort after N seconds; 0 = unlimited (exit only on win/death)')
    parser.add_argument('--max-calls',type=int,default=0,
                        help='Jev call budget; 0 = unlimited (no CallBudgetReached)')
    parser.add_argument('--memory-mode', choices=MEMORY_MODES, default=default_memory_mode(),
                        help='Cross-run/game memory control flag; default none (cold); env: JEV_MEMORY_MODE')
    parser.add_argument('--wall-status-seconds',type=float,default=3600,
                        help='Log wall_status checkpoint every N seconds without stopping; 0 disables')
    parser.add_argument('--strict-unit-timeout',action='store_true',
                        help='Hard-stop after 90s with no owned units (legacy); default is warn-only checkpoint')
    parser.add_argument('--interval',type=float,default=0.35)
    parser.add_argument('--max-age-loops',type=int,default=64,
                        help='Discard decisions older than this many game loops; the 3s Jev wait can extend the cutoff so a finished-in-time call is not dropped')
    parser.add_argument('--objective',default='Keep your units alive and defeat visible enemy units.')
    parser.add_argument('--doctor',action='store_true')
    parser.add_argument('--close-sc2',action='store_true',
                        help='After the run, quit the attached/local SC2 process for batch teardown')
    parser.add_argument('--retry-stalls',action='store_true',
                        help='Bounded in-process map restart after a ten-second game-clock stall (pause/tutorial); does not auto-dismiss UI')
    args=parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print('Harness stopped. SC2 was left running.')


if __name__ == '__main__':
    main()

