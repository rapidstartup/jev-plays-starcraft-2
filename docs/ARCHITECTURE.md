# Jev Plays architecture: SC2 harness layers to generic game ports

> **HOLD MERGE.** This is an architecture decision record for the Jev Plays
> family. Do not merge or promote the Fortnite work until Nathan supplies the
> card/approval.

## Decision in one paragraph

Jev owns bounded choices; the Python harness owns observation shaping, candidate
generation, legality checks, transport, timing, logging, and outcome evidence.
OpenRouter is the current decision transport for the Jev model, not a second
policy. Camera movement and livestreaming are presentation concerns and never
choose gameplay actions. StarCraft II remains an adapter behind this control
loop. A future Fortnite adapter should implement the same port contract without
bringing SC2 protocol types, tags, map assumptions, or campaign state into the
portable layers.

This document describes the current implementation and the seam to extract. It
does not claim that a Fortnite control or observation interface has been chosen.

## Current loop

The implemented SC2 path is:

```text
SC2 Protobuf/WebSocket
        |
        v
  SC2 session client -----> raw observation, game info, data, ability queries
        |
        v
  SC2 observation adapter (jev_sc2/view.py)
        |
        v
  player.py asks narrow questions through Jev
        |
        v
  Jev decision gateway (OpenRouter Decisions by default)
        |
        v
  fresh observation + command validation
        |
        v
  SC2 action transport ---> engine result/action errors/outcome

  The presentation branch reads the same view:
  view ---> camera director ---> camera-only SC2 action ---> OBS/display capture
```

The game stays in realtime while inference runs. Before submission, the harness
observes again and removes duplicate, unoffered, unowned, invisible, or otherwise
stale commands. The engine remains the final authority on whether an action is
legal or succeeds.

## Layer breakdown

| Layer | Implemented for SC2 | Portable contract for another game |
| --- | --- | --- |
| Session and transport | `jev_sc2/sc2.py` sends an allowlisted sequence of binary Protobuf requests over `ws://127.0.0.1:<port>/sc2api`; map bytes are supplied at game creation and requests are serialized. | Start/attach, observe, query capabilities, submit actions, read lifecycle/outcome, and save artifacts. The wire protocol and process ownership stay in the adapter. |
| Observation | `jev_sc2/view.py` filters player-owned and currently visible entities, preserves explicitly stale fog snapshots, masks unexplored terrain, and adds resource/capability facts and engine-queried candidates. | A small model-facing state with current facts, permitted memory, resources, capabilities, and lifecycle status. Keep hidden information and protocol objects out of the policy state. |
| Decision | `player.py` asks Jev for strategic priority, contribution, investment, and concrete orders. `jev_sc2/jev.py` uses the OpenRouter Decisions API with the Jev model allowlist by default. | `DecisionPort.ask(state, questions)` returns typed choices/probabilities plus model, latency, cost, and failure metadata. A game port supplies facts; it does not become a policy. |
| Validation | A fresh SC2 observation checks ownership, visibility, offered candidates, duplicate casters, and target freshness. The adapter may preserve an intent with an approved point-target fallback; all rejects are logged. | `validate(commands, offered, fresh) -> accepted, rejected`. Validation must be independent of model confidence and must never turn hidden state into a target. |
| Execution and outcome | Validated commands become SC2 raw unit actions. `player_result`, status, engine errors, replay saving, and supervised end-screen evidence are recorded separately. | Submit only validated commands, report engine acknowledgements/errors separately from completed effects, and expose an explicit terminal/unknown result. |
| Camera and streaming | `jev_sc2/camera.py` chooses a shot from the view and emits only a world position/reason; the main loop sends `camera_move`. OBS captures the window/display externally. | Optional presentation port: choose a viewport/frame from observations without access to gameplay command selection. A game without a camera API can use an external capture adapter. |
| Experiment loop | Commits are the policy journal; `player.py`, the view adapter, and camera reload atomically at decision boundaries. JSONL records state, questions, distributions, model, cost, latency, age, rejects, and results. | Scenario + hypothesis + bounded run + evidence artifact. Preserve the distinction between an accepted request, an observed effect, and an objective outcome. |

