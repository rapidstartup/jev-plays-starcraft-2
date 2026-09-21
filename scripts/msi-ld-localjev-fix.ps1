$ErrorActionPreference = 'Stop'
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Write-Output "=== MSI LD LocalJev fix $ts ==="

$harness = 'C:\Users\natha\code\jev-plays-starcraft-2'
$lj = 'C:\Users\natha\code\jev-copycats\localjev'

# 1) Harness: pull + ensure continue_operations suppress
Set-Location $harness
git fetch origin harness/ld-validate-fallback 2>&1 | Out-String | Write-Output
git checkout harness/ld-validate-fallback 2>&1 | Out-String | Write-Output
git pull --ff-only origin harness/ld-validate-fallback 2>&1 | Out-String | Write-Output
Write-Output ("HARNESS_HEAD=" + (git rev-parse --short HEAD))
$py = Get-Content (Join-Path $harness 'player.py') -Raw
if ($py -notmatch 'continue_operations_suppressed') {
  Write-Output 'HARNESS_CONTINUE_OPS_SUPPRESS_MISSING — applying local patch'
  if ($py -match "continue_operations':'Let current tasks progress before changing commitment\.',\r?\n        \}") {
    # emergency inline: pop continue_operations when all selection_facts fully idle
    $insert = @"
        if not state.get('objective', {}).get('done'):
            facts_map = state.get('selection_facts') or {}
            if facts_map and all((f.get('count') or 0) > 0 and (f.get('idle_count') or 0) >= (f.get('count') or 0) for f in facts_map.values()):
                options.pop('continue_operations', None)
                jev.log('continue_operations_suppressed', loop=view['loop'], reason='all_selection_facts_fully_idle')
"@
    $py2 = $py -replace "(continue_operations':'Let current tasks progress before changing commitment\.',\r?\n        \}\r?\n)(\s*)decision = await jev.ask", "`$1$insert`$2decision = await jev.ask"
    if ($py2 -ne $py) { Set-Content -Path (Join-Path $harness 'player.py') -Value $py2 -NoNewline; Write-Output 'HARNESS_INLINE_PATCH_APPLIED' }
    else { Write-Output 'HARNESS_INLINE_PATCH_FAIL' }
  }
} else { Write-Output 'HARNESS_CONTINUE_OPS_SUPPRESS_OK' }

# 2) LocalJev engine: force json_object + format json (no json_schema)
Set-Location $lj
$eng = Join-Path $lj 'src\engine.ts'
$engText = [IO.File]::ReadAllText($eng)
if ($engText -match 'type:\s*"json_schema"') {
  $engText = $engText -replace '(?s)response_format:\s*\{\s*type:\s*"json_schema".*?\},', @'
format: "json",
        response_format: {
          type: "json_object",
        },
'@
  [IO.File]::WriteAllText($eng, $engText)
  Write-Output 'ENGINE_JSON_SCHEMA_REPLACED'
} elseif ($engText -match 'json_object') {
  Write-Output 'ENGINE_JSON_OBJECT_OK'
  if ($engText -notmatch 'format:\s*"json"') {
    $engText = $engText.Replace('response_format: {', 'format: "json",`r`n        response_format: {')
    [IO.File]::WriteAllText($eng, $engText)
    Write-Output 'ENGINE_FORMAT_JSON_ADDED'
  }
} else { Write-Output 'ENGINE_UNEXPECTED' }

# Ensure content|reasoning + extractJson think strip
if ($engText -notmatch 'reasoning_content') { Write-Output 'ENGINE_WARN_NO_REASONING_FALLBACK' } else { Write-Output 'ENGINE_REASONING_OK' }
if ($engText -notmatch '<think>') { Write-Output 'ENGINE_WARN_NO_THINK_STRIP' } else { Write-Output 'ENGINE_THINK_STRIP_OK' }

# Env for qwen reliability / speed
$env:LOCALJEV_MAX_OUTPUT_TOKENS = '2048'
$env:LOCALJEV_MALFORMED_RETRIES = '1'
$env:LOCALJEV_MAX_INFLIGHT = '1'
$env:LOCALJEV_TEMPERATURE = '0'
$env:LOCALJEV_TIMEOUT = '60'

