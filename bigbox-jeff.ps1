# Start jeff (GLiFormer SystemOne server) on this box, serving :8010.
# Idempotent. The harness (typesafe-sdk) talks to it unchanged via the
# openjev-latest alias. Installs CUDA torch and launches the venv exe DIRECTLY
# (uv run would re-sync CPU torch and break CUDA).
#
#   .\bigbox-jeff.ps1                       # base weights (real-time capable)
#   .\bigbox-jeff.ps1 -Model large          # heavier, more accurate
param(
  [ValidateSet('base','large')][string]$Model = 'base',
  [int]$Port = 8010,
  [string]$Key = 'devkey',
  [string]$CopycatsRoot = $env:JEV_COPYCATS_ROOT
)
$ErrorActionPreference = 'Stop'

$harness = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $CopycatsRoot) { $CopycatsRoot = Join-Path (Split-Path -Parent $harness) 'jev-copycats' }
$repo = Join-Path $CopycatsRoot 'jeff'
$modelDir = if ($Model -eq 'large') { 'gliformer-large-v1' } else { 'gliformer-base-v1' }
$hfRepo  = if ($Model -eq 'large') { 'knowledgator/gliformer-large-v1' } else { 'knowledgator/gliformer-base-v1' }

Write-Host "== jeff ($modelDir) -> serve :$Port =="

# 1) clone if missing
if (-not (Test-Path $repo)) {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git not found' }
  New-Item -ItemType Directory -Path $CopycatsRoot -Force | Out-Null
  Write-Host 'cloning logan-markewich/jeff ...'
  git clone --depth 1 https://github.com/logan-markewich/jeff.git $repo
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv not found (pip install uv)' }

Push-Location $repo
# 2) venv + deps
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  Write-Host 'uv sync ...'
  uv sync --extra dev
}

# 3) CUDA torch (critical). Do NOT run via 'uv run' after this - it re-syncs CPU torch.
uv pip install --python .venv\Scripts\python.exe --reinstall-package torch torch --index-url https://download.pytorch.org/whl/cu130 | Out-Null
$cuda = & .\.venv\Scripts\python.exe -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())" 2>&1
Write-Host $cuda
if ($cuda -notmatch 'cuda True') { Write-Warning 'CUDA not available in jeff venv - this box may lack an NVIDIA GPU/driver for torch.' }

# 4) weights
$modelPath = Join-Path $repo "models\$modelDir"
if (-not (Test-Path (Join-Path $modelPath 'config.json'))) {
  Write-Host "downloading $hfRepo ..."
  uv run hf download $hfRepo --local-dir "models/$modelDir" | Out-Null
  # uv run may have re-synced torch; re-assert CUDA just in case
  uv pip install --python .venv\Scripts\python.exe --reinstall-package torch torch --index-url https://download.pytorch.org/whl/cu130 | Out-Null
}

# 5) (re)start - run the exe directly, not 'uv run'
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Write-Host "port $Port busy (pid $($existing.OwningProcess)) - leaving it, assuming jeff already up"
} else {
  $env:JEFF_API_KEYS = $Key
  $env:JEFF_MODEL = "models/$modelDir"
  $env:JEFF_MODEL_NAME = $modelDir
  $env:JEFF_DEVICE = 'cuda'
  $env:JEFF_PORT = "$Port"
  $env:JEFF_HOST = '0.0.0.0'          # reachable from MSI over the LAN
  $env:JEFF_WARMUP = '0'
  $env:JEFF_ISOLATE = 'none'          # single encoder pass (faster)
  $env:JEFF_MODEL_ALIASES = 'jev-latest,jev,openjev-latest,openjev,typesafe/jev-1.13'
  $logOut = Join-Path $repo 'jeff.bigbox.out.log'
  $logErr = Join-Path $repo 'jeff.bigbox.err.log'
  $proc = Start-Process -FilePath '.\.venv\Scripts\jeff.exe' -WorkingDirectory $repo -WindowStyle Minimized -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru
  Write-Host "started jeff pid=$($proc.Id) (logs: $logOut)"
}

# 6) health (model load takes ~30-60s)
# NOTE: do NOT let a failed curl abort the loop. With $ErrorActionPreference='Stop',
# curl.exe writing to stderr raises a terminating NativeCommandError on PS 5.1, so the
# very first not-yet-listening probe (5s after launch) used to kill the script. Relax it
# for the probe, then restore.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 5
  $h = curl.exe -sS -m 5 "http://127.0.0.1:$Port/healthz" 2>$null
  if ($h) { Write-Host "READY (~$(($i+1)*5)s) $h"; $ready = $true; break }
}
$ErrorActionPreference = $prevEap
if (-not $ready) {
  Write-Warning "not ready after 150s - tail of the error/output logs follows"
  if (Test-Path $logErr) { Get-Content $logErr -Tail 40 | ForEach-Object { Write-Host "  [err] $_" } }
  if (Test-Path $logOut) { Get-Content $logOut -Tail 20 | ForEach-Object { Write-Host "  [out] $_" } }
  Pop-Location; exit 1
}

# 7) a tiny decide through the wire format
$body = '{"state":"A marine squad is near the enemy base.","questions":{"a":{"type":"choice","instructions":"Pick the next action.","criteria":{"attack":"Attack-move the squad forward.","hold":"Hold position."}}}}'
$tmp = Join-Path $env:TEMP 'bigbox-jeff-smoke.json'
Set-Content -Path $tmp -Value $body -Encoding ASCII
$prevEap2 = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$sw = [Diagnostics.Stopwatch]::StartNew()
$out = curl.exe -sS -m 60 -X POST "http://127.0.0.1:$Port/v1/systemone" -H "Content-Type: application/json" -H "Authorization: Bearer $Key" --data-binary "@$tmp" 2>&1
$sw.Stop()
$ErrorActionPreference = $prevEap2
Write-Host ("decide: " + ($out -join ''))
Write-Host ("decide latency: " + [math]::Round($sw.Elapsed.TotalSeconds,2) + "s")
Pop-Location
Write-Host "jeff up on :$Port - point the MSI harness at http://<this-box>:$Port with key '$Key'"
