# REMOTE-BOX TASK LIST (big-GPU machine: Minecraft, .env.local keys, 24GB docker)
# Pull first: git fetch; git checkout main; git pull --ff-only
# Copycats live OUTSIDE the repo: run scripts/opencode/cc-clone.ps1 to create
# <harness>\..\jev-copycats (or set $env:JEV_COPYCATS_ROOT first).
# Secrets (.env, .env.local) are NEVER in git — recreate by hand on the box.
#
# 1) LD-DJ (djev): .env.local holds the djev key. Probe the hosted endpoint
#    (confirm path from djev docs) with Bearer key + tiny q1 body (shape: see
#    scripts/opencode/probe_game_payload.py). NOTE: jev_sc2/jev.py has NO djev
#    via — if djev speaks SystemOne, add a JEV_VIA=djev mapping modelled on
#    env-LD-DG.ps1, else file an adapter blocker.
# 2) CC-DJEV: same key, hosted latency/correctness sample.
# 3) CC-SEMIF (real SemIf TheoLeeCJ): jev-copycats\semif needs Python 3.10+,
#    CUDA + GPU holding 4B BF16. `pip install -e .[test]`, then semif-score
#    --mode direct --model Qwen/Qwen3.5-4B --input examples/decisions.jsonl.
# 4) CC-OJ (razorback16/openjev): needs 24GB VRAM docker:
#      git clone https://github.com/razorback16/openjev && cd openjev && docker compose up -d
#    (~18GB weights on first start), then curl localhost:8080/v1/models + tiny decide.
# 5) CC-MC (rmalde/minecraft-agent): THE Minecraft line. Needs Minecraft Java 1.16.5
#    server + Mineflayer (npm install) + JEV via OpenRouter (typesafe/jev-1.13).
#    NOTE: their relay reads the key from Google Secret Manager and IGNORES
#    OPENROUTER_API_KEY env — either configure GSM/app-default creds or patch
#    models.mjs to accept env. Then ./start-server.sh + node nether-agent.mjs per README.
#    Widget for screengrabs: scripts/opencode/restart-controller.ps1 (game-agnostic,
#    serves runs/); tile with layout-screengrab.ps1 -GameTitle 'Minecraft*'.
# 6) LJ speedup (optional): LocalJev :8080 runs gemma4:26b (~100s+/call game-size
#    on MSI's Ollama box). If this GPU is faster, point a LocalJev checkout at it
#    and compare first-call latency via scripts/opencode/run-probe.ps1 LD-LJ
#    probe_first_call.py 300000.
# 7) Re-run any MSI kit here: scripts/opencode/{env,preflight,run}-LD-*.ps1
#    ($env:JEV_HARNESS_ROOT override if the checkout path differs).
