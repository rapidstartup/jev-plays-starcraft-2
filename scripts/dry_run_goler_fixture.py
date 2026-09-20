#!/usr/bin/env python3
"""No-run decision test: Guide (optional) + Jev on a frozen Goler-mode fixture.

Does not launch StarCraft II. Loads OPENROUTER_API_KEY from repo .env or env.

Examples:
  GUIDE_ENABLED=1 uv run python scripts/dry_run_goler_fixture.py \\
      tests/fixtures/goler_modes/workers-as-attackers.json
  uv run python scripts/dry_run_goler_fixture.py --all --guide
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from jev_sc2.guide import (
    Guide,
    compact_view_summary,
    format_guide_for_state,
    guide_model,
)
from jev_sc2.jev import Jev


def _load_env():
    load_dotenv(ROOT / ".env")
    # Box secrets fallback for dry-runs (never print values)
    secrets = Path("/workspace/secrets/jev.env")
    if secrets.exists() and not os.getenv("OPENROUTER_API_KEY"):
        for line in secrets.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _log(event, **fields):
    row = {"event": event, **fields}
    # Strip bulky nested state from console for readability
    if event == "jev" and "state" in row:
        row = {**row, "state": {"_omitted": True, "keys": list(fields.get("state", {}).keys())}}
    print(json.dumps(row, default=str), flush=True)


async def run_one(path: Path, *, use_guide: bool, max_calls: int) -> dict:
    fixture = json.loads(path.read_text())
    view = fixture["view"]
    probe = fixture["jev_probe"]
    memory: dict = {}
    result: dict = {"fixture": fixture.get("id") or path.stem, "path": str(path)}

    guide_advice = None
    if use_guide:
        os.environ["GUIDE_ENABLED"] = "1"
        guide = Guide(log=_log)
        summary = compact_view_summary(view, memory)
        guide_advice = await guide.advise(summary)
        memory["guide_advice"] = guide_advice
        result["guide"] = guide_advice
        result["guide_cost"] = guide.cost

    state = {
        "objective": view.get("objective"),
        "resources": view.get("resources"),
        "loop": view.get("loop"),
        "own_summary": compact_view_summary(view, memory),
        "fixture_mode": fixture.get("goler_mode"),
    }
    if guide_advice:
        state["guide_oversight"] = format_guide_for_state(guide_advice)

    jev = Jev(_log, session=f"dry-goler-{path.stem}", max_calls=max_calls)
    answers = await jev.ask(
        state,
        {
            "priority": {
                "type": "choice",
                "instructions": probe["instructions"]
                + (" Consider guide_oversight if present; you still choose." if use_guide else ""),
                "criteria": probe["criteria"],
            }
        },
    )
    choice = (answers.get("priority") or {}).get("choice")
    result["jev_choice"] = choice
    result["jev_answers"] = answers
    result["jev_calls"] = jev.calls
    result["jev_cost"] = jev.cost
    result["criteria_keys"] = list(probe["criteria"])
    return result


async def main():
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", nargs="?", help="Path to one fixture JSON")
    parser.add_argument("--all", action="store_true", help="Run all fixtures in goler_modes/")
    parser.add_argument("--guide", action="store_true", help="Call Gemini guide before Jev")
    parser.add_argument("--max-calls", type=int, default=4)
    args = parser.parse_args()

    fixtures: list[Path] = []
    if args.all:
        fixtures = sorted((ROOT / "tests/fixtures/goler_modes").glob("*.json"))
    elif args.fixture:
        fixtures = [Path(args.fixture)]
    else:
        parser.error("pass a fixture path or --all")

    if not os.getenv("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY missing (.env or /workspace/secrets/jev.env)")

    print(
        json.dumps(
            {
                "event": "dry_run_start",
                "guide": args.guide,
                "guide_model": guide_model() if args.guide else None,
                "jev_model": os.getenv("JEV_MODEL", "typesafe/jev-1.13"),
                "fixtures": [str(p) for p in fixtures],
            }
        ),
        flush=True,
    )

    outcomes = []
    for path in fixtures:
        try:
            outcomes.append(await run_one(path, use_guide=args.guide, max_calls=args.max_calls))
        except Exception as exc:
            outcomes.append({"fixture": path.stem, "error": f"{type(exc).__name__}: {exc}"})

    summary = {"event": "dry_run_summary", "results": outcomes}
    print(json.dumps(summary, default=str, indent=2), flush=True)
    if any("error" in o for o in outcomes):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
