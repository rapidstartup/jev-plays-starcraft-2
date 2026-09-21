# Helper: dot-source an env script then run a probe in the SAME session.
# Usage: .\scripts\opencode\run-probe.ps1 <EnvId> <ProbeFile> [extra probe args...]
#   .\scripts\opencode\run-probe.ps1 LD-LJ probe_first_call.py 300000
param([string]$EnvId = 'LD-LJ', [string]$Probe = 'probe_first_call.py')
$ErrorActionPreference = 'Stop'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root
. (Join-Path $root ("scripts\opencode\env-" + $EnvId + ".ps1"))
$probeArgs = @((Join-Path $root ("scripts\opencode\" + $Probe)))
if ($args.Count -gt 0) { $probeArgs += $args }
& (Join-Path $root '.venv\Scripts\python.exe') @probeArgs
exit $LASTEXITCODE