# 3) Restart LocalJev ONLY (port 8080 bun) — never kill python trees
Write-Output '===LOCALJEV_RESTART==='
$conn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
$ljPids = @()
if ($conn) { $ljPids = @($conn | Select-Object -ExpandProperty OwningProcess -Unique) }
foreach ($procId in $ljPids) {
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId"
  $cmd = $p.CommandLine
  Write-Output ("8080_pid=$procId cmd=" + ($(if ($cmd.Length -gt 180) { $cmd.Substring(0,180) } else { $cmd })))
  if ($cmd -match 'localjev|bun.*index|src[/\\]index') {
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    Write-Output "Stopped LocalJev $procId"
  } else { Write-Output "SKIP non-localjev $procId" }
}
Start-Sleep -Seconds 2

# Load .env if present without printing secrets
$envFile = Join-Path $lj '.env'
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k,$v = $_.Split('=',2)
    if ($k -and $v -ne $null -and $k -notmatch 'KEY|TOKEN|SECRET|PASSWORD') {
      Set-Item -Path "Env:$k" -Value $v.Trim().Trim('"')
    } elseif ($k -match 'KEY|TOKEN') {
      Set-Item -Path "Env:$k" -Value $v.Trim().Trim('"')
    }
  }
  Write-Output 'ENV_LOADED_FROM_DOTENV'
}
# Force critical overrides after dotenv
$env:LOCALJEV_MAX_OUTPUT_TOKENS = '2048'
$env:LOCALJEV_MALFORMED_RETRIES = '1'
$env:LOCALJEV_MAX_INFLIGHT = '1'
$env:LOCALJEV_TEMPERATURE = '0'

$log = Join-Path $lj 'localjev-relaunch.log'
Start-Process -FilePath 'bun' -ArgumentList @('run','src/index.ts') -WorkingDirectory $lj -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $log
Write-Output "LOCALJEV_START_ISSUED log=$log"
Start-Sleep -Seconds 3
try {
  $h = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 5 -UseBasicParsing
  Write-Output ("LOCALJEV_HEALTH " + $h.Content)
} catch { Write-Output ("LOCALJEV_HEALTH_FAIL " + $_.Exception.Message); Get-Content $log -Tail 40 }

# 4) Diagnose: curl what LocalJev would send vs direct Ollama
Write-Output '===DIRECT_OLLAMA==='
$ollama = 'http://192.168.0.10:11434/v1/chat/completions'
$sw = [Diagnostics.Stopwatch]::StartNew()
try {
  $body = @{
    model = 'qwen3.5:4b'
    messages = @(@{role='user'; content='Reply with JSON only: {"ok":true}' })
    temperature = 0
    max_tokens = 64
    format = 'json'
    response_format = @{ type = 'json_object' }
  } | ConvertTo-Json -Depth 6
  $r = Invoke-WebRequest -Uri $ollama -Method POST -Body $body -ContentType 'application/json' -TimeoutSec 30 -UseBasicParsing
  $sw.Stop()
  Write-Output ("OLLAMA_MS=" + $sw.ElapsedMilliseconds + " status=" + $r.StatusCode)
  Write-Output ("OLLAMA_BODY=" + $r.Content.Substring(0, [Math]::Min(300, $r.Content.Length)))
} catch {
  $sw.Stop()
  Write-Output ("OLLAMA_FAIL ms=" + $sw.ElapsedMilliseconds + " " + $_.Exception.Message)
}

