# Close stale controller servers + widget windows, boot a fresh one.
# Idempotent. Called by every run-*.ps1 before SC2 boot.
param([int]$Port = 8765)
$ErrorActionPreference = 'Continue'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root

# 1) Kill stale widget servers
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'controller_widget_server\.py' }
foreach ($p in $procs) {
  try { Stop-Process -Id $p.ProcessId -Force; Write-Output ("CTRL killed server pid=" + $p.ProcessId) }
  catch { Write-Output ("CTRL kill-fail pid=" + $p.ProcessId) }
}
# 2) Kill stale Edge/Chrome --app widget windows for this port
$apps = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'msedge|chrome') -and ($_.CommandLine -match ([string]$Port)) }
foreach ($p in $apps) {
  try { Stop-Process -Id $p.ProcessId -Force; Write-Output ("CTRL killed widget browser pid=" + $p.ProcessId) }
  catch { Write-Output ("CTRL browser kill-fail pid=" + $p.ProcessId) }
}
Start-Sleep -Seconds 2

# 3) Boot fresh server
$py = Join-Path $root '.venv\Scripts\python.exe'
Start-Process -FilePath $py -ArgumentList @((Join-Path $root 'scripts\controller_widget_server.py'), '--run', 'latest', '--port', "$Port") -WorkingDirectory $root -WindowStyle Minimized
Start-Sleep -Seconds 1
$listening = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listening) { Write-Output ("CTRL server listening port=" + $Port) }
else { Write-Output ("CTRL_WARN server not yet on port=" + $Port) }

# 4) Open widget window beside SC2
& (Join-Path $root 'scripts\open-controller-widget.ps1') -Port $Port
Write-Output 'CTRL fresh widget booted'
