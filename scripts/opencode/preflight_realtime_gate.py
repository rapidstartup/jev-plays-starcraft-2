"""Real-time gate: measure ACTUAL game-sized decision latencies through the real
harness Jev path and fail fast if the backend is too slow to drive a real-time
game loop. Run BEFORE any SC2 run so a slow backend is rejected up front instead
of timing out mid-run (which starves the agent and causes defeats).

It sends an ESCALATING series of DIFFERENT Liberation Day-sized states
(small -> mid -> late) and gates on the WORST latency. This matters because
single-sequence models (GLiFormer/jeff) degrade super-linearly with state size
and can pass a cached/small warm probe while being unusable in a real game. A
single fixed-size (or repeated-identical) probe gives false GREENs.

Usage:  set env, then  .venv/Scripts/python.exe scripts/opencode/preflight_realtime_gate.py [max_ms]
Exit 0 only if every size returns a non-null choice AND the worst latency <= max_ms.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _log(*a, **k):
    pass


# Escalating (ally, enemy, squad) sizes. 'mid' mirrors the live loop early/mid game;
# 'large' mirrors late game. Distinct shapes/loops defeat server-side response caching.
SERIES = [
    ("small", 20, 20, 6, 600),
    ("mid", 40, 30, 8, 1200),
    ("large", 60, 45, 10, 2400),
]

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


def game_state(n_ally, n_enemy, squad, loop):
    return {
        "objective": "Destroy the Logistics Headquarters. Raynor must survive.",
        "loop": loop,
        "resources": {"minerals": 150, "vespene": 0, "food_used": 12, "food_cap": 20},
        "visible_entities": (
            [{"tag": f"m{i}", "type": "Marine", "alliance": "Ally", "position": [80.0 + i, 50.0 + (i % 5)]} for i in range(n_ally)]
            + [{"tag": f"e{i}", "type": "Queen", "alliance": "Enemy", "position": [95.0 + i, 55.0 + (i % 4)]} for i in range(n_enemy)]
            + [{"tag": "hq", "type": "LogisticsHeadquarters", "alliance": "Enemy", "position": [120.0, 60.0]}]
        ),
        "squad": [
            {"tag": 100 + i, "type": "Marine", "position": [80.0 + i, 50.0], "health_fraction": 0.8, "build_progress": 1.0}
            for i in range(squad)
        ],
    }


async def main() -> int:
    max_ms = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("JEV_REALTIME_MAX_MS", "5000"))
    from jev_sc2.jev import Jev

    try:
        jev = Jev(_log, "rt-gate", max_calls=None)
    except Exception as exc:  # noqa: BLE001
        print(f"GATE_RED init via={os.getenv('JEV_VIA')} model={os.getenv('JEV_MODEL')} error={exc}")
        return 1

    worst = 0
    worst_label = ""
    for label, a, e, s, loop in SERIES:
        started = time.perf_counter()
        try:
            answers = await asyncio.wait_for(jev.ask(game_state(a, e, s, loop), QUESTIONS), timeout=120)
        except Exception as exc:  # noqa: BLE001
            dt = (time.perf_counter() - started) * 1000
            print(f"GATE_RED decide {label} (ally={a} enemy={e}) error after {dt:.0f}ms: {type(exc).__name__}: {exc}")
            return 1
        dt_ms = (time.perf_counter() - started) * 1000
        choices = [v.get("choice") for v in answers.values() if isinstance(v, dict)]
        if not choices or not all(choices):
            print(f"GATE_RED null-choice {label} via={os.getenv('JEV_VIA')} answers={str(answers)[:200]}")
            return 1
        print(f"GATE {label} ally={a} enemy={e} squad={s} latency_ms={dt_ms:.0f} choices={choices}")
        if dt_ms > worst:
            worst, worst_label = dt_ms, f"{label} (ally={a} enemy={e})"

    base = os.getenv("OPENJEV_BASE_URL", "") or os.getenv("JEV_VIA", "")
    if worst > max_ms:
        print(f"GATE_RED too-slow for real-time: worst={worst:.0f}ms > max={max_ms}ms at {worst_label} (via={base} model={os.getenv('JEV_MODEL')})")
        print("This backend cannot drive a real-time game loop; do not boot SC2. Use a faster backend or raise the bar knowingly.")
        return 1
    print(f"GATE_GREEN worst_ms={worst:.0f} <= max_ms={max_ms} at {worst_label} (via={base} model={os.getenv('JEV_MODEL')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
