# OpenCode handover — Jev Plays harness runs + env fixes

**Date:** 21 Sep 2026 (Australia/Perth)  
**From:** RapidStartup Gaming Dev (Nathan seat)  
**To:** OpenCode (own env scripts, smoke, Liberation Day / copycat runs)  
**Return results to:** Gaming Dev → publish measured rows on https://jevbench.dev  

Gaming Dev keeps: site/leaderboard copy, Track 3 X drafts, architecture narrative.  
OpenCode owns: machine env, preflight, cold-start scripts, live SC2/copycat runs, raw run artifacts.

---

## 0) Success contract

For each **bench line** below:

1. Create (or update) a **named env/launch script** that is idempotent.
2. **Preflight** before SC2 (or before a copycat smoke): prove decide path returns valid `answers` with **non-null** choice fields.
3. Run the bench line to the success bar for that line.
4. Hand Gaming Dev a **result packet** (schema §6) — do not invent scores; do not claim official BH % as ours.

**Stop conditions:** 1 verified Liberation Day win per decision backend, or a clear blocker filed in the result packet.

---

## 1) Machines & paths (authoritative)

| Role | Where | Notes |
|---|---|---|
| SC2 + harness host | Nathan MSI | `C:\Users\natha\code\jev-plays-starcraft-2` |
| Local bridges | MSI | `C:\Users\natha\code\jev-copycats\localjev` (:8080), `semif-bridge` (:8081) |
| Heavy local models | CleanLeads `192.168.0.10` | Ollama `:11434`; **dgemma-small SystemOne** `:8011` |
| Guide LLM | OpenRouter | Gemini Flash `google/gemini-2.5-flash` |
| Public site | jevbench.dev | Gaming Dev updates from your result packets |

MSI machineId (Grok Bot local-exec): `231e4b34-3308-4f91-ba6f-6c3e4328f6a9`.

---

## 2) Hard constraints (do not regress)

1. **dgemma-small is single-sequence.** Concurrent `/v1/systemone` POSTs cross replies (proven with nonce → other client’s answer).  
   - Shim on `.10` single-flights + retries.  
   - Harness **must** also single-flight: `asyncio.Lock` on `_ask_systemone`, **no** `asyncio.gather` of parallel `jev.ask` batches. Already patched in `jev_sc2/jev.py` + `player.py` on MSI — keep it.  
   - Never parallel preflight + harness decide against `:8011`.
2. **`DG_NGL=0` is intentional** (safe CPU tensors). Do **not** “fix” by raising DG_NGL unless `.10` owner asks.
3. **Liberation Day controls (fixed):** Gemini Flash guide · `memory_mode=none` (cold) · HQ-win detector (`ObjectiveWinEvidence`) · exit on win/death only · do not leave/rejoin on Help/Tutorials (await human dismiss).
4. **Never print API keys** in scripts committed to forks / chat dumps.
5. **Do not grind more TypeSafe LD wins** — baseline is locked (4+ verified). Rotate backends.
6. **Official / BH numbers** → mark `source=official` + URL; never as RapidStartup re-runs.

---

## 3) Bench lines — Liberation Day matrix (Track 1)

Map: `maps/traynor01.SC2Map` (Liberation Day). Objective: destroy Logistics HQ; Raynor survives.

| ID | Bench line | Wire | Env sketch | Ready? | Success bar |
|---|---|---|---|---|---|
| **LD-TS** | TypeSafe Jev 1.13 | `JEV_VIA=typesafe` · model `typesafe/jev-1.13` | Typesafe key in `.env` | **DONE** — 4+ verified wins | Stop; do not re-run for “more wins” |
| **LD-OR** | OpenRouter Jev | `JEV_VIA=openrouter` | `OPENROUTER_API_KEY` | Ready | 1 verified HQ win |
| **LD-LJ** | LocalJev → Ollama | `JEV_VIA=openjev` · `OPENJEV_BASE_URL=http://127.0.0.1:8080` · upstream Ollama on `.10` | LocalJev Bearer; prefer fast model (e.g. qwen3.5:4b); **Ollama-native `/api/chat`** not hung `json_schema` | Flaky JSON / 502 historically | 1 verified HQ win |
| **LD-DG** | dgemma-small SystemOne | `JEV_VIA=openjev` · `OPENJEV_BASE_URL=http://192.168.0.10:8011` · `JEV_TIMEOUT_MS≥180000` | No parallel POSTs; strict preflight: non-null `answers.*.choice` | Shim green when uncontended; red under concurrency | 1 verified HQ win |
| **LD-SF** | SemIf-bridge | `JEV_VIA=openjev` · `OPENJEV_BASE_URL=http://127.0.0.1:8081` | SemIf upstream model via Ollama/WebGPU path | Parked — slow / invalid JSON | 1 win **or** blocker “generation≠SemIf logit-read” |
| **LD-DJ** | djev hosted / djev-spark / dgemma-small alt | Hosted `djev.dev` **or** `.10:8011` | Account key / local shim | After LD-DG | 1 verified HQ win |
| **LD-LIST** | Von / Verdict / Nimble / etc. | TBD adapters | — | List-only until SystemOne adapter | Official-cite row only |

**Launcher notes (MSI):**

- Prefer `jev-launch-traynor.ps1` (does not force TypeSafe).  
- Cold-start helpers: `_coldstart-localjev.ps1`, `scripts\preflight-decide-path.ps1` — rewrite per backend; **curl** hard timeouts, not hanging `Invoke-WebRequest`.  
- Controller widget: `scripts\open-controller-widget.ps1` (for screengrabs).  
- Soft 502 backoff exists in `__main__.py` (`soft_decision_failure`, threshold 25) — keep for flaky local SystemOne; still fix root causes.

