$ErrorActionPreference = 'Stop'
$root = 'C:\Users\natha\code\jev-plays-starcraft-2'
Set-Location $root
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $root ("runs\guide-traynor01-" + $stamp)
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$objective = 'Destroy the Logistics Headquarters. Raynor must survive.'
$jevModel = if ($env:JEV_MODEL) { $env:JEV_MODEL } else { 'typesafe/jev-1.13' }
$timeoutMs = if ($env:JEV_TIMEOUT_MS) { [int]$env:JEV_TIMEOUT_MS } else { 5000 }
$gitHead = $null
try { $gitHead = (git rev-parse HEAD 2>$null) } catch {}
$control = [ordered]@{
  stamp = ("guide-traynor01-" + $stamp)
  git_head = $gitHead
  map = 'maps/traynor01.SC2Map'
  objective = $objective
  seconds = 0
  max_calls = 0
  wall_status_seconds = 3600
  exit_policy = 'win_or_death_only'
  retry_stalls = $true
  close_sc2 = $true
  guide_expected = $true
  jev_model = $jevModel
  jev_timeout_ms = $timeoutMs
  # State presented to the model: 'compact' (small SystemOne projection) vs
  # 'full' (legacy rich view). Recorded so the bench can tell the two eras apart.
  state_mode = $(if ((($env:JEV_COMPACT_STATE) -ne '0') -and (($env:JEV_COMPACT_STATE) -ne 'false')) { 'compact' } else { 'full' })
  state_budget_chars = $(if ($env:JEV_CONTEXT_BUDGET_CHARS) { $env:JEV_CONTEXT_BUDGET_CHARS } else { '3000' })
  openrouter_key_present = [bool]($env:OPENROUTER_API_KEY)
  launched_at = (Get-Date).ToUniversalTime().ToString('o')
  note = 'Launcher-side mirror; harness also writes control.json under runs/<utc-stamp>/'
}
($control | ConvertTo-Json -Depth 4) | Set-Content -Path (Join-Path $runDir 'control.json') -Encoding UTF8
$launch = @"
Set-Location '$root'
# Preserve parent env (matrix combos); defaults only when unset.
if (-not `$env:GUIDE_ENABLED) { `$env:GUIDE_ENABLED='1' }
# Preserve JEV_VIA from parent env (typesafe|openrouter); do not overwrite
if (-not `$env:JEV_VIA) { `$env:JEV_VIA='typesafe' }
if (-not `$env:GUIDE_MODEL) { `$env:GUIDE_MODEL='google/gemini-2.5-flash' }
if (-not `$env:GUIDE_BACKEND) { `$env:GUIDE_BACKEND='openrouter' }
if (-not `$env:GUIDE_OLLAMA_MODEL) { `$env:GUIDE_OLLAMA_MODEL='gemma4:e2b' }
if (-not `$env:GUIDE_OLLAMA_BASE_URL) { `$env:GUIDE_OLLAMA_BASE_URL='http://127.0.0.1:11434' }
if (-not `$env:GUIDE_EVERY_N_TICKS) { `$env:GUIDE_EVERY_N_TICKS='8' }
`$env:JEV_MODEL='$jevModel'
if (-not `$env:JEV_TIMEOUT_MS) { `$env:JEV_TIMEOUT_MS='5000' }
& '$root\.venv\Scripts\python.exe' -m jev_sc2 --map maps/traynor01.SC2Map --follow-camera --max-calls 0 --seconds 1800 --wall-status-seconds 3600 --retry-stalls --objective 'Destroy the Logistics Headquarters. Raynor must survive.' --close-sc2 *>&1 | Tee-Object -FilePath '$runDir\run.log'
"@
Set-Content -Path (Join-Path $runDir 'launch.ps1') -Value $launch -Encoding UTF8
$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $runDir 'launch.ps1')) -WorkingDirectory $root -WindowStyle Hidden -PassThru
Set-Content -Path (Join-Path $runDir 'pid.txt') -Value $proc.Id
Write-Output ("STARTED runDir=" + $runDir)
Write-Output ("STARTED pid=" + $proc.Id)
Start-Sleep -Seconds 12
Write-Output "===PORT_AFTER==="
$port = Get-NetTCPConnection -LocalPort 5001 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($port) { Write-Output ("PORT5001 state=" + $port.State + " pid=" + $port.OwningProcess) } else { Write-Output "PORT5001 still closed" }
Write-Output "===SC2_AFTER==="
Get-Process -Name SC2* -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ($_.ProcessName + " pid=" + $_.Id) }
if (-not (Get-Process -Name SC2* -ErrorAction SilentlyContinue)) { Write-Output "no SC2 yet" }
Write-Output "===LOG_HEAD==="
if (Test-Path (Join-Path $runDir 'run.log')) {
  Get-Content (Join-Path $runDir 'run.log') -TotalCount 40
} else {
  Write-Output "run.log not yet"
}
Write-Output "===PROC==="
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq $proc.Id -or ($_.CommandLine -and $_.CommandLine -match 'traynor01|jev_sc2') } | ForEach-Object {
  $c = if ($_.CommandLine) { $_.CommandLine.Substring(0, [Math]::Min(200, $_.CommandLine.Length)) } else { '' }
  Write-Output ("pid=" + $_.ProcessId + " name=" + $_.Name + " " + $c)
}
