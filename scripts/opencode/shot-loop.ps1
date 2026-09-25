# Periodically screenshot the StarCraft II window (game-only) during a run.
# Usage: .\shot-loop.ps1 -OutDir <dir> [-EverySec 10] [-MaxSec 1800]
param(
  [Parameter(Mandatory)][string]$OutDir,
  [int]$EverySec = 10,
  [int]$MaxSec = 1800
)
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$cap = Join-Path $PSScriptRoot 'capture-game-window.ps1'
$start = Get-Date
$i = 0
while (((Get-Date) - $start).TotalSeconds -lt $MaxSec) {
  $sc2 = Get-Process SC2_x64 -ErrorAction SilentlyContinue
  if (-not $sc2) { Start-Sleep -Seconds 3; continue }
  $i++
  $out = Join-Path $OutDir ("shot-{0:D4}.png" -f $i)
  & $cap -Out $out 2>$null | Out-Null
  Start-Sleep -Seconds $EverySec
}
Write-Output "SHOT_LOOP_DONE shots=$i"
