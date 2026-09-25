# JevBench result packets

The canonical machine-readable contract is [`jevbench-result.schema.json`](jevbench-result.schema.json).
It describes one result packet for a game run, copycat smoke test, probe, or official citation.

The required packet fields come from the existing run handoff: benchmark and attempt IDs,
outcome, backend/model settings, call count, provenance, artifacts, and notes. The optional
latency, cost, action, and correctness fields preserve measurements already emitted by the
SC2 report and probe results.

Use these status values consistently:

- `win`: the benchmark success bar was independently verified.
- `loss`: the run reached a verified failed outcome.
- `incomplete`: the run ended without a verified win or loss.
- `blocked`: setup or a preflight failure prevented the attempt; `blocker` is required.

`map`, `jev_via`, `jev_model`, `guide_model`, and `hq_win_evidence` may be `null` when a
row is not a game run. This keeps the same row shape usable for future non-game benchmarks.
Native harness outcomes such as `victory` and `defeat` should only be translated to `win` and
`loss` after applying the relevant success bar; otherwise publish `incomplete`.
