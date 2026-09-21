# Strict preflight LD-OR (OpenRouter). Single serial harness decide call.
$ErrorActionPreference = 'Continue'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root
. (Join-Path $root 'scripts\opencode\env-LD-OR.ps1')
if (-not $env:OPENROUTER_API_KEY -or -not $env:JEV_VIA) { Write-Output 'PREFLIGHT_RED env'; exit 1 }

& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\opencode\preflight_decide.py')
if ($LASTEXITCODE -ne 0) { Write-Output 'PREFLIGHT_RED decide'; exit 1 }
Write-Output 'PREFLIGHT_GREEN LD-OR'
exit 0
