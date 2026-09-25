# Fortnite adapter spike plan

Status: planning artifact only. This is not Fortnite support, and the repository
must not claim Fortnite support from this document.

The spike starts only after the generic harness architecture and its versioned
contracts land. A Fortnite support claim is gated on that architecture plus a
recorded SC2/Fortnite bakeoff. Until both gates pass, this remains a thin adapter
sketch and a list of questions to answer.

## Purpose and boundaries

The generic harness should own the decision loop, policy state, logging,
freshness checks, and outcome reporting. A game adapter should own only the
translation between that contract and one game's transport and vocabulary.

The spike does not include a Fortnite dependency, game launcher, credentials,
automation against a live service, or a second policy. It also does not assume
that Fortnite exposes a suitable authoritative control transport. Finding and
validating that transport is part of the spike.

## Reference seam from the current SC2 harness

These are the seams to preserve when the generic architecture is extracted;
they are not the final package layout:

| Generic responsibility | Current SC2 reference | Adapter boundary |
| --- | --- | --- |
| Session and transport | `jev_sc2/sc2.py` | Connect, start or attach, request observations, submit actions, close |
| Player-visible projection | `jev_sc2/view.py` | Convert raw game data into fair observations and legal action candidates |
| Decision policy | `player.py` | Consume the generic observation and return policy choices; no game transport |
| Terminal evidence | `jev_sc2/outcome.py` | Normalize engine and independently checked objective evidence |
| Optional presentation | `jev_sc2/camera.py` | Keep display following separate from gameplay control |

The extraction must not move SC2 protocol types into the generic contract. The
same policy-facing fields should work when the source is a different game, and
game-specific facts should stay behind the adapter.

## Thin adapter sketch

The exact names belong to the architecture work. The boundary should be
equivalent to this shape:

```python
class GameAdapter(Protocol):
    async def connect(self, config: SessionConfig) -> SessionInfo: ...
    async def observe(self) -> Observation: ...
    async def apply(self, commands: Sequence[Command]) -> Sequence[ActionResult]: ...
    def outcome(self, observation: Observation) -> Outcome | None: ...
    async def close(self) -> None: ...


class FortniteAdapter(GameAdapter):
    async def observe(self):
        raw = await self.transport.observe()
        return normalize_fortnite_observation(raw, self.last_observation)

    async def apply(self, commands):
        checked = validate_against_last_observation(commands, self.last_observation)
        raw_results = await self.transport.apply(checked)
        return normalize_fortnite_results(raw_results)

    def outcome(self, observation):
        return normalize_fortnite_outcome(observation)
```

`normalize_fortnite_*` is deliberately a placeholder, not an implementation
promise. The adapter must preserve unknowns rather than fill gaps with inferred
facts.

The minimum normalized records are:

- `Observation`: session and tick identity, game time, objective, player-visible
  entities, resources or other economy facts when available, affordances,
  visibility/freshness metadata, and the source timestamp.
- `Command`: an entity reference from the latest observation, an explicit action
  verb, and a target or point where applicable. The core must not manufacture a
  command the adapter did not offer.
- `ActionResult`: accepted, rejected, stale, or unknown status; the engine's
  reason when available; and the observation/tick used to apply it.
- `Outcome`: victory, defeat, draw, active, or unknown, with source and evidence
  separate from the normalized status.

Stable entity identity, visibility rules, action legality, and terminal evidence
are adapter responsibilities. The policy may choose among presented affordances
but must not receive hidden entities, enemy intent, or transport-specific debug
fields.

## Fortnite spike questions

Before writing the adapter, record answers and evidence for:

1. What authoritative transport can start or attach to a permitted test session,
   observe player-visible state, submit ordinary actions, and close cleanly?
2. Which game mode, map, and objective provide a repeatable bounded scenario?
3. Are entity identities stable between observations, and how are despawns,
   respawns, inventory changes, and player-visible fog represented?
4. Which actions can be represented as explicit affordances with engine results?
   What does the transport report for stale, illegal, delayed, or accepted work?
5. How are match end, objective completion, disconnect, timeout, and ambiguous
   results distinguished?
6. What timing budget, rate limit, and session isolation constraints apply to the
   generic loop?

An unanswered question is a spike blocker, not permission to guess a mapping.

## Bakeoff gate

Run the same normalized harness probe against SC2 and the selected Fortnite
scenario after the generic contract is frozen. Use fresh sessions and preserve
raw evidence plus normalized logs. At minimum, exercise:

| Probe | Required evidence |
| --- | --- |
| Connect/start/close | Session lifecycle succeeds without adapter-specific policy code |
| Observation fairness | Only player-visible facts are normalized; hidden data stays absent or explicitly unknown |
| Action round trip | A presented action is submitted, its result is classified, and the next observation shows the measured effect or no effect |
| Freshness/legality | Stale entity references and rejected actions are reported without being silently retried or rewritten |
| Terminal state | Victory, defeat, timeout/disconnect, and unknown are distinguishable with evidence |
| Realtime behavior | Latency and failure rates are measured against the architecture's declared budget |

The result is `PASS`, `FAIL`, or `DEFER` with the scenario, run count, timing
statistics, rejected-action counts, terminal evidence, and known gaps recorded.
Only `PASS` on the bakeoff and a landed generic architecture can unlock an
explicit Fortnite support statement. A spike, partial mapping, or successful
connection is not a pass.

## Exit criteria and non-goals

The spike is complete when the contract questions have evidence, the thin
adapter passes the shared contract tests, and the bakeoff record is reviewable.
It is not complete merely because a Fortnite session can be observed or joined.

No production Fortnite adapter, public support claim, live-service automation,
or secret-bearing configuration should be added as part of this plan.