**Verified win evidence required:** HQ health→destroyed + Raynor alive + harness `ObjectiveWinEvidence` / mission UI — not bare SC2 API `Victory`.

---

## 4) Bench lines — copycat / SystemOne catalog (Track 2)

Install/smoke or official-cite. Leaderboard sourcing rule: `source=ours` only if independently smoked/serviced.

### P0 games-first / control (top 8)

| ID | System | Action for OpenCode | Success bar |
|---|---|---|---|
| **CC-JEV** | TypeSafe Jev 1.13 | Already control | Keep as control row |
| **CC-NANO** | NanoJev | Install/smoke maze+Snake if feasible | Smoke + latency or official cite |
| **CC-S1O** | system-one-open | Smoke Doom/agent demos path | Smoke or official |
| **CC-JEVLIKE** | jevlike | Vision Doom/chess checkpoints | Smoke or official |
| **CC-SEMIF** | SemIf / OpenJev (TheoLeeCJ) | Local/WebGPU smoke ≠ our SemIf-bridge LD numbers | Do not equate bridge to BH SemIf |
| **CC-DJEV** | djev (Maisa) | Hosted API smoke | Latency/correctness sample |
| **CC-OJ** | OpenJev (razorback16/Codiv) | If reachable | Smoke or official |
| **CC-S1** | system-one (Sean Goedecke) | Any-LLM SystemOne | Smoke or official |

### Also list

| ID | System | Notes |
|---|---|---|
| **CC-LAYA** | Laya | Install if GPU allows |
| **CC-LOCALJEV** | LocalJev (githubnext) | Same stack as LD-LJ |
| **CC-JEFF** | jeff (logan-markewich) | |
| **CC-LAYA-MLX** | Laya-MLX | Official-cite only (Apple Silicon) |
| **CC-ALT** | open-alternative-jev, openjev-sglang, mini-jev, Nimble 9B, … | Official-cite until adapter |

Catalog source: `deliverables/2026-09-20-jev-copycats-field-catalog.md` · plan: `deliverables/jev-copycat-bench/PLAN.md`.

---

## 5) Env script checklist (what OpenCode creates)

For each active LD line, ship under MSI `jev-plays-starcraft-2\scripts\opencode\` (suggested):

```
env-<line-id>.ps1          # sets .env keys for that backend only
preflight-<line-id>.ps1    # health + SystemOne tiny + (optional) multi-q; exit 0 only if non-null choices
run-<line-id>.ps1          # preflight → jev-launch-traynor → optional widget
```

**Strict preflight green (SystemOne):**

- `GET …/health` OK  
- `POST …/v1/systemone` tiny choice → HTTP 200 **and** `answers.q1.choice` is a non-null non-empty string  
- Prefer wall time ≳ a few seconds on dgemma (sub-50ms identical responses may be cache — still OK if choice non-null, but prefer a second call)

**Refuse SC2 boot on red.**

---

## 6) Result packet → Gaming Dev (for jevbench.dev)

Return one markdown or JSON blob per finished attempt (win, loss, or blocker):

```json
{
  "bench_id": "LD-DG",
  "run_id": "20260921T073335…",
  "map": "traynor01 / Liberation Day",
  "status": "win | loss | incomplete | blocked",
  "jev_via": "openjev",
  "jev_model": "openjev-latest",
  "openjev_base_url": "192.168.0.10:8011",
  "guide_model": "google/gemini-2.5-flash",
  "memory_mode": "none",
  "calls": 0,
  "wall_seconds": null,
  "hq_win_evidence": true,
  "source": "ours",
  "blocker": null,
  "artifact_paths": ["runs/…/events.jsonl", "runs/…/game.SC2Replay", "controller stills"],
  "notes": "single-flight enforced; Help dismissed once"
}
```

Gaming Dev will translate into jevbench rows / details drawer. **Do not** edit the public site yourself unless Nathan says so.

---

## 7) Current state snapshot (21 Sep ~15:40 PT)

- TypeSafe LD baseline **locked** (4+ wins).  
- LocalJev / SemIf LD: **0** verified wins; JSON/502 history.  
- dgemma `:8011`: root cause = **concurrency cross-talk**; shim + harness single-flight required. Serial smokes still intermittently 502 after shim’s 3 retries — if that continues, paste `attempt=` lines from `docker logs dgemma-small` to `.10` owner.  
- Gaming Dev **removed** automated 30m / green-watch routines — OpenCode owns the run loop.  
- Help/Tutorials overlay still needs **human close** when it appears (do not leave/rejoin loop).

---

## 8) Suggested OpenCode order of work

1. **LD-DG** — prove serial preflight green → one Liberation Day win with single-flight harness.  
2. **LD-OR** — OpenRouter Jev one win (clean A/B vs TypeSafe).  
3. **LD-LJ** — LocalJev with fast Ollama model + native `/api/chat` path.  
4. Copycat P0 smokes (**CC-***) for site rows (`source=ours` or official).  
5. Park SemIf-bridge full LD until bridge quality matches SemIf claim.

---

## 9) Contacts

- Nathan — MSI console, Battle.net, Help dismiss, `.10` docker when needed.  
- RapidStartup Delivery — historically stood up `dgemma-small` on `.10`.  
- RapidStartup Gaming Dev — receives result packets → jevbench.dev.  
- RapidStartup Gaming Launch — X drafts only (not runs).

---

*End of handover. Update this file when a bench line flips DONE or a new backend joins the matrix.*
