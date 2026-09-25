# Harness architecture: SC2 layers to generic game ports

**Status: HOLD MERGE.** This is an architecture decision record for the next
porting step, not a claim that Fortnite support exists or that the SC2 policy is
game-complete.

## Boundary and design decision

The harness has one deliberate ownership rule:

> Jev chooses among the choices the game adapter exposes. Python owns facts,
> legality, transport, timing, logging, and recovery. No second tactical model
> silently replaces Jev after a failed or ambiguous decision.

The current SC2 path is:

```text
SC2 client
  │ binary Protobuf over localhost WebSocket
  ▼
SC2 transport (jev_sc2/sc2.py)
  │ raw observations + queries
  ▼
SC2 observation/action adapter (jev_sc2/view.py)
  │ player-visible state + mechanically offered candidates
  ▼
player.py policy
  │ state + narrow choice questions
  ▼
Jev through OpenRouter Decisions (jev_sc2/jev.py)
  │ structured choices/probabilities
  ▼
fresh observation → validation → SC2 action transport
```

`--follow-camera` is a parallel presentation path. It may submit a camera move
to the SC2 client, but it never supplies policy observations or gameplay orders.
OBS captures the display; streaming is an output concern, not part of the agent
control loop.

## Layer breakdown

| Layer | Current SC2 implementation | Portable contract | SC2-specific residue |
| --- | --- | --- | --- |
| Observation | `SC2.observe()` plus `view.make_view()` | Produce a bounded, player-fair observation with clock, objective, entities, visibility, resources, capabilities and recent facts | SC2 raw units, alliances, snapshots, pathing/visibility grids, ability catalog and protobuf fields |
| Decision | `player.decide(view, jev, memory)` asks Jev narrow structured-choice questions | A policy consumes normalized state and returns intent/command selections; policy memory is separate from adapter state | SC2 action names and unit-type conventions in prompts; current selection/cohort policy |
| Jev provider | `Jev` defaults to the allowlisted `typesafe/jev-1.13` through OpenRouter Decisions; TypeSafe/OpenJev-compatible paths also exist | A single structured decision provider with model, timeout, cost, probability and error telemetry | OpenRouter Decisions request shape, provider model IDs, API credentials and provider-specific response errors |
| Candidate construction | `view.py` derives actions from queried abilities, visible targets, resource costs and placement results | Adapter offers only actions the game says are currently possible, with stable IDs and descriptions | SC2 ability IDs, remaps, target kinds, unit tags, building placement and raw action protobuf |
| Validation | Re-observe after inference; reject stale, duplicate, unowned, unoffered and no-longer-visible commands; let the engine return final results | Validate against a fresh authoritative state, preserve rejects/fallbacks, and never treat submission as completion | SC2 tags, visibility display types, action errors and attack/move fallback rules |
| Transport | Serialized request/response access under `SC2.lock`; real-time mode advances while Jev is thinking; no `RequestStep` | Session lifecycle, serialized requests, deadlines, reconnect/stop behavior and action submission | Local `sc2api` WebSocket, Protobuf message names, `RequestObservation`, `RequestQuery`, `RequestAction` and replay save |
| Outcome | API result plus objective evidence/campaign bank checks; ambiguous endings remain incomplete | Explicit outcome source and evidence policy; unknown is distinct from win/loss | SC2 player results, campaign bank instrumentation, objective structures and hero evidence |
| Camera/streaming | `camera.choose_shot()` reads the view and camera memory; controller sends only `camera_move`; OBS captures the window | Optional presentation director consuming view snapshots without influencing policy | SC2 camera action, map coordinates, window/display setup and OBS scene/capture configuration |
| Experiment loop | Controller observes, builds view, optionally moves camera, calls policy, re-observes, validates, submits, logs, and repeats; committed policy reloads at boundaries | A repeatable run manifest, bounded budget, append-only telemetry, replay/artifact capture and measured outcome | SC2 replay files, game-loop age, map loading and campaign-specific recovery |

The portable contract is intentionally narrower than the SC2 implementation. A
future adapter may expose richer game-specific facts under an extension field,
but the core policy must not depend on them to remain runnable.

## What is already validated in SC2

The repository's tests and recorded runs establish infrastructure behavior, not
game-playing competence:

- SC2 communication is the retail player's ordinary API: binary Protobuf over a
  localhost WebSocket. Fog remains enabled, hidden units and enemy orders are not
  sent to Jev, and stale snapshots are labeled as stale rather than live targets.
