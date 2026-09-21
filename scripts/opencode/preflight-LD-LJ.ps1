# Strict preflight LD-LJ. Single serial call. Exit 0 only on non-null choice.
$ErrorActionPreference = 'Continue'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root
. (Join-Path $root 'scripts\opencode\env-LD-LJ.ps1')
if (-not $env:OPENJEV_API_KEY -or -not $env:JEV_VIA) { Write-Output 'PREFLIGHT_RED env'; exit 1 }

$base = 'http://127.0.0.1:8080'
Write-Output '=== health ==='
$h = curl.exe -sS -m 10 ($base + '/health')
Write-Output ("health=" + $h)
if ($h -notmatch 'ok') { Write-Output 'PREFLIGHT_RED health'; exit 1 }

Write-Output '=== decide via harness path (single call) ==='
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\opencode\preflight_decide.py')
if ($LASTEXITCODE -ne 0) { Write-Output 'PREFLIGHT_RED decide'; exit 1 }
Write-Output 'PREFLIGHT_GREEN LD-LJ'
exit 0
