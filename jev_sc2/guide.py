"""Gemini Flash guide / oversight via OpenRouter chat completions.

Runs less often than Jev. Proposes strategy notes and intents only —
never picks unit actions. Jev remains the sole typed decision chooser.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from openrouter import OpenRouter

# Chosen 2026-09-20 after listing OpenRouter google/gemini-*-flash*.
# google/gemini-2.5-flash: reliable JSON with response_format; non-lite/non-image.
# Rejected for default: gemini-3.8-flash (finish=error/truncation),
# gemini-3.5-flash (finish=length), *-image*, *:batch*, *-preview*.
# Override via GUIDE_MODEL (e.g. google/gemini-3.5-flash-lite for cheaper).
DEFAULT_GUIDE_MODEL = "google/gemini-2.5-flash"

GUIDE_SYSTEM = """You are the strategy / oversight brain for a StarCraft II agent.
Another model (Jev) makes all typed action decisions. You do NOT pick unit orders,
ability ids, or per-unit micro. Return ONLY a JSON object with keys:
  strategy: short label (e.g. defend_approach, attack_base, rebuild_economy, hold)
  notes: 1-3 sentences of situational guidance for Jev's state context
  suggested_intents: array of short intent strings Jev may weigh (not commands)
  avoid: array of anti-patterns to avoid (e.g. workers_as_attackers, army_all_to_tc)
Keep each string compact. No markdown fences."""


def guide_enabled() -> bool:
    return os.getenv("GUIDE_ENABLED", "0").strip() in {"1", "true", "TRUE", "yes", "on"}


def guide_every_n_ticks() -> int:
    try:
        return max(1, int(os.getenv("GUIDE_EVERY_N_TICKS", "8")))
    except ValueError:
        return 8


def guide_model() -> str:
    return os.getenv("GUIDE_MODEL", DEFAULT_GUIDE_MODEL).strip() or DEFAULT_GUIDE_MODEL


def compact_view_summary(view: dict[str, Any], memory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shrink a harness view into guide-safe facts (no full candidate menus)."""
    memory = memory or {}
    self_units = view.get("self") or []
    by_type: dict[str, int] = {}
    workers = 0
    army = 0
    structures = 0
    idle = 0
    worker_names = {"SCV", "Drone", "Probe", "MULE"}
    structure_hint = {"CommandCenter", "OrbitalCommand", "PlanetaryFortress", "Barracks",
                      "Factory", "Starport", "SupplyDepot", "Bunker", "Refinery",
                      "EngineeringBay", "MissileTurret", "SensorTower", "Armory",
                      "FusionCore", "GhostAcademy", "TechLab", "Reactor",
                      "Hatchery", "Lair", "Hive", "SpawningPool", "RoachWarren",
                      "Nexus", "Pylon", "Gateway", "CyberneticsCore"}
    for u in self_units:
        t = u.get("type") or "Unknown"
        by_type[t] = by_type.get(t, 0) + 1
        if t in worker_names:
            workers += 1
        elif t in structure_hint or u.get("build_progress") is not None and u.get("build_progress", 1) < 1:
            structures += 1
        else:
            army += 1
        orders = u.get("orders") or []
        if not orders:
            idle += 1
    enemies = []
    for e in (view.get("visible_entities") or view.get("enemy") or [])[:24]:
        if isinstance(e, dict):
            enemies.append({"type": e.get("type"), "position": e.get("position")})
        else:
            enemies.append(str(e)[:80])
    resources = view.get("resources") or {}
    return {
        "loop": view.get("loop"),
        "objective": view.get("objective"),
        "resources": {k: resources.get(k) for k in ("minerals", "vespene", "food_used", "food_cap")},
        "own_counts_by_type": by_type,
        "own_workers": workers,
        "own_army_approx": army,
        "own_structures_approx": structures,
        "idle_own_units": idle,
        "visible_enemies_sample": enemies[:16],
        "previous_guide": memory.get("guide_advice"),
        "strategy_chosen_by_jev": memory.get("strategy"),
        "note": "Counts are approximate from observation; fog may hide threats.",
    }


