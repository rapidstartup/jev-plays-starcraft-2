# Strict preflight LD-LJ-BIG: LocalJev on the big box via the real harness decide path.
$ErrorActionPreference = 'Continue'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root
. (Join-Path $root 'scripts\opencode\env-LD-LJ-BIG.ps1')
$h = curl.exe -sS -m 10 'http://192.168.0.10:8080/ready'
Write-Output ("ready=" + $h)
if ($h -notmatch 'ready') { Write-Output 'PREFLIGHT_RED localjev not ready'; exit 1 }
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\opencode\preflight_decide.py')
if ($LASTEXITCODE -ne 0) { Write-Output 'PREFLIGHT_RED decide'; exit 1 }
Write-Output 'PREFLIGHT_GREEN LD-LJ-BIG'
exit 0
