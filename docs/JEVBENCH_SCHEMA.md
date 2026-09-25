# JevBench result schema

`jevbench.schema.json` is the canonical schema for one benchmark-attempt
packet. It is based on the result packet already used by the harness handover
and on the fields emitted by `result.json` and `scripts/report.py`.

The required identity and provenance fields are deliberately small:

- `bench_id` identifies a stable benchmark line.
- `run_id` identifies one attempt.
- `status` is normalized to `win`, `loss`, `tie`, `incomplete`, or `blocked`.
- `source` is `ours` for an independently run result or `official` for a
  cited external result. Official results require `source_url`.

The existing harness uses `victory`, `defeat`, and `incomplete`; packets map
those values to `win`, `loss`, and `incomplete`. Run measurements such as
`calls`, `cost_usd`, `latency_median_ms`, `latency_p95_ms`, and
`actions_submitted` stay as optional top-level fields so current result rows
remain easy to publish. Other scalar measurements go in `metrics`.

`map`, `hq_win_evidence`, and the Jev backend fields are optional because they
describe the current StarCraft II surface, not every future JevBench domain.
Use `scenario` for comparable inputs and `metadata` for display or provenance
that should not be treated as a score. Keep API keys, bearer tokens, and other
secrets out of packets and artifact paths.

Example:

```json
{
  "schema_version": 1,
  "bench_id": "LD-DG",
  "run_id": "20260921T073335Z",
  "map": "traynor01 / Liberation Day",
  "status": "win",
  "jev_via": "openjev",
  "jev_model": "openjev-latest",
  "openjev_base_url": "192.168.0.10:8011",
  "guide_model": "google/gemini-2.5-flash",
  "memory_mode": "none",
  "calls": 412,
  "wall_seconds": 247.4,
  "hq_win_evidence": true,
  "source": "ours",
  "artifact_paths": [
    "runs/20260921T073335Z/events.jsonl",
    "runs/20260921T073335Z/game.SC2Replay"
  ],
  "notes": "Single-flight enforced."
}
```
