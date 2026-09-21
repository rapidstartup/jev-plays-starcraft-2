"""Strict preflight via the real harness decide path (jev_sc2/jev.py).

Usage (env already set by env-LD-*.ps1):
  .venv/Scripts/python.exe scripts/opencode/preflight_decide.py

Asks a single tiny choice question through Jev.ask and requires a
non-null, non-empty answers.q1.choice. Prints PREFLIGHT_GREEN/RED.
Single call only - never parallel (dgemma-small is single-sequence).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _log(*args, **kwargs):
    pass


async def main() -> int:
    from jev_sc2.jev import Jev

    via = os.environ.get("JEV_VIA", "(unset)")
    model = os.environ.get("JEV_MODEL", "(unset)")
    timeout = os.environ.get("JEV_TIMEOUT_MS", "(unset)")
    base = os.environ.get("OPENJEV_BASE_URL", "")
    started = time.monotonic()
    try:
        jev = Jev(_log, "preflight", max_calls=None)
    except Exception as exc:  # noqa: BLE001 - preflight must report, not crash
        print(f"PREFLIGHT_RED init via={via} model={model} error={exc}")
        return 1
    questions = {
        "q1": {
            "type": "choice",
            "instructions": "pick",
            "criteria": {"a": "A", "b": "B"},
        }
    }
    try:
        answers = await asyncio.wait_for(
            jev.ask({}, questions), timeout=(jev.timeout_ms / 1000.0) + 30
        )
    except Exception as exc:  # noqa: BLE001
        print(f"PREFLIGHT_RED decide via={via} model={model} base={base} error={type(exc).__name__}: {str(exc)[:200]}")
        return 1
    elapsed = time.monotonic() - started
    try:
        choice = answers.get("q1", {}).get("choice")
    except AttributeError:
        choice = None
    if choice is None or not str(choice).strip() or str(choice) == "null":
        print(f"PREFLIGHT_RED null-choice via={via} model={model} answers={str(answers)[:200]}")
        return 1
    print(
        f"PREFLIGHT_GREEN via={via} model={model} choice={choice} "
        f"time={elapsed:.1f}s timeout_ms={timeout} base={base}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
