# CC-NANO smoke: NanoJev 0.6B serve + maze/Snake evals. Rerunnable; idempotent.
# Prereqs: uv, NVIDIA GPU (CUDA), ~4GB disk (venv + 2.4GB checkpoint).
# Serves on :8771 (NOT :8765 — that is the SC2 controller widget).
$ErrorActionPreference = 'Stop'
$harnessRoot = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$cc = if ($env:JEV_COPYCATS_ROOT) { $env:JEV_COPYCATS_ROOT } else { Join-Path (Split-Path -Parent $harnessRoot) 'jev-copycats' }
$repo = Join-Path $cc 'nanojev'
Set-Location $repo
if (-not (Test-Path .\.venv-nano\Scripts\python.exe)) {
  uv venv --python 3.12 .venv-nano
  uv pip install --python .venv-nano/Scripts/python.exe -r requirements-toy.txt
  .\.venv-nano\Scripts\python.exe -m pip install --force-reinstall --no-deps --index-url https://download.pytorch.org/whl/cu130 'torch==2.14.0'
}
$py = (Join-Path $repo '.venv-nano\Scripts\python.exe')
& $py -c "import torch; assert torch.cuda.is_available(), 'CUDA torch missing'"
if (-not (Test-Path .\checkpoints\NanoJev\best.safetensors)) {
  & $py -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='C-Tianyu/NanoJev', local_dir='checkpoints/NanoJev', allow_patterns=['best.safetensors','config.json','tokenizer/*','backbone_config/*'])"
}
$busy = Get-NetTCPConnection -LocalPort 8771 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $busy) {
  Start-Process -FilePath $py -ArgumentList @('serve_decisions.py','--checkpoint-dir','../checkpoints/NanoJev','--web-root','../web','--port','8771','--precision','bf16') -WorkingDirectory (Join-Path $repo 'scripts') -WindowStyle Minimized
  Start-Sleep -Seconds 60
}
curl.exe -sS -m 15 http://127.0.0.1:8771/api/health
$body = '{"states": [{"id": "smoke", "state": "The room is 29 degrees, the target is 24 degrees.", "questions": {"action": {"type": "choice", "instructions": "Choose the action that most directly lowers the room temperature.", "criteria": {"cool": "Turn on air conditioning", "light": "Turn on the lights", "wait": "Keep the current settings"}}}}]}'
[IO.File]::WriteAllText("$env:TEMP\cc-nano.json", $body)
curl.exe -sS -m 120 -X POST 'http://127.0.0.1:8771/api/evaluate' -H 'Content-Type: application/json' --data-binary "@$env:TEMP\cc-nano.json" -o "$env:TEMP\cc-nano-out.json" -w 'evaluate http=%{http_code} time=%{time_total}s'
Set-Location (Join-Path $repo 'scripts')
& $py evaluate_composed_maze.py --episodes ../results/rollout_pilot_episodes.jsonl --engine checkpoint --checkpoint ../checkpoints/NanoJev --output ../results/msi-maze-checkpoint.json --audit-every 8
& $py evaluate_composed_snake.py --episodes ../results/arcade_snake_cohort.jsonl --engine checkpoint --checkpoint ../checkpoints/NanoJev --output ../results/msi-snake-checkpoint.json --max-steps 256
Write-Output 'CC-NANO smoke done (service :8771, maze + snake evals in results/msi-*.json)'
