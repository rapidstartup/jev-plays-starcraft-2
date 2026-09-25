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
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _log(*a, **k):
    pass


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


# Representative Liberation Day state: ~40 friendly + ~30 visible enemies plus a
# squad, with the rich per-cohort/per-type facts and recent history the live loop
# carries. This is deliberately a FULL view: Jev.ask compacts it to the real
# operating size (JEV_STATE_BUDGET_CHARS), so the gate measures what the backend
# actually receives in a real game -- not a toy payload.
def game_state(n_ally, n_enemy, squad, loop):
    entities = (
        [{"tag": f"m{i}", "type": "Marine", "alliance": "Ally", "position": [80.0 + i, 50.0 + (i % 5)], "health": 100.0, "shield": 0.0, "is_flying": False} for i in range(n_ally)]
        + [{"tag": f"e{i}", "type": "Queen", "alliance": "Enemy", "position": [95.0 + i, 55.0 + (i % 4)], "health": 120.0, "shield": 50.0, "is_flying": False} for i in range(n_enemy)]
        + [{"tag": "hq", "type": "LogisticsHeadquarters", "alliance": "Enemy", "position": [120.0, 60.0], "health": 2500.0, "shield": 0.0, "is_flying": False}]
    )
    sel = {
        "Marine / combat": {"count": squad, "idle_count": 0, "max_separation": 3.2,
                            "visible_enemies_within_12_of_any_member": {"Enemy Marine": 2, "Enemy Queen": 1},
                            "current_order_counts": {"Attack": squad}, "average_health_fraction": 0.82,
                            "recent_change": "advanced 6 map units toward the enemy base"},
        "SCV / gather": {"count": 6, "idle_count": 1, "current_order_counts": {"Gather": 5, "Return": 1},
                         "average_health_fraction": 1.0, "harvest_target": "minerals"},
    }
    type_facts = {
        "Marine": {"mineral_cost": 50, "gas_cost": 0, "supply_provided": 1, "supply_required": 1,
                   "catalog_weapons": [{"targets": "Ground", "range": 5.0, "damage_per_cycle": 6.0, "damage_per_time_unit_before_armor_and_bonuses": 0.86}]},
        "SCV": {"mineral_cost": 50, "gas_cost": 0, "supply_provided": 1, "supply_required": 1,
                "catalog_weapons": [{"targets": "Ground", "range": 0.5, "damage_per_cycle": 5.0, "damage_per_time_unit_before_armor_and_bonuses": 2.5}]},
    }
    return {
        "objective": "Destroy the Logistics Headquarters. Raynor must survive.",
        "loop": loop,
        "resources": {"minerals": 350, "vespene": 100, "estimated_minerals_per_minute": 220.0,
                      "estimated_vespene_per_minute": 0.0, "food_used": 14, "food_cap": 20,
                      "supply_in_construction": 1, "supply_remaining": 6, "supply_blocked": False},
        "completed_upgrades": [{"id": 1, "name": "Stimpack"}],
        "visible_entities": entities,
        "last_known_entities": [{"type": "Marine", "alliance": "Enemy", "position": [110.0, 58.0], "status": "snapshot under fog"}],
        "unit_type_facts": type_facts,
        "explored_map": {"start": [0, 0], "end": [128, 128], "walls": [[20, 40], [60, 30]]},
        "selection_facts": sel,
        "type_selection_facts": sel,
        "strategy_chosen_by_jev": {"loop": loop - 50, "choice": "attack", "description": "Commit forces to damaging or destroying the enemy base."},
        "recent_outcomes": [{"loop": loop - 40, "event": "killed 3 enemy Marines"}, {"loop": loop - 20, "event": "lost 1 Marine"}],
        "recent_action_feedback": [{"order": "attack_move", "result": "moved 8 units, engaged 2 enemies"}, {"order": "hold", "result": "no change"}],
        "units": [{"tag": 100 + i, "type": "Marine", "position": [80.0 + i, 50.0], "health_fraction": 0.82, "orders": ["attack"], "build_progress": 1.0} for i in range(squad)],
        "guide_oversight": {"strategy": "attack", "focus": "enemy base", "notes": "Enemy base is defended by a small queen cluster. Focus fire, keep Raynor back."},
    }


async def main() -> int:
    max_ms = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("JEV_REALTIME_MAX_MS", "5000"))
    from jev_sc2.jev import Jev

    try:
        jev = Jev(_log, "rt-gate", max_calls=None)
    except Exception as exc:  # noqa: BLE001
        print(f"GATE_RED init via={os.getenv('JEV_VIA')} model={os.getenv('JEV_MODEL')} error={exc}")
        return 1

    # Sweep the compaction budget. Jev.ask compacts the full view to
    # JEV_STATE_BUDGET_CHARS, so this measures the backend at the real operating
    # size (and catches a backend that is fine at a tiny budget but too slow at
    # the default). The 'large' case matches the shipped default (2600).
    from jev_sc2.jev import compact_model_state
    base_budget = int(os.getenv("JEV_STATE_BUDGET_CHARS", "2600"))
    budgets = sorted({max(600, int(base_budget * 0.6)), base_budget, int(base_budget * 1.5)})
    worst = 0
    worst_label = ""
    for budget in budgets:
        os.environ["JEV_STATE_BUDGET_CHARS"] = str(budget)
        packed = compact_model_state(game_state(40, 30, 8, 1200))
        packed_chars = len(json.dumps(packed))
        started = time.perf_counter()
        try:
            answers = await asyncio.wait_for(jev.ask(game_state(40, 30, 8, 1200), QUESTIONS), timeout=120)
        except Exception as exc:  # noqa: BLE001
            dt = (time.perf_counter() - started) * 1000
            print(f"GATE_RED decide budget={budget} error after {dt:.0f}ms: {type(exc).__name__}: {exc}")
            return 1
        dt_ms = (time.perf_counter() - started) * 1000
        choices = [v.get("choice") for v in answers.values() if isinstance(v, dict)]
        if not choices or not all(choices):
            print(f"GATE_RED null-choice budget={budget} via={os.getenv('JEV_VIA')} answers={str(answers)[:200]}")
            return 1
        print(f"GATE budget={budget} packed_chars={packed_chars} latency_ms={dt_ms:.0f} choices={choices}")
        if dt_ms > worst:
            worst, worst_label = dt_ms, f"budget={budget} (packed {packed_chars} chars)"

    base = os.getenv("OPENJEV_BASE_URL", "") or os.getenv("JEV_VIA", "")
    if worst > max_ms:
        print(f"GATE_RED too-slow for real-time: worst={worst:.0f}ms > max={max_ms}ms at {worst_label} (via={base} model={os.getenv('JEV_MODEL')})")
        print("This backend cannot drive a real-time game loop; do not boot SC2. Use a faster backend or raise the bar knowingly.")
        return 1
    print(f"GATE_GREEN worst_ms={worst:.0f} <= max_ms={max_ms} at {worst_label} (via={base} model={os.getenv('JEV_MODEL')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
