"""Replay the game's first decide shape: strategy+coordination, previous_strategy=None.

Run: . .\\scripts\\opencode\\env-LD-LJ.ps1; .\\.venv\\Scripts\\python.exe scripts/opencode/probe_first_call.py
Single serial call. Prints traceback on failure to locate the AttributeError.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def main() -> int:
    from jev_sc2.jev import Jev

    if len(sys.argv) > 1:
        os.environ['JEV_TIMEOUT_MS'] = sys.argv[1]
    jev = Jev(lambda *a, **k: None, "firstcall-probe")
    options = {
        "attack": "Commit forces to damaging or destroying the enemy base.",
        "strengthen": "Increase military strength through resource collection and production.",
        "protect": "Preserve owned units and structures from current threats.",
        "assemble": "Bring separated units together and accumulate a force before committing to an engagement.",
        "explore": "Acquire information about the map and enemy positions.",
        "recover": "Restore income and replace losses.",
        "continue_operations": "Let current tasks progress before changing commitment.",
    }
    state = {
        "objective": "Destroy the Logistics Headquarters. Raynor must survive.",
        "previous_strategy": None,
        "resources": {"minerals": 150, "vespene": 0},
        "guide_advice": {"strategy": "initial_drop", "notes": "Find a safe landing zone."},
        "visible_entities": [
            {"tag": str(i), "type": "Marine", "alliance": "Ally", "position": [80.0 + i, 50.0]}
            for i in range(6)
        ],
    }
    questions = {
        "strategy": {
            "type": "choice",
            "instructions": "Choose the current strategic priority for completing the mission.",
            "criteria": options,
        },
        "coordination": {
            "type": "choice",
            "instructions": "Choose how to organize the next control selections.",
            "criteria": {
                "by_type": "Keep different unit types in separate selections.",
                "by_current_order": "Separate each unit type by its current first order.",
                "mobile_combat": "Combine units with movement and attack controls.",
            },
        },
    }
    started = time.monotonic()
    try:
        answers = await asyncio.wait_for(
            jev.ask(state, questions), timeout=(jev.timeout_ms / 1000.0) + 30
        )
    except Exception:  # noqa: BLE001
        print(f"FIRSTCALL_RED time={time.monotonic() - started:.1f}s")
        traceback.print_exc()
        return 1
    print(f"FIRSTCALL_GREEN time={time.monotonic() - started:.1f}s answers={str(answers)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