Write-Output '===SYSTEMONE_SMOKE==='
$smokeBody = @{
  model = 'openjev-latest'
  state = @{ objective = @{ done = $false }; note = 'smoke' }
  questions = @{
    strategy = @{
      type = 'choice'
      instructions = 'Pick one.'
      criteria = @{ attack = 'Attack'; recover = 'Recover' }
    }
    coordination = @{
      type = 'choice'
      instructions = 'Pick grouping.'
      criteria = @{ by_type = 'By type'; mobile_combat = 'Combat' }
    }
  }
} | ConvertTo-Json -Depth 8
$sw2 = [Diagnostics.Stopwatch]::StartNew()
try {
  $r2 = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v1/systemone' -Method POST -Body $smokeBody -ContentType 'application/json' -TimeoutSec 45 -UseBasicParsing
  $sw2.Stop()
  Write-Output ("SYSTEMONE_MS=" + $sw2.ElapsedMilliseconds + " status=" + $r2.StatusCode)
  Write-Output ("SYSTEMONE_BODY=" + $r2.Content.Substring(0, [Math]::Min(500, $r2.Content.Length)))
} catch {
  $sw2.Stop()
  Write-Output ("SYSTEMONE_FAIL ms=" + $sw2.ElapsedMilliseconds + " " + $_.Exception.Message)
  if (Test-Path $log) { Get-Content $log -Tail 60 }
}

# 5) If LD run wedged on timeouts — cold-restart traynor01 LocalJev once with widget
Write-Output '===LD_RUN_CHECK==='
$runs = Get-ChildItem (Join-Path $harness 'runs') -Directory -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 5
foreach ($run in $runs) {
  Write-Output ("RUN " + $run.LastWriteTime.ToString('HH:mm:ss') + " " + $run.Name)
}
$newest = $runs | Select-Object -First 1
$wedged = $false
if ($newest) {
  $logs = Get-ChildItem $newest.FullName -Recurse -Include *.jsonl,*.log -ErrorAction SilentlyContinue
  foreach ($f in $logs) {
    if (Select-String -Path $f.FullName -Pattern 'TimeoutError|502 after|no JSON object' -Quiet) { $wedged = $true; break }
  }
}
Write-Output ("WEDGED=" + $wedged)

if ($wedged) {
  Write-Output '===COLD_RESTART_TRAYNOR01==='
  # Kill SC2 only, not python trees
  Get-Process -Name 'SC2*','SC2Switcher*' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("kill SC2 " + $_.Id); Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 2
  $env:JEV_VIA = 'openjev'
  $env:OPENJEV_BASE_URL = 'http://127.0.0.1:8080'
  $env:JEV_MODEL = 'openjev-latest'
  $env:JEV_TIMEOUT_MS = '180000'
  $env:MEMORY_MODE = 'none'
  $env:GUIDE_ENABLED = '1'
  $env:GUIDE_MODEL = 'google/gemini-2.5-flash'
  $launch = Join-Path $harness 'jev-launch-traynor.ps1'
  if (Test-Path $launch) {
    Write-Output "LAUNCH $launch"
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$launch) -WorkingDirectory $harness -WindowStyle Normal
  } else {
    Write-Output 'LAUNCH_SCRIPT_MISSING'
  }
  $widget = Join-Path $harness 'scripts\open-controller-widget.ps1'
  if (Test-Path $widget) { & $widget 2>&1 | Select-Object -First 20 }
}

# 6) Evidence after short wait
Start-Sleep -Seconds 12
Write-Output '===EVIDENCE==='
$newest = Get-ChildItem (Join-Path $harness 'runs') -Directory -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($newest) {
  Write-Output ("RUN " + $newest.Name)
  Get-ChildItem $newest.FullName -Recurse -Include *.jsonl -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 8 |
    ForEach-Object {
      Write-Output ("FILE " + $_.Name)
      Select-String -Path $_.FullName -Pattern 'continue_operations_suppressed|strategy_choice|SystemOne|latency|submitted|cmds|TimeoutError|group_choice' |
        Select-Object -First 12 | ForEach-Object { Write-Output $_.Line.Substring(0, [Math]::Min(240, $_.Line.Length)) }
    }
}

Write-Output '===DONE==='
Write-Output ("HARNESS=" + (git -C $harness rev-parse --short HEAD))
Write-Output ("CONTINUE_OPS_SUPPRESS=" + ($py -match 'continue_operations_suppressed' -or (Get-Content (Join-Path $harness 'player.py') -Raw) -match 'continue_operations_suppressed'))
