"""Structured human-readable controller log for live run observation.

Writes runs/<stamp>/controller.log (scrolling text) and controller.jsonl
(structured events). Never logs API keys or secrets.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# Events mirrored into the controller surface (and how to summarize them).
_IMPORTANT = frozenset({
    'control', 'connected', 'loading_map', 'joined_game', 'jev_init',
    'guide', 'jev', 'tick', 'camera_shot', 'checkpoint', 'wall_status',
    'awaiting_units', 'stall_recovery', 'stall_recovery_failed',
    'campaign_outcome', 'result', 'stopped', 'finished', 'decision_error',
    'jev_request_rejected', 'jev_request_split', 'reload', 'reload_error',
    'engine_action_error', 'close_sc2', 'replay_unavailable',
    'api_bookmark_restored', 'run_start', 'false_api_end', 'unverified_api_end',
    'verified_objective_win',
})

_SECRET_KEYS = frozenset({
    'api_key', 'OPENROUTER_API_KEY', 'JEV_API_KEY', 'TYPESAFE_API_KEY',
    'authorization', 'password', 'token', 'secret',
})


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ('***' if k in _SECRET_KEYS or 'key' in k.lower() and 'present' not in k.lower()
                    else _safe(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _summarize(event: str, fields: dict) -> str:
    if event == 'control':
        return (f"exit_policy={fields.get('exit_policy')} "
                f"max_calls={fields.get('max_calls')} seconds={fields.get('seconds')} "
                f"wall_status={fields.get('wall_status_seconds')}s via={fields.get('jev_via')}")
    if event == 'connected':
        return f"SC2 {fields.get('version')} obj={fields.get('objective', '')[:60]}"
    if event == 'loading_map':
        return f"map={fields.get('map')}"
    if event == 'jev_init':
        return f"model={fields.get('model')} via={fields.get('via')} timeout_ms={fields.get('timeout_ms')}"
    if event == 'guide':
        advice = fields.get('advice') or {}
        focus = advice.get('focus') or advice.get('priority') or advice.get('summary')
        return f"latency={fields.get('latency_ms')}ms focus={str(focus)[:80] if focus else '-'}"
    if event == 'jev':
        answers = (fields.get('response') or {}).get('answers') or {}
        if not answers and isinstance(fields.get('response'), dict):
            answers = fields['response']
        keys = list((fields.get('questions') or answers or {}).keys())[:6]
        chosen = []
        if isinstance(answers, dict):
            for k in keys[:4]:
                a = answers.get(k)
                if isinstance(a, dict) and 'choice' in a:
                    chosen.append(f"{k}->{a['choice']}")
                elif a is not None:
                    chosen.append(f"{k}->{a}")
        return (f"latency={fields.get('latency_ms')}ms via={fields.get('via')} "
                f"q={len(fields.get('questions') or keys)} "
                f"{'; '.join(chosen)[:120]}")
    if event == 'tick':
        return (f"loop={fields.get('loop')} units={fields.get('own_units')} "
                f"cmds={len(fields.get('commands') or [])} "
                f"submitted={fields.get('submitted')} latency={fields.get('latency_ms')}ms")
    if event == 'wall_status':
        return (f"elapsed={fields.get('elapsed_s')}s loop={fields.get('loop')} "
                f"units={fields.get('own_units')} api={fields.get('api_status')} "
                f"outcome={fields.get('outcome_hint')}")
    if event == 'checkpoint':
        return f"{fields.get('kind')}: {fields.get('reason') or fields.get('note') or ''}"[:140]
    if event == 'camera_shot':
        return f"loop={fields.get('loop')} subject={fields.get('subject') or fields.get('reason')}"
    if event in ('stopped', 'finished', 'campaign_outcome', 'result'):
        return (f"status={fields.get('status')} reason={fields.get('reason')} "
                f"calls={fields.get('calls')}").strip()
    if event == 'false_api_end' or event == 'unverified_api_end':
        return (f"hint={fields.get('hint')} loop={fields.get('loop')} "
                f"{fields.get('reason') or ''}")[:140]
    if event == 'verified_objective_win':
        hq = fields.get('hq_health') or {}
        return (f"hq={hq} hero={fields.get('hero_name')}:"
                f"{fields.get('hero_alive')} loop={fields.get('loop')}")[:140]
    if event == 'decision_error':
        return f"{fields.get('error')}: {fields.get('detail')}"
    if event == 'awaiting_units':
        return fields.get('reason') or 'no owned units'
    if event == 'stall_recovery':
        return f"attempt={fields.get('attempt')}/{fields.get('max_attempts')}"
    # Generic fallback - keep short, strip bulky payloads
    slim = {k: v for k, v in fields.items()
            if k not in ('state', 'questions', 'response', 'units', 'commands', 'advice')
            and not isinstance(v, (dict, list))}
    return ' '.join(f'{k}={v}' for k, v in list(slim.items())[:8])[:160]


class ControllerLog:
    """Append-only controller.log + controller.jsonl beside events.jsonl."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log_path = self.directory / 'controller.log'
        self.jsonl_path = self.directory / 'controller.jsonl'
        self._log = self.log_path.open('a', buffering=1, encoding='utf-8')
        self._jsonl = self.jsonl_path.open('a', buffering=1, encoding='utf-8')
        self.emit('run_start', directory=str(self.directory))

    def emit(self, event: str, **fields: Any) -> None:
        safe = _safe(fields)
        summary = _summarize(event, safe)
        now = time.time()
        stamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        line = f"{stamp}  [{event}]  {summary}\n"
        self._log.write(line)
        row = {'time': now, 'event': event, 'summary': summary, **safe}
        # Drop bulky nested blobs from jsonl (TUI/widget use summary + scalars)
        for bulky in ('state', 'questions', 'response', 'units', 'commands'):
            row.pop(bulky, None)
        if 'advice' in row and isinstance(row['advice'], dict):
            row['advice'] = {k: row['advice'][k] for k in list(row['advice'])[:8]}
        self._jsonl.write(json.dumps(row, default=str) + '\n')

    def mirror(self, event: str, **fields: Any) -> None:
        if event in _IMPORTANT or event.startswith('checkpoint'):
            self.emit(event, **fields)

    def close(self) -> None:
        try:
            self._log.close()
        finally:
            self._jsonl.close()

    def wrap(self, log_fn: Callable[..., None]) -> Callable[..., None]:
        """Return a log() that forwards to log_fn and mirrors into controller."""
        def wrapped(event: str, **fields: Any) -> None:
            log_fn(event, **fields)
            try:
                self.mirror(event, **fields)
            except Exception:
                pass  # never break the harness for controller I/O
        return wrapped


def unlimited(value) -> bool:
    """True when a CLI budget means 'no hard cap' (0, None, or negative)."""
    return value is None or value <= 0


def normalize_budget(value):
    """Return None for unlimited, else the positive int/float budget."""
    if unlimited(value):
        return None
    return value
