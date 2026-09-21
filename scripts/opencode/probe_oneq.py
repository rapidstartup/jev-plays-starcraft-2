"""Single-question game-size probe: same state shape as probe_game_payload.py, one question.

Run: . .\\scripts\\opencode\\env-LD-DG.ps1; .\\.venv\\Scripts\\python.exe scripts/opencode/probe_oneq.py
Distinguishes question-count failure from state-size failure on dgemma-small.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def main() -> int:
    from jev_sc2.jev import Jev

    jev = Jev(lambda *a, **k: None, "oneq-probe")
    state = {
        "objective": "Destroy the Logistics Headquarters. Raynor must survive.",
        "resources": {"minerals": 150, "vespene": 0},
        "visible_entities": [
            {"tag": str(i), "type": "Marine", "alliance": "Ally", "position": [80.0 + i, 50.0]}
            for i in range(6)
        ],
        "squad": [
            {
                "tag": 100 + i,
                "type": "Marine",
                "position": [80.0 + i, 50.0],
                "health_fraction": 1.0,
                "build_progress": 1,
                "nearby_terrain": {},
            }
            for i in range(6)
        ],
    }
    questions = {
        "100": {
            "type": "choice",
            "instructions": "Choose the next action for this unit to advance the objective.",
            "criteria": {
                "continue": "Keep existing orders unchanged.",
                "attack_move": "Attack-move toward the enemy.",
            },
        }
    }
    started = time.monotonic()
    try:
        answers = await asyncio.wait_for(
            jev.ask(state, questions), timeout=(jev.timeout_ms / 1000.0) + 30
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ONEQ_RED time={time.monotonic() - started:.1f}s {type(exc).__name__}: {str(exc)[:250]}")
        return 1
    choice = (answers.get("100") or {}).get("choice")
    if not choice:
        print("ONEQ_RED null choice")
        return 1
    print(f"ONEQ_GREEN time={time.monotonic() - started:.1f}s choice={choice}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
