# Architecture: SC2 harness layers → generic game ports

> **HOLD MERGE.** This is an architecture decision note for Jev Plays, not an
> authorization to merge or to start a Fortnite integration. Nathan's card and
> review remain required. Keep credentials, stream keys and local run artifacts
> out of commits.

## Scope and current decision

The harness has one game-independent experiment loop and one StarCraft II
adapter. Jev is the decision-maker; the harness owns the facts it exposes,
mechanical legality, transport, timing, telemetry and presentation. OpenRouter's
Decisions API is the current hosted Jev path. The TypeSafe/OpenJev paths are
compatible backends for the same decision boundary, not alternate game policies.

The intended shape is:

```text
game process / game service
        │
        ▼
  GamePort transport ── raw observation, queries, actions, terminal state
        │
        ▼
  Game adapter ──────── fair snapshot + offered action affordances
        │
        ├──────────────► Jev decision (OpenRouter / compatible backend)
        │                         │
        │                         ▼
        └────────────── command validation + fresh-state recheck
                                  │
                                  ▼
                         GamePort action submission

  snapshot/events ──► camera director ──► capture/streaming surface
                    (presentation only; never an action source)
```

## Layer breakdown

### 1. Observation: raw game state to a fair decision view

`jev_sc2/sc2.py` is the SC2 transport-facing client. `jev_sc2/view.py` turns
SC2 observations, static catalog data and engine ability queries into the small
JSON-like view consumed by `player.py`. The adapter currently handles:

- visible owned, enemy and neutral entities;
- explicit stale last-known locations under fog, without treating them as live
  targets;
- player-visible terrain summaries and local geometry;
- resources, orders, health, shields, cargo, cooldowns and build progress;
- engine-offered action candidates, including resource/building checks; and
- objective context and recent outcome/action feedback supplied by the loop.

The portable contract should be a snapshot of what the player is allowed to
know, plus explicitly offered affordances. It should not require SC2 tags,
ability IDs, races, tile grids, worker terminology or a particular camera model.
A future port should be able to express, for example, agents, inventory,
interactables, zones and objectives while preserving the same guarantees:

1. hidden state is not placed in the decision view;
2. stale information is labeled and cannot silently become a live target; and
3. an affordance describes a legal candidate without pretending that submission
   has already succeeded.

### 2. Decision: Jev through OpenRouter

`player.py` implements the live policy contract:

```python
async def decide(view: dict, jev, memory: dict) -> list[dict]:
    ...
```

The policy asks Jev narrow, named questions over the fair view and returns
intent represented by offered command dictionaries. It does not call the game
socket, inspect hidden state or provide a scripted fallback policy.

`jev_sc2/jev.py` is the provider boundary. The default route is OpenRouter's
Decisions API with the Jev model allowlist. TypeSafe System One and OpenJev
(hosted or local) use the same `ask(state, questions)` shape. Provider details
belong here: credentials, model names, endpoint selection, timeout, request
splitting, single-flight behavior, call budget, cost and decision telemetry.
They must not leak into a game adapter or become a second inference model in the
game loop.

For a generic port, retain the decision contract and replace only the view
builder, command vocabulary and action validator. Do not make the common layer
depend on OpenRouter response internals; the policy needs answers, probabilities
where available, and logged request metadata.

### 3. Validation: intent to executable action

Validation is a separate trust boundary between Jev and the game. SC2's
`validate_commands_with_rejects` rechecks commands against a fresh observation
and the candidates that were offered when the decision was made. It rejects
duplicates, stale decisions, unavailable abilities, unowned units and invalid
targets. Limited attack-move or ownership remaps are explicit fallbacks and are
logged as such. An accepted request still means only that the engine accepted
the request; later observation must establish its effect.

Portable validation should preserve these concepts while letting each game
define its own authority checks:

```text
decision + offered affordances + fresh snapshot
    → submitted actions + structured rejects/fallbacks
    → engine/server result
    → observed effect (or no verified effect)
```

The common loop owns age limits, duplicate suppression, feedback recording and
the distinction between accepted, completed, rejected and unknown. The port
owns target identity, permissions, cooldown/resource checks and conversion to
native actions.

### 4. Transport: the game port

SC2 currently uses binary Protobuf over WebSocket at `/sc2api`. Its port also
owns map-byte loading, ping, create/join, observation, query, action, replay
save and the restricted request allowlist. Request/response IDs are checked and
requests are serialized so replies cannot cross wires.

The portable seam is a `GamePort`, not an SC2-shaped replacement API:

```text
connect() / close()
start_or_attach(scenario)
observe() -> RawSnapshot
capabilities(snapshot) -> NativeAffordances
submit(actions) -> NativeActionResults
terminal_state() -> TerminalState | None
save_artifact() -> Artifact | None
```

The exact method names can change during implementation. The important rule is
that the port hides protocol, authentication/session setup and native message
types from the experiment loop. A Fortnite port must not be assumed to use
WebSocket, Protobuf, a local process, a public automation API or a particular
capture path until that transport is verified and approved.

