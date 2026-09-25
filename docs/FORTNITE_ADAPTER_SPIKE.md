# Fortnite adapter spike plan

Status: planning only. This is a thin-adapter sketch, not Fortnite support.

The existing harness is StarCraft II-specific. The next architecture step should
make the game loop generic before anyone adds a Fortnite implementation. The
Fortnite spike starts only after that generic contract is reviewed and landed;
it must not add Fortnite branches to the Jev policy or SC2 adapter.

## Boundary

The generic harness owns policy scheduling, request budgets, observation age,
logging, replay/evidence metadata, and terminal-result handling. A game adapter
owns transport and the translation between a game and the generic contract:

```text
GameAdapter
  connect(config) -> Session
  observe(session) -> Observation
  apply(session, Action) -> ActionResult
  status(session) -> GameStatus
  close(session) -> None
```

The contract should make these invariants explicit:

- observations carry a monotonic game tick, capture time, visibility scope,
  entities, objectives, available resources, and terminal state;
- actions are declarative intents with stable IDs, targets, and an expiration
  tick; the adapter validates ownership, visibility, freshness, and legality
  before translation;
- every action returns accepted, rejected, or unknown with a reason and the
  adapter's raw correlation ID; a successful transport call is not a successful
  in-game action;
- the adapter never invents hidden entities, routes, targets, or tactical
  priorities; and
- disconnects, stale observations, unsupported actions, and ambiguous terminal
  states remain observable to the harness rather than becoming a win or loss.

## Fortnite adapter sketch

The Fortnite adapter should be deliberately small. It translates the generic
contract at the boundary and leaves policy decisions in the shared harness.

| Generic concern | Fortnite adapter responsibility | Evidence required |
| --- | --- | --- |
| Session lifecycle | Establish and close the approved local/game bridge; report capability version and session ID | Repeatable connect, health check, and clean close |
| Observation | Map the bridge's player-visible state into tick, pose, inventory/resources, nearby entities, objectives, and terminal state | Field-by-field fixture with visibility and freshness checks |
| Movement/interactions | Translate intent and target IDs into Fortnite controls; report engine rejection separately from transport failure | Accepted and rejected action fixtures |
| Combat/use/build | Expose only capabilities proven by the bridge; preserve cooldown, ammo, inventory, and target legality as facts | Capability matrix plus negative tests |
| Replay/result | Save the bridge's replay or event trace and correlate it with harness decisions | Replay/trace can be matched to session and terminal result |

Fortnite-specific concepts such as storm/zone state, inventory slots, build
materials, and weapon cooldowns belong in an adapter-owned extension payload
until the architecture proves that they are useful across games. The shared
contract should still expose a small common vocabulary (for example,
`move`, `interact`, `use`, and `attack`) and let the adapter reject unsupported
variants explicitly.

The spike must first identify the actual Fortnite control surface and its
allowed observation scope. No protocol, endpoint, automation method, or field
is assumed by this document.

## Bakeoff gate

Run the same bounded harness scenario through the existing SC2 adapter and the
Fortnite spike adapter, using recorded fixtures where a live Fortnite session
is not yet available. The result is a comparison, not a performance claim.

The bakeoff is a prerequisite for calling the adapter viable and records:

1. connect/close and health behavior;
2. observation schema coverage, tick monotonicity, visibility boundaries, and
   maximum observation age;
3. action translation coverage, legality rejection, correlation, and result
   classification;
4. unsupported-capability behavior and failure recovery;
5. terminal-state accuracy, replay/trace linkage, and deterministic fixture
   replay; and
6. harness invariants: shared call budget, no hidden information, no policy
   fallback, and no cross-session state leakage.

The go/no-go record must include the fixture set, adapter capability matrix,
known gaps, and a comparison against SC2's contract tests. A green transport
smoke test alone is insufficient.

## Exit criteria and wording gate

The spike is complete only when the generic architecture is landed, the
Fortnite adapter passes the agreed contract tests, the bakeoff evidence is
reviewed, and a decision is recorded. Until then, repository copy must say
**Fortnite adapter spike/proposal** or **planned**, never **Fortnite support**.

If any gate fails, keep the adapter experimental, document the failing evidence,
and do not expand the shared contract to fit one Fortnite-only behavior.

## Follow-up deliverables

- generic harness architecture and adapter contract;
- Fortnite bridge capability and visibility inventory;
- fixture-backed adapter prototype with negative-path tests;
- SC2-versus-Fortnite bakeoff report; and
- explicit go/no-go decision before any support claim or production wiring.
