# Run LD-OR: preflight -> fresh controller -> jev-launch-traynor. Refuses SC2 boot on red.
$ErrorActionPreference = 'Stop'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root
. (Join-Path $root 'scripts\opencode\env-LD-OR.ps1')
& (Join-Path $root 'scripts\opencode\preflight-LD-OR.ps1')
if ($LASTEXITCODE -ne 0) { Write-Output 'RUN_ABORT LD-OR preflight red; SC2 not booted'; exit 1 }
& (Join-Path $root 'scripts\opencode\restart-controller.ps1')
& (Join-Path $root 'jev-launch-traynor.ps1')
