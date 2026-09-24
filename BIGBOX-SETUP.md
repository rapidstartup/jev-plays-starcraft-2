# Big-box (192.168.0.10) setup for the remaining bench lines

This box is the NVIDIA 24GB server. It already has Ollama on `:11434` with
`qwen3.5:4b` (fast) and `gemma4:26b` loaded. The two bench lines that MSI cannot
run at game speed - **LocalJev** and **jeff** - start here. After they are up,
the MSI harness (StarCraft) points at them over the LAN and I run the Liberation
Day attempts from MSI.

## You run these two (on this box)

```powershell
git -C <harness-checkout> pull            # get these scripts
cd <harness-checkout>

# 1) LocalJev  -> OpenJev wire over Ollama qwen3.5:4b  (serves :8080)
.\bigbox-localjev.ps1

# 2) jeff (GLiFormer) SystemOne server                    (serves :8010)
.\bigbox-jeff.ps1
```

Each script is idempotent: safe to re-run. Each prints `READY ...` when healthy.

## What they set up

**`bigbox-localjev.ps1`** - clones `githubnext/localjev` if missing, points it at
this box's Ollama OpenAI-compatible endpoint (`http://127.0.0.1:11434/v1`,
model `qwen3.5:4b`) instead of the Mac's oMLX, sets `LOCALJEV_HOST=0.0.0.0` so the
MSI harness can reach it, and serves `POST /v1/systemone` on `:8080`. Bearer is
`local` (or set your own with `-Key`).

**`bigbox-jeff.ps1`** - clones `logan-markewich/jeff`, builds a uv venv, installs
the **CUDA** torch (the important bit: `uv sync` leaves CPU torch, and `uv run`
re-syncs it back to CPU - so we install `+cu130` and launch the venv exe directly),
downloads the GLiFormer weights, and serves `/v1/systemone` on `:8010` with the
`openjev-latest` alias so the harness speaks to it unchanged. Defaults to the
`base` weights (real-time capable); pass `-Model large` for the more accurate
but heavier model.

## After both are READY (tell me, then I do the rest)

From MSI I run one Liberation Day attempt per backend. The harness env is the only
thing that changes:

- LocalJev: `JEV_VIA=openjev`, `OPENJEV_BASE_URL=http://192.168.0.10:8080`,
  `OPENJEV_API_KEY=local`, `JEV_MODEL=openjev-latest`
- jeff:     `JEV_VIA=openjev`, `OPENJEV_BASE_URL=http://192.168.0.10:8010`,
  `OPENJEV_API_KEY=devkey`, `JEV_MODEL=openjev-latest`

## Requirements on this box

- **Bun** (for LocalJev) - `bun --version` should be >= 1.2. If missing: install
  Bun, or skip LocalJev and just run jeff.
- **uv** (for jeff) - `uv --version`. If missing: `pip install uv`.
- **Ollama** on `:11434` with `qwen3.5:4b` (already present).

## Troubleshooting

- **LocalJev prints READY but a decide fails** - the upstream key/Ollama model is
  wrong. Check `curl http://127.0.0.1:11434/v1/models` and the two `*_UPSTREAM*`
  values in the localjev `.env`. The default upstream key is a placeholder; with
  local Ollama the key can be any non-empty string.
- **jeff prints "Attempting to deserialize on a CUDA device but
  torch.cuda.is_available() is False"** - torch got reverted to CPU. Re-run
  `bigbox-jeff.ps1`; it reinstalls `+cu130` and starts the exe directly (it never
  uses `uv run`, which would re-sync CPU torch).
- **Port 8080/8010 already in use** - pass `-Port` to change it, and tell me the
  new port so I can point the harness at it.
