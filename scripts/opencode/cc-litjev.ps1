# CC-ALT LitJev smoke: same /v1/systemone schema on off-the-shelf Qwen. Rerunnable.
# Default model Qwen3-0.6B fits 8GB; swap --model for bigger GPUs (remote).
param([string]$Model = 'Qwen/Qwen3-0.6B')
$ErrorActionPreference = 'Stop'
$harnessRoot = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$cc = if ($env:JEV_COPYCATS_ROOT) { $env:JEV_COPYCATS_ROOT } else { Join-Path (Split-Path -Parent $harnessRoot) 'jev-copycats' }
$repo = Join-Path $cc 'litjev'
Set-Location $repo
uv sync --locked
$busy = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $busy) {
  Start-Process -FilePath 'uv' -ArgumentList @('run','--locked','litjev','--model',$Model) -WorkingDirectory $repo -WindowStyle Minimized
  Start-Sleep -Seconds 120
}
curl.exe -sS -m 400 --fail-with-body http://127.0.0.1:8000/v1/systemone -H 'Content-Type: application/json' --data-binary '@examples/request.json' -o "$env:TEMP\cc-litjev-out.json" -w 'systemone http=%{http_code} time=%{time_total}s'
Write-Output 'CC-LITJEV smoke done (server :8000)'
