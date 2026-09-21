"""Single realistic-size decide probe (game-like payload, 6 questions).

Run inside one shell after dot-sourcing env-LD-DG.ps1 / env-LD-LJ.ps1:
  . .\scripts\opencode\env-LD-DG.ps1; .\.venv\Scripts\python.exe scripts/opencode/probe_game_payload.py

One serial Jev.ask only. Prints GAMEPAYLOAD_GREEN or GAMEPAYLOAD_RED.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def main() -> int:
    from jev_sc2.jev import Jev

    jev = Jev(lambda *a, **k: None, "blocker-probe")
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
        str(100 + i): {
            "type": "choice",
            "instructions": "Choose the next action for this unit to advance the objective.",
            "criteria": {
                "continue": "Keep existing orders unchanged.",
                "attack_move": "Attack-move toward the enemy.",
            },
        }
        for i in range(6)
    }
    started = time.monotonic()
    try:
        answers = await asyncio.wait_for(
            jev.ask(state, questions), timeout=(jev.timeout_ms / 1000.0) + 30
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"GAMEPAYLOAD_RED time={time.monotonic() - started:.1f}s "
            f"{type(exc).__name__}: {str(exc)[:250]}"
        )
        return 1
    nulls = [k for k, v in answers.items() if not (v or {}).get("choice")]
    if nulls:
        print(f"GAMEPAYLOAD_RED null choices for {nulls}")
        return 1
    print(
        f"GAMEPAYLOAD_GREEN time={time.monotonic() - started:.1f}s "
        f"answers={json.dumps(answers)[:200]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