The portable layers should not depend on `s2clientprotocol`, SC2 unit tags,
ability IDs, map grids, game loops, replay format, or SC2 campaign screens.

## Observation boundary

The SC2 adapter is deliberately responsible for translating protocol facts into
facts Jev can use:

1. `RequestObservation` supplies the player perspective with fog enabled.
2. `RequestData` supplies catalog names and static metadata; `RequestQuery`
   supplies resource-aware available abilities.
3. The adapter excludes hidden entities and enemy orders. A snapshot is labeled
   as stale type/location memory and cannot be used as a live unit-tag target.
4. Static pathing is revealed only where the player has visibility. It is a
   terrain fact, not a precomputed route or tactical recommendation.
5. Candidate commands include the concrete SC2 ability/target facts needed for
   a choice, while the engine still checks range, cost, race, cooldown, and
   other conditions.

For a generic port, preserve the same distinction between current observation,
permitted memory, and derived facts. The adapter may calculate geometry and
legality; Jev should receive the result as a compact, explicit state rather than
raw packets or an unbounded map dump.

## Decision boundary: Jev and OpenRouter

The policy decision is intentionally narrow and typed:

- Jev chooses among the offered alternatives, including the option to keep
  existing orders or defer spending.
- OpenRouter's Decisions endpoint is the default network path to
  `typesafe/jev-1.13`; it carries the request and returns the decision. It does
  not replace Jev with a general-purpose fallback model.
- The repository also contains wire-compatible TypeSafe/OpenJev paths for local
  or alternate deployment experiments. They remain Jev-only paths and are
  recorded as a different `via` label; the architecture does not require them.
- The harness applies call budgets, timeouts, request-size splitting, and
  serialized access where the backend requires it. Failures stop or preserve
  existing orders according to the run policy; they do not silently invoke a
  scripted tactical policy.

The generic seam is therefore a decision gateway, not a game-specific prompt
builder:

```text
GamePort.observe() -> ModelState
QuestionBuilder(ModelState) -> typed questions
DecisionPort.ask(ModelState, questions) -> typed answers
CommandBuilder(ModelState, answers) -> candidate commands
GamePort.validate_and_submit(...) -> execution evidence
```

Only `QuestionBuilder` and `CommandBuilder` should need game vocabulary. The
gateway, budgets, logging, and failure semantics should not.

## Validation and transport rules

SC2 uses binary Protobuf over WebSocket rather than a text protocol. The client
keeps requests ordered and allowlists setup, observation, query, ordinary
actions, replay saving, and lifecycle operations. It does not expose debug
requests, observer slots, fog disabling, map commands, or resource overrides.
Realtime operation intentionally does not use `RequestStep`.

The important transport invariant is **observe -> decide -> fresh observe ->
validate -> submit**. Inference can make a unit, target, resource amount, or
ability stale. A successful API response only means the request was accepted;
the next observation and the run's outcome evidence determine whether the
intended effect happened. This is also the invariant a Fortnite adapter must
prove, even if its transport is HTTP, a local test server, input injection, or
another supported mechanism.

## Camera and streaming boundary

The camera director is not part of Jev's action authority. It scores visible
engagements, damage, movement, and quiet-scene rotation, then returns a framing
position. It has separate memory and emits no unit, target, or ability command.
In SC2 that position is sent as a camera-only raw action. `docs/STREAMING.md`
documents the current OBS/display arrangement, audio controls, and secret
handling.

This separation lets a future game use a spectator camera, a video crop, or no
camera control at all without changing the decision loop. Stream health and
capture configuration are run evidence/presentation concerns, not gameplay
success criteria.

