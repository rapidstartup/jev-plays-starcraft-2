# Fortnite adapter spike plan

Status: proposal only. Fortnite is not supported by this repository, and this
document is not a support claim. The spike may begin only after the generic
harness architecture and its adapter contract are landed. A Fortnite support
claim requires that contract plus a completed, recorded bakeoff.

## Goal

Test whether a thin Fortnite adapter can provide the generic harness with the
same four responsibilities already separated in the SC2 experiment:

1. start or attach to a game session;
2. return player-visible observations;
3. validate and submit policy-selected actions; and
4. report action results, terminal outcomes and run artifacts.

The adapter owns platform protocol details. The policy must not import a
Fortnite SDK, know Fortnite actor names, or receive data that a player could
not observe.

## Prerequisites and non-goals

Before implementation, the architecture work must land a versioned generic
contract for observations, commands, action results, session lifecycle,
timeouts, and terminal outcomes. It must also specify ownership of visibility
filtering, legality checks, telemetry, replay/artifact storage, and shutdown.

This spike does not:

- add a Fortnite dependency, launcher, bot, or input-injection path;
- promise access to a supported Fortnite automation interface;
- change the existing SC2 runtime or claim that SC2 and Fortnite are already
  interchangeable; or
- add Fortnite-specific behavior to the generic policy.

## Thin adapter sketch

The final names belong to the architecture contract. The following is the
smallest boundary the Fortnite experiment should need to implement:

```python
class GameAdapter(Protocol):
    async def open(self, config: SessionConfig) -> Session: ...
    async def observe(self, session: Session) -> Observation: ...
    async def act(
        self, session: Session, commands: Sequence[Command]
    ) -> Sequence[ActionResult]: ...
    async def close(self, session: Session) -> None: ...
```

The generic types should contain platform-neutral facts only:

- `Observation`: monotonic tick/time, objective state, player-visible entities,
  resources, spatial facts, available affordances, and visibility metadata;
- `Command`: an explicit generic intent plus an optional observed entity or
  position reference; no platform-specific IDs in policy-facing data;
- `ActionResult`: accepted/rejected/unknown status, stable reason category,
  observed effects, and the source tick; and
- `TerminalOutcome`: win, loss, draw, stopped, or unknown with evidence.

The adapter may retain opaque platform IDs internally and map them to stable
run-local entity references. It must reject stale, invisible, unavailable, or
otherwise illegal targets before submission when the platform permits that
check, while preserving the platform's authoritative result.

### Fortnite boundary questions

The discovery spike must answer these questions with evidence rather than
assumptions:

- What supported or permitted observation and control channel can provide a
  player-scoped view and authoritative action results?
- Can session identity, tick ordering, reconnects, pauses, and terminal state
  be recorded reliably?
- Which generic actions can be mapped without silently changing their meaning?
- What is the visibility model for remote players, loot, objectives, and map
  information?
- Can the adapter enforce rate limits, backpressure, cancellation, and safe
  shutdown without blocking the generic decision loop?
- What deterministic fixture or instrumented test arena can be replayed for a
  fair comparison?

An unanswered question is a spike result and a blocker, not a reason to fill
the gap with a scripted fallback or an inferred success.

## Bakeoff gate

Run the same bounded policy contract against the existing SC2 path and the
Fortnite spike path only after the architecture exposes equivalent generic
telemetry for both. Keep platform-specific capabilities in separate columns;
do not score an unsupported Fortnite capability as a pass.

The bakeoff record must include:

| Area | Required evidence |
| --- | --- |
| Lifecycle | repeatable session start/attach, stop, reconnect behavior, and terminal detection |
| Observation | player-scoped visibility, tick/order integrity, freshness, and no hidden-state leakage |
| Actions | command mapping, legality rejection, acceptance/result correlation, and cancellation behavior |
| Timing | end-to-end latency, stale-observation rate, rate-limit behavior, and bounded backpressure |
| Outcomes | independently checkable win/loss/unknown evidence; no success inferred from API acknowledgement alone |
| Artifacts | replay or equivalent trace, structured events, and enough metadata to reproduce the run |
| Safety | no secrets in logs, no uncontrolled external actions, and clean shutdown on adapter failure |

Use a small fixed scenario set with repeated runs, a declared timeout and
budget, and a pre-registered pass/fail rule. A passing connectivity smoke is
not a bakeoff pass. The result must state which generic capabilities are
covered, which remain Fortnite-specific, and which are unknown.

## Ordered deliverables

1. Land the generic architecture contract and a fake adapter with unit tests.
2. Add an adapter conformance suite that the SC2 implementation and any spike
   adapter must pass.
3. Write a Fortnite discovery report answering the boundary questions and
   naming the permitted test channel and fixture.
4. Implement only the thinnest adapter needed for that fixture; keep it behind
   an explicit experimental flag and do not modify the default SC2 path.
5. Run and archive the bakeoff, including failures and unknown outcomes.
6. Make a separate go/no-go decision. Only a successful architecture review
   and bakeoff may authorize a future Fortnite support statement.

Until steps 1 and 5 are complete, references to Fortnite should use
“planned spike” or “experimental adapter,” never “supported.”
