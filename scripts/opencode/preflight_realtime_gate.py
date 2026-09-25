"""Real-time gate: measure an ACTUAL game-sized decision latency through the real
harness Jev path and fail fast if the backend is too slow to drive a real-time
game loop. Run BEFORE any SC2 run so a slow backend is rejected up front instead
of timing out mid-run (which starves the agent and causes defeats).

Usage:  set env, then  .venv/Scripts/python.exe scripts/opencode/preflight_realtime_gate.py [max_ms]
Exit 0 only if a representative game-sized decide returns a non-null choice AND
p95-ish (max of 2 calls) latency <= max_ms (default 5000).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _log(*a, **k):
    pass


# Representative Liberation Day mid-game state: ~40 friendly + ~30 visible enemies,
# plus a squad. This mirrors the size the live loop actually sends.
GAME_STATE = {
    "objective": "Destroy the Logistics Headquarters. Raynor must survive.",
    "loop": 1200,
    "resources": {"minerals": 150, "vespene": 0, "food_used": 12, "food_cap": 20},
    "visible_entities": (
        [{"tag": f"m{i}", "type": "Marine", "alliance": "Ally", "position": [80.0 + i, 50.0 + (i % 5)]} for i in range(40)]
        + [{"tag": f"e{i}", "type": "Queen", "alliance": "Enemy", "position": [95.0 + i, 55.0 + (i % 4)]} for i in range(30)]
        + [{"tag": "hq", "type": "LogisticsHeadquarters", "alliance": "Enemy", "position": [120.0, 60.0]}]
    ),
    "squad": [
        {"tag": 100 + i, "type": "Marine", "position": [80.0 + i, 50.0], "health_fraction": 0.8, "build_progress": 1.0}
        for i in range(8)
    ],
}

QUESTIONS = {
    "q1": {
        "type": "choice",
        "instructions": "Choose the best action for the marine squad.",
        "criteria": {
            "attack_move": "Attack-move the squad toward the enemy base.",
            "hold": "Hold the current position.",
            "retreat": "Retreat away from the enemy.",
        },
    },
    "q2": {
        "type": "choice",
        "instructions": "Choose the most important immediate risk.",
        "criteria": {
            "defense": "Enemy units threatening the squad.",
            "economy": "Losing workers or economy.",
            "none": "No immediate risk.",
        },
    },
}


async def main() -> int:
    max_ms = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("JEV_REALTIME_MAX_MS", "5000"))
    from jev_sc2.jev import Jev

    try:
        jev = Jev(_log, "rt-gate", max_calls=None)
    except Exception as exc:  # noqa: BLE001
        print(f"GATE_RED init via={os.getenv('JEV_VIA')} model={os.getenv('JEV_MODEL')} error={exc}")
        return 1

    times = []
    for attempt in range(2):  # first call may warm the model; take the worse of two
        started = time.perf_counter()
        try:
            answers = await asyncio.wait_for(jev.ask(dict(GAME_STATE), QUESTIONS), timeout=120)
        except Exception as exc:  # noqa: BLE001
            print(f"GATE_RED decide call{attempt} timeout/error after {time.perf_counter()-started:.1f}s: {type(exc).__name__}: {exc}")
            return 1
        dt_ms = (time.perf_counter() - started) * 1000
        choices = [v.get("choice") for v in answers.values() if isinstance(v, dict)]
        if not choices or not all(choices):
            print(f"GATE_RED null-choice via={os.getenv('JEV_VIA')} answers={str(answers)[:200]}")
            return 1
        times.append(dt_ms)
        print(f"GATE call{attempt} latency_ms={dt_ms:.0f} choices={choices}")

    worst = max(times)
    base = os.getenv("OPENJEV_BASE_URL", "") or os.getenv("JEV_VIA", "")
    if worst > max_ms:
        print(f"GATE_RED too-slow for real-time: worst={worst:.0f}ms > max={max_ms}ms (via={base} model={os.getenv('JEV_MODEL')})")
        print("This backend cannot drive a real-time game loop; do not boot SC2. Use a faster backend or raise the bar knowingly.")
        return 1
    print(f"GATE_GREEN worst_ms={worst:.0f} <= max_ms={max_ms} (via={base} model={os.getenv('JEV_MODEL')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