## Experiment loop and evidence

Each experiment should follow this bounded sequence:

1. State a hypothesis and the smallest policy/interface change that tests it.
2. Commit the policy or adapter change so the active revision is identifiable.
3. Run a named scenario with a call/time budget and a known observation age
   limit.
4. At each decision boundary, record observation, question set, full returned
   distributions, selected answers, candidate commands, validation rejects,
   action errors, latency, cost, and outcome evidence.
5. Inspect the JSONL run and replay/artifact, then record the measured result,
   confounds, and next experiment in the journal.

Do not call an experiment successful because Jev answered, the engine accepted
an action, a unit moved once, or a stream was visible. Those are separate
measurements from completing an objective. Current SC2 evidence is sequential
and evolving-state evidence; it supports engineering lessons, not broad claims
of game-playing competence.

## SC2-specific versus portable map

| Concern | Keep in the SC2 adapter | Carry into a generic port |
| --- | --- | --- |
| Identity | Unit tags, unit types, alliance/display types, SC2 ability IDs | Stable entity identity, ownership, visibility, and capability identity |
| World | SC2 coordinates, pathing/visibility images, game loops, fog snapshots | Positions/regions only when the game exposes them, plus explicit age/visibility |
| Actions | Raw ability commands, point/tag targets, build-site and resource target rules | Typed intent, target reference, and adapter-defined legal candidate |
| Lifecycle | `create_game`, `join_game`, `player_result`, SC2 end screens, replay files | Start/stop/resume, terminal/unknown outcome, and an evidence artifact |
| Presentation | `action_raw.camera_move`, SC2 window flags, OBS display capture | Optional viewport/frame selection and external capture metadata |
| Campaign | Map packaging, mission objectives, Hyperion/research/unlock limitations | Scenario manifest and objective text, without assuming campaign persistence |
| Safety | No debug requests, no hidden units, no fog override, engine legality | No hidden state, no unvalidated command submission, no silent policy fallback |
| Research | SC2 loop age, Jev call cost/latency, replay and JSONL fields | Same metric names and evidence standard where the port can measure them |

## Path to Fortnite

This is a staged port, not a second SC2 implementation hidden behind renamed
classes:

1. **Freeze the contract.** Treat the current SC2 loop and tests as the
   reference behavior for visibility, staleness, validation, failure, logging,
   and presentation separation. Do not generalize SC2 fields prematurely.
2. **Extract the orchestration seam.** Introduce a small generic `GamePort`,
   `DecisionPort`, and optional `PresentationPort` around the existing loop.
   Keep `jev_sc2` implementing those interfaces; this step should not alter
   Jev's policy or SC2 results.
3. **Do Fortnite interface discovery before coding gameplay.** Select and
   document a supported local/test control and observation route, its player
   perspective and visibility rules, action rate/latency, lifecycle signals,
   and artifact/replay support. If no sufficiently authoritative route exists,
   stop at a fixture/mock port rather than guessing or using a human-only
   stream as ground truth.
4. **Build the adapter and fixtures.** Convert Fortnite observations into the
   generic state, expose only observed/legal candidates, validate against a
   fresh observation, and record unknown outcomes. Add deterministic fixtures
   for hidden information, stale targets, rejected actions, and terminal
   states before live spending.
5. **Port presentation independently.** Add a Fortnite viewport or external
   capture adapter that cannot submit gameplay commands. Keep stream setup and
   credentials outside the repository and outside decision logs.
6. **Re-run the experiment protocol.** Start with connectivity and validation
   probes, then a tiny Jev decision loop, then bounded gameplay experiments.
   Preserve the same cost/latency/age/reject/outcome fields so SC2 and Fortnite
   results remain comparable without pretending their mechanics are identical.

The first Fortnite deliverable is a validated port and evidence trail, not a
claim of autonomous Fortnite competence. The HOLD MERGE gate remains in force
until Nathan's card/approval is present.
