#!/usr/bin/env python3
"""Run a same-image Astra vs Gemini Flash vision bakeoff.

The Astra model id is deliberately required (or read from ASTRA_MODEL): this
script must record the provider's real id rather than guess a version. Results
contain each model id, wall latency, reported billed cost, and a transparent
case-insensitive reference-match quality score. The API key is read from the
environment/.env and is never printed.

Example:
  uv run python scripts/benchmark_vision.py shot.png \
      --astra-model "$ASTRA_MODEL" \
      --expected "enemy base" "two marines" \
      --output docs/experiments/vision-bakeoff.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from openrouter import OpenRouter

from jev_sc2.guide import DEFAULT_GUIDE_MODEL, image_data_url


DEFAULT_PROMPT = (
    "Inspect this StarCraft II screenshot. Return JSON only with keys "
    "observations (array of short visible facts), confidence (0 to 1), and "
    "summary (one short sentence). Do not infer units or map areas hidden by "
    "fog, overlays, or unreadable UI."
)


def _response_dump(response: Any) -> dict[str, Any]:
    try:
        dumped = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
    except Exception:
        dumped = {}
    return dumped if isinstance(dumped, dict) else {}


def _response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if choices:
        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if content is None and isinstance(first, dict):
            content = (first.get("message") or {}).get("content")
        if content:
            return _content_text(content)
    dumped = _response_dump(response)
    choices = dumped.get("choices") or []
    if choices:
        return _content_text((choices[0].get("message") or {}).get("content", ""))
    return ""


def _content_text(content: Any) -> str:
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _response_cost(response: Any) -> float:
    usage = getattr(response, "usage", None)
    if usage is not None:
        value = getattr(usage, "cost", None)
        if value is not None:
            return float(value or 0)
    return float((_response_dump(response).get("usage") or {}).get("cost") or 0)


def _response_model(response: Any) -> str | None:
    value = getattr(response, "model", None)
    if value:
        return str(value)
    value = _response_dump(response).get("model")
    return str(value) if value else None


def quality_score(answer: str, expected: list[str]) -> dict[str, Any]:
    """Score only the reference facts supplied for this image; never invent a grade."""
    folded = answer.casefold()
    matched = [fact for fact in expected if fact.casefold() in folded]
    missing = [fact for fact in expected if fact.casefold() not in folded]
    return {
        "score": round(len(matched) / len(expected), 3) if expected else None,
        "matched": matched,
        "missing": missing,
        "basis": "case-insensitive reference phrase matches in model response",
    }


async def run_model(
    client: Any,
    model: str,
    image_url: str,
    prompt: str,
    expected: list[str],
) -> dict[str, Any]:
    started = time.monotonic()
    response = await client.chat.send_async(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a careful visual QA evaluator. Return JSON only.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=512,
        reasoning_effort="none",
        timeout_ms=30000,
    )
    answer = _response_text(response)
    return {
        "model_id": model,
        "response_model_id": _response_model(response),
        "latency_ms": round((time.monotonic() - started) * 1000),
        "cost_usd": _response_cost(response),
        "quality": quality_score(answer, expected),
        "valid_json": _parse_json(answer) is not None,
    }


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


async def run(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY missing (.env or environment)")
    image_path = Path(args.image)
    image_url = image_data_url(image_path)
    client = OpenRouter(
        api_key=os.environ["OPENROUTER_API_KEY"],
        x_open_router_title="Jev SC2 vision bakeoff",
    )
    results = {}
    for label, model in (("astra", args.astra_model), ("gemini_flash", args.gemini_model)):
        results[label] = await run_model(client, model, image_url, args.prompt, args.expected)
    return {
        "schema_version": 1,
        "image": str(image_path),
        "prompt": args.prompt,
        "expected_facts": args.expected,
        "models": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="One screenshot used for both API calls")
    parser.add_argument(
        "--astra-model",
        default=os.getenv("ASTRA_MODEL"),
        help="Exact Astra provider model id (also ASTRA_MODEL; required)",
    )
    parser.add_argument(
        "--gemini-model",
        default=DEFAULT_GUIDE_MODEL,
        help=f"Exact Gemini model id (default: {DEFAULT_GUIDE_MODEL})",
    )
    parser.add_argument("--expected", nargs="+", required=True, help="Visible reference facts for quality scoring")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output", type=Path, help="Write JSON results to this path")
    args = parser.parse_args()
    if not args.astra_model:
        parser.error("--astra-model or ASTRA_MODEL is required; do not guess an Astra model id")
    result = asyncio.run(run(args))
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