def format_guide_for_state(advice: dict[str, Any]) -> dict[str, Any]:
    """Shape injected into Jev state — advisory only."""
    return {
        "role": "oversight_not_action_chooser",
        "strategy": advice.get("strategy"),
        "notes": advice.get("notes"),
        "suggested_intents": advice.get("suggested_intents") or [],
        "avoid": advice.get("avoid") or [],
        "model": advice.get("model"),
        "loop": advice.get("loop"),
        "instruction_for_jev": (
            "Consider guide_oversight notes and avoid-list when choosing among "
            "typed criteria. You still make every concrete choice; the guide "
            "never issues unit commands."
        ),
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_advice(raw: dict[str, Any], *, model: str, loop: Any) -> dict[str, Any]:
    intents = raw.get("suggested_intents") or raw.get("suggests_intents") or raw.get("intents") or []
    avoid = raw.get("avoid") or raw.get("anti_patterns") or []
    if isinstance(intents, str):
        intents = [intents]
    if isinstance(avoid, str):
        avoid = [avoid]
    return {
        "strategy": str(raw.get("strategy") or "continue_operations")[:120],
        "notes": str(raw.get("notes") or "")[:800],
        "suggested_intents": [str(x)[:160] for x in list(intents)[:12]],
        "avoid": [str(x)[:120] for x in list(avoid)[:12]],
        "model": model,
        "loop": loop,
    }


class Guide:
    """Async Gemini Flash planner; call maybe_advise on a cadence."""

    def __init__(self, log=None, model: str | None = None):
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("Set OPENROUTER_API_KEY for Guide")
        self.model = model or guide_model()
        self.client = OpenRouter(
            api_key=key,
            x_open_router_title="Jev SC2 Gemini Guide",
        )
        self.log = log or (lambda event, **fields: None)
        self.calls = 0
        self.cost = 0.0

    async def advise(self, view_summary: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        user = (
            "Compact SC2 observation summary follows. Return JSON only.\n"
            + json.dumps(view_summary, default=str)[:12000]
        )
        response = await self.client.chat.send_async(
            model=self.model,
            messages=[
                {"role": "system", "content": GUIDE_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=512,
            # Prefer no hidden reasoning budget so JSON is not truncated.
            reasoning_effort="none",
            timeout_ms=20000,
        )
        self.calls += 1
        content = ""
        usage_cost = 0.0
        # Prefer live attributes; fall back to model_dump for SDK variance.
        try:
            choices_obj = getattr(response, "choices", None) or []
            if choices_obj:
                msg = getattr(choices_obj[0], "message", None)
                content = getattr(msg, "content", None) if msg is not None else None
                if content is None and isinstance(choices_obj[0], dict):
                    content = (choices_obj[0].get("message") or {}).get("content")
            usage_obj = getattr(response, "usage", None)
            if usage_obj is not None:
                usage_cost = float(getattr(usage_obj, "cost", 0) or 0)
        except Exception:
            content = ""
        if not content:
            try:
                dumped = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
            except Exception:
                dumped = {}
            choices = dumped.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content") or ""
            usage = dumped.get("usage") or {}
            usage_cost = usage_cost or float(usage.get("cost") or 0) or 0.0
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        self.cost += usage_cost
        raw = _extract_json(content if isinstance(content, str) else str(content))
        advice = _normalize_advice(raw, model=self.model, loop=view_summary.get("loop"))
        self.log(
            "guide",
            latency_ms=round((time.monotonic() - started) * 1000),
            model=self.model,
            summary_chars=len(json.dumps(view_summary, default=str)),
            advice=advice,
            cost=usage_cost,
        )
        return advice

    async def maybe_advise(
        self,
        view: dict[str, Any],
        memory: dict[str, Any],
        *,
        tick: int | None = None,
        force: bool = False,
    ) -> dict[str, Any] | None:
        if not guide_enabled() and not force:
            return memory.get("guide_advice")
        n = guide_every_n_ticks()
        tick_i = tick if tick is not None else int(memory.get("guide_tick", 0)) + 1
        memory["guide_tick"] = tick_i
        last = memory.get("guide_last_tick")
        due = force or last is None or (tick_i - int(last)) >= n
        if not due:
            return memory.get("guide_advice")
        summary = compact_view_summary(view, memory)
        advice = await self.advise(summary)
        memory["guide_advice"] = advice
        memory["guide_last_tick"] = tick_i
        return advice


async def refresh_guide_into_state(
    view: dict[str, Any],
    state: dict[str, Any],
    memory: dict[str, Any],
    *,
    log=None,
    force: bool = False,
) -> dict[str, Any] | None:
    """Ensure a Guide instance in memory and inject guide_oversight into state."""
    if not guide_enabled() and not force:
        cached = memory.get("guide_advice")
        if cached:
            state["guide_oversight"] = format_guide_for_state(cached)
        return cached
    guide = memory.get("_guide")
    if guide is None:
        guide = Guide(log=log)
        memory["_guide"] = guide
    advice = await guide.maybe_advise(view, memory, force=force)
    if advice:
        state["guide_oversight"] = format_guide_for_state(advice)
    return advice