- `view.py` constructs mechanically available candidates and uses SC2 queries for
  ability and building-placement checks. The engine remains authoritative.
- A decision is followed by a fresh observation before commands are submitted.
  Commands older than the configured game-loop age are discarded; ownership,
  target visibility, duplicate casters and offer membership are checked.
- The OpenRouter Decisions path is the selected Jev integration. The provider
  model is allowlisted, retries are disabled for decisions, calls are budgeted,
  and request latency, cost, model/provider label, probabilities and outcomes
  are logged without API keys.
- Camera state is separate from policy memory. Camera selection follows visible
  engagements, damage and moving forces, but sends only display-camera movement.
- The loop records accepted/rejected commands, engine results, observation age,
  reload revision, outcome evidence and replay availability. A successful API
  response or accepted action is not itself evidence of mission success.

Useful source-of-truth documents are [the verified procedure](PROCEDURE.md),
[the experiment report](EXPERIMENT_REPORT.md), and the focused tests in
`tests/test_infra.py`, `tests/test_camera.py`, `tests/test_outcome.py` and
`tests/test_galaxy_bridge.py`.

## Generic port shape

The next refactor should introduce a game-neutral runner around a small adapter,
without moving SC2 policy logic into the runner:

```text
GamePort
  connect() / close()
  observe() -> Observation
  candidates(observation) -> [Candidate]
  validate(commands, fresh_observation) -> ValidationResult
  submit(actions) -> ActionResult
  outcome(observation) -> Outcome | unknown
  save_artifacts() -> ArtifactRefs

GenericRunner
  observe → normalize → Jev policy → fresh observe → validate → submit → log
```

`Observation`, `Candidate`, `Command`, `ValidationResult`, `ActionResult` and
`Outcome` should be small typed contracts. They should carry stable IDs and
timestamps/sequence numbers, while game adapters retain raw payloads only for
diagnostics. The runner should know about budgets, stale-state policy, decision
timeouts, logging and experiment manifests; it should not know what an SCV,
marine, Fortnite player, ability ID or weapon cooldown means.

The first extraction can be an SC2 adapter with behavior-preserving tests. This
is preferable to changing policy and transport at the same time: existing SC2
replays and logs remain the regression fixture while the seam is introduced.

## Path to Fortnite

Fortnite is a new adapter, not an SC2 reskin. The integration mechanism must be
confirmed before implementation: an authorized game API, a test harness, or a
screen/input route has materially different visibility, action, latency and
fairness properties. Do not infer that the SC2 API guarantees a Fortnite API.

1. **Write the integration boundary.** Record what can be observed, how player
   visibility is represented, how actions are submitted, rate limits, pause and
   reconnect behavior, and what constitutes authoritative outcome evidence. Keep
   secrets and service credentials outside the repository.
2. **Build an observer-only Fortnite adapter.** Normalize player position/state,
   visible entities, inventory/resources, objective/progress, clock and
   observation sequence. Preserve uncertainty explicitly; never turn an
   occluded or delayed screen/API sample into a fact.
3. **Add candidate actions and strict validation.** Candidate IDs should describe
   controls available in the current state. Validate freshness, ownership,
   target visibility and duplicate commands where those concepts exist. The
   adapter, not Jev, must handle input encoding and the authoritative game
   response.
4. **Run synthetic Jev decisions first.** Feed recorded normalized observations
   to the same OpenRouter/Jev boundary with no game connection. Check schema,
   latency, budget accounting, probability capture and provider failure behavior.
5. **Submit one safe action in a bounded sandbox.** Verify that the submitted
   action matches the selected candidate, that no fallback policy takes over, and
   that disconnects leave the game in a known state. Keep camera capture and
   policy control independently switchable.
6. **Measure before expanding.** Compare observation age, decision latency,
   action acceptance, rejected-command reasons, objective progress, survival and
   unknown outcomes. A visually plausible action is not a successful experiment.
7. **Only then add experiment sequencing.** Add Fortnite run manifests, replay or
   capture references, and outcome evidence without changing the generic runner.
   Game-specific prompt extensions belong in the Fortnite adapter/policy
   boundary, with a portable baseline kept available for comparison.

The first Fortnite milestone is therefore: observe → normalize → ask Jev →
validate one action → submit → record evidence. It is not autonomous victory,
competitive play, or equivalence with SC2's fog/API fairness until those claims
are separately measured.

## Merge gate

**HOLD MERGE** until Nathan's card authorizes merge. This note intentionally does
not add Fortnite code, change the SC2 policy, alter provider credentials, or
claim a new gameplay result.