### 5. Camera and streaming: presentation side channel

`jev_sc2/camera.py` chooses a display shot from the same visible view and keeps
separate camera memory. It follows engagements, damage and moving forces but
never emits unit orders or changes policy memory. `docs/STREAMING.md` records
the current OBS/capture setup and its operational controls.

This separation is portable: a game port supplies visible snapshots/events; a
game-specific or generic director selects a region, subject or spectator view;
OBS or another capture system publishes it. Streaming must not grant the
decision model extra state, alter action timing, or be required for headless
experiments. Fortnite's spectator/camera controls therefore belong in a
presentation adapter, with their own permission and latency tests.

### 6. Experiment loop and evidence

The current loop in `jev_sc2/__main__.py` is:

1. observe through the port;
2. build a fair view and affordance set;
3. let Jev choose among the offered questions/actions;
4. re-observe, enforce the decision-age limit and validate;
5. submit valid actions through the port;
6. record engine results, rejects and the next observed effects;
7. update bounded policy memory, camera memory and run telemetry; and
8. stop on a verified result, budget/time boundary or explicit unknown state,
   then save the replay/artifact when possible.

The policy and observation adapter reload from a committed revision at a
decision boundary. The game socket remains alive and policy memory is retained;
an invalid revision leaves the previous loaded pair active. This is an
experiment feature, not a requirement that every game port support hot reload.
Every port should instead provide deterministic run identity, structured
events, latency/age data, action outcomes and an artifact or explicit reason
when no artifact is available.

## SC2-specific versus portable

| Concern | SC2-specific today | Portable contract or responsibility |
| --- | --- | --- |
| Raw transport | `sc2api.proto`, WebSocket, localhost lifecycle | `GamePort` connection/session/request boundary |
| Scenario startup | `.SC2Map` bytes, race, `create_game`/`join_game` | scenario descriptor and attach/start semantics |
| Observation | SC2 raw units, alliances, fog display types, pathing grid, catalogs | fair snapshot, visibility policy, entities and affordances |
| Action identity | ability IDs, unit tags, world-space points | opaque action intents resolved by the port |
| Legality | `RequestQuery`, owned/visible tags, SC2 action results | fresh-state authorization, target/cooldown/resource checks |
| Economy | minerals, vespene, supply, workers, buildings/upgrades | optional resources/inventory and project affordances |
| Outcomes | `player_result`, `OutcomeMonitor`, campaign objective bridge | terminal-state evidence and confidence/verification rules |
| Replay/evidence | `.SC2Replay`, JSONL run logs, SC2 status transitions | artifacts, structured telemetry and reproducible run metadata |
| Camera | SC2 world positions and combat/economic candidate labels | presentation-only shot selection from visible events |
| Streaming | OBS/macOS capture procedure | independent capture/publish integration |
| Policy | Jev questions and `player.py` memory | shared decision policy contract and provider boundary |

## Path to Fortnite

Fortnite should be a new port behind the contracts above, not a rewrite of the
SC2 adapter and not a change to Jev's authority model. The proposed sequence is:

1. **Freeze the seam.** Add small protocol/dataclass types or a test double for
   snapshots, affordances, actions, feedback and terminal evidence. Keep the
   existing SC2 path green while the names settle.
2. **Prove transport first.** Identify and approve the Fortnite session/control
   mechanism, authentication boundary and allowed automation surface. Build a
   fake port and a bounded local/instrumented smoke test before connecting Jev.
3. **Build the observation adapter.** Map only player-visible agents, world
   objects, inventory/resources, objectives, zones and timing into the common
   view. Make visibility and stale-data behavior explicit; do not infer hidden
   opponents or routes.
4. **Build affordances and validation.** Expose a small set of server/client
   actions as named candidates. Recheck identity, permissions, cooldowns,
   inventory, target visibility and observation age immediately before submit.
5. **Reuse the decision layer.** Point the same Jev/OpenRouter boundary at the
   Fortnite view. Start with narrow choices and bounded call/time budgets; no
   Fortnite-specific fallback model or hidden scripted strategy.
6. **Add presentation separately.** Implement spectator/camera framing and
   capture only after headless observation/action tests pass. Confirm the
   stream receives no facts that Jev does not receive.
7. **Run a parity experiment.** Compare fake-port and live-port traces for
   observation filtering, action rejection, latency/age handling, terminal
   evidence, replay/artifacts and secret redaction. Begin with one bounded
   arena/scenario and an explicit stop condition.

Fortnite-specific API, camera and replay details remain **TBD** until the
transport and permitted control surface are verified. That is an intentional
boundary, not a missing assumption to fill in from SC2.

## Merge gate

This note is documentation only. Keep the task **HOLD MERGE** until Nathan's
card/review is present and the implementation scope is approved. Any future
port work should include a fake-port test, a visibility/legality test, a
transport smoke test without committed credentials, and an evidence review
before it is considered ready.
