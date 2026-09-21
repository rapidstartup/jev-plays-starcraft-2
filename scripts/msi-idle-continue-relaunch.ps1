$ErrorActionPreference = 'Stop'
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Write-Output "=== MSI idle-continue apply+relaunch $ts ==="

# ---- 1) Harness: pull continue-idle commit on ld-validate-fallback ----
$harness = 'C:\Users\natha\code\jev-plays-starcraft-2'
Set-Location $harness
Write-Output '===GIT_BEFORE==='
git rev-parse --short HEAD
git log -1 --format='%h %s'
git fetch origin harness/ld-validate-fallback 2>&1 | Out-String | Write-Output
git checkout harness/ld-validate-fallback 2>&1 | Out-String | Write-Output
git pull --ff-only origin harness/ld-validate-fallback 2>&1 | Out-String | Write-Output
Write-Output '===GIT_AFTER==='
git rev-parse --short HEAD
git log -1 --format='%h %s'
# Confirm continue_would_idle early return present
$py = Get-Content (Join-Path $harness 'player.py') -Raw
if ($py -notmatch 'Fully idle selection: continue issues no SC2 commands') {
  Write-Output 'HARNESS_PATCH_MISSING'
  exit 2
}
Write-Output 'HARNESS_PATCH_OK'

# ---- 2) LocalJev harden on MSI checkout ----
$lj = 'C:\Users\natha\code\jev-copycats\localjev'
if (-not (Test-Path $lj)) { Write-Output "LOCALJEV_MISSING $lj"; exit 3 }
Set-Location $lj
$cfg = Join-Path $lj 'src\config.ts'
$eng = Join-Path $lj 'src\engine.ts'
$cfgText = [IO.File]::ReadAllText($cfg)
if ($cfgText -match 'LOCALJEV_MALFORMED_RETRIES", 2,') {
  $cfgText = $cfgText.Replace('LOCALJEV_MALFORMED_RETRIES", 2,', 'LOCALJEV_MALFORMED_RETRIES", 4,')
  [IO.File]::WriteAllText($cfg, $cfgText)
  Write-Output 'LOCALJEV_CONFIG_BUMPED_2_TO_4'
} elseif ($cfgText -match 'LOCALJEV_MALFORMED_RETRIES", 4,') {
  Write-Output 'LOCALJEV_CONFIG_ALREADY_4'
} else {
  Write-Output 'LOCALJEV_CONFIG_UNEXPECTED'
}

$engText = [IO.File]::ReadAllText($eng)
$changed = $false
if ($engText -notmatch 'think: false') {
  $engText = $engText.Replace(
    "chat_template_kwargs: { enable_thinking: false },",
    "chat_template_kwargs: { enable_thinking: false },`r`n        think: false,")
  $changed = $true
  Write-Output 'ENGINE_THINK_FALSE_ADDED'
} else { Write-Output 'ENGINE_THINK_FALSE_PRESENT' }

if ($engText -notmatch 'reasoning_content') {
  $oldMsg = @'
        const message = choices[0].message;
        if (!record(message) || typeof message.content !== "string") {
          throw new TypeError("message content is missing");
        }
        text = message.content;
'@
  $newMsg = @'
        const message = choices[0].message;
        if (!record(message)) {
          throw new TypeError("message content is missing");
        }
        const content =
          typeof message.content === "string" ? message.content : "";
        const reasoning =
          typeof message.reasoning === "string"
            ? message.reasoning
            : typeof message.reasoning_content === "string"
              ? message.reasoning_content
              : "";
        text = content.trim() ? content : reasoning;
        if (!text.trim()) {
          throw new TypeError("message content is missing");
        }
'@
  if ($engText.Contains($oldMsg)) {
    $engText = $engText.Replace($oldMsg, $newMsg)
    $changed = $true
    Write-Output 'ENGINE_CONTENT_REASONING_ADDED'
  } else {
    Write-Output 'ENGINE_CONTENT_BLOCK_NOT_FOUND'
  }
} else { Write-Output 'ENGINE_CONTENT_REASONING_PRESENT' }

if ($engText -notmatch '<think>') {
  $oldEx = "function extractJson(text: string): unknown {`r`n  let candidate = text.trim();"
  $newEx = "function extractJson(text: string): unknown {`r`n  let candidate = text.trim();`r`n  candidate = candidate.replace(/<think>[\\s\\S]*?<\\/think>/gi, \"\").trim();`r`n  candidate = candidate.replace(/<reasoning>[\\s\\S]*?<\\/reasoning>/gi, \"\").trim();"
  # try lf variants
  if (-not $engText.Contains($oldEx)) {
    $oldEx = "function extractJson(text: string): unknown {`n  let candidate = text.trim();"
    $newEx = "function extractJson(text: string): unknown {`n  let candidate = text.trim();`n  candidate = candidate.replace(/<think>[\\s\\S]*?<\\/think>/gi, \"\").trim();`n  candidate = candidate.replace(/<reasoning>[\\s\\S]*?<\\/reasoning>/gi, \"\").trim();"
  }
  if ($engText.Contains($oldEx)) {
    $engText = $engText.Replace($oldEx, $newEx)
    $changed = $true
    Write-Output 'ENGINE_EXTRACT_THINK_STRIP_ADDED'
  } else {
    Write-Output 'ENGINE_EXTRACT_BLOCK_NOT_FOUND'
  }
} else { Write-Output 'ENGINE_EXTRACT_THINK_STRIP_PRESENT' }

if ($changed) { [IO.File]::WriteAllText($eng, $engText) }

# ---- 3) Restart LocalJev only (port 8080 / bun localjev) — do NOT kill python trees ----
Write-Output '===LOCALJEV_RESTART==='
# Find listeners on 8080
$conn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
$ljPids = @()
if ($conn) { $ljPids = @($conn | Select-Object -ExpandProperty OwningProcess -Unique) }
foreach ($pid in $ljPids) {
  try {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$pid"
    $cmd = $p.CommandLine
    Write-Output ("8080_pid=$pid cmd=" + ($(if ($cmd.Length -gt 160) { $cmd.Substring(0,160) } else { $cmd })))
    if ($cmd -match 'localjev|bun|node') {
      Write-Output "Stopping LocalJev pid $pid"
      Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    } else {
      Write-Output "SKIP non-localjev listener $pid"
    }
  } catch { Write-Output "pid lookup fail $pid $_" }
}
Start-Sleep -Seconds 2

# Prefer existing start script if present
$started = $false
$startCandidates = @(
  (Join-Path $lj 'scripts\start.ps1'),
  (Join-Path $lj 'start.ps1'),
  'C:\Users\natha\code\jev-copycats\localjev\package.json'
)
# Use bun run from localjev dir with env for ollama/gemma via whatever they already use
$env:LOCALJEV_MALFORMED_RETRIES = '4'
# Health check current first
try {
  $h = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 3 -UseBasicParsing
  Write-Output ("LOCALJEV_STILL_UP status=" + $h.StatusCode)
  $started = $true
} catch {
  Write-Output 'LOCALJEV_DOWN_STARTING'
  Set-Location $lj
  if (Test-Path (Join-Path $lj 'package.json')) {
    # background start
    $log = 'C:\Users\natha\code\jev-copycats\localjev\localjev-relaunch.log'
    Start-Process -FilePath 'bun' -ArgumentList @('run','src/index.ts') -WorkingDirectory $lj -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $log
    $started = $true
    Write-Output "LOCALJEV_START_ISSUED log=$log"
  }
}
Start-Sleep -Seconds 4
try {
  $h = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 5 -UseBasicParsing
  Write-Output ("LOCALJEV_HEALTH " + $h.Content)
} catch {
  Write-Output ("LOCALJEV_HEALTH_FAIL " + $_.Exception.Message)
}

# Quick SystemOne-style smoke if smoke script exists
$smoke = Join-Path $harness 'scripts\smoke_openjev.py'
if (Test-Path $smoke) {
  Write-Output '===SMOKE_OPENJEV==='
  $env:OPENJEV_BASE_URL = 'http://127.0.0.1:8080'
  $env:JEV_MODEL = 'openjev-latest'
  & python $smoke 2>&1 | Select-Object -First 40 | ForEach-Object { Write-Output $_ }
}

# ---- 4) Cold start Liberation Day LocalJev — do NOT kill python parent/child trees ----
Write-Output '===COLDSTART_PREP==='
# If port 5001 busy / orphan SC2 only — kill SC2 then cold start once
$sc2ApiUp = $false
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5001' -TimeoutSec 2 -UseBasicParsing
  $sc2ApiUp = $true
  Write-Output 'PORT_5001_OPEN'
} catch { Write-Output 'PORT_5001_CLOSED' }

if ($sc2ApiUp) {
  Write-Output 'SC2_API_BUSY — killing SC2 processes only (not python trees)'
  Get-Process -Name 'SC2*','SC2Switcher*' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("kill SC2 " + $_.Id)
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 3
}

Set-Location $harness
$env:JEV_VIA = 'openjev'
$env:OPENJEV_BASE_URL = 'http://127.0.0.1:8080'
$env:JEV_MODEL = 'openjev-latest'
$env:JEV_TIMEOUT_MS = '300000'
$env:MEMORY_MODE = 'none'
$env:GUIDE_ENABLED = '1'
$env:GUIDE_MODEL = 'google/gemini-2.5-flash'

$cold = Join-Path $harness '_coldstart-localjev.ps1'
if (-not (Test-Path $cold)) { $cold = 'C:\Users\natha\code\jev-plays-starcraft-2\jev-launch-traynor.ps1' }
# Prefer workspace-copied scripts if present under repo
$alts = @(
  (Join-Path $harness 'jev-launch-traynor.ps1'),
  'C:\Users\natha\code\jev-plays-starcraft-2\scripts\..\jev-launch-traynor.ps1'
)
Write-Output ("LAUNCH_SCRIPT candidates")
Get-ChildItem $harness -Filter '*traynor*.ps1' -ErrorAction SilentlyContinue | ForEach-Object { Write-Output $_.FullName }
Get-ChildItem $harness -Filter '*coldstart*.ps1' -ErrorAction SilentlyContinue | ForEach-Object { Write-Output $_.FullName }

# Use jev-launch-traynor.ps1 if present in repo root or parent scripts dropped
$launch = $null
foreach ($c in @(
  (Join-Path $harness '_coldstart-localjev.ps1'),
  (Join-Path $harness 'jev-launch-traynor.ps1'),
  (Join-Path $harness 'scripts\msi-coldstart-openjev.ps1')
)) {
  if (Test-Path $c) { $launch = $c; break }
}
if (-not $launch) {
  # Inline traynor LD launch matching prior coldstart env
  Write-Output 'NO_LAUNCH_SCRIPT — using python -m jev_sc2 campaign Traynor Liberation Day style'
  $runLog = Join-Path $harness ("runs\guide-ld-localjev-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -ItemType Directory -Path $runLog -Force | Out-Null
  Write-Output "RUN_DIR $runLog"
  # Fall through to known launcher name from prior scripts
  if (Test-Path (Join-Path $harness 'start-guide.ps1')) {
    $launch = Join-Path $harness 'start-guide.ps1'
  }
}

if ($launch) {
  Write-Output "LAUNCH $launch"
  & $launch 2>&1 | Select-Object -First 80 | ForEach-Object { Write-Output $_ }
} else {
  Write-Output 'LAUNCH_MISSING'
}

Start-Sleep -Seconds 8
Write-Output '===NEWEST_RUNS==='
Get-ChildItem (Join-Path $harness 'runs') -Directory -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 8 |
  ForEach-Object { Write-Output ($_.LastWriteTime.ToString('HH:mm:ss') + ' ' + $_.Name) }

# Open controller widget
$widget = Join-Path $harness 'scripts\open-controller-widget.ps1'
if (Test-Path $widget) {
  Write-Output '===OPEN_WIDGET==='
  & $widget 2>&1 | Select-Object -First 30 | ForEach-Object { Write-Output $_ }
} else {
  Write-Output 'WIDGET_SCRIPT_MISSING'
}

# Evidence: first jev/tick lines from newest run
Write-Output '===FIRST_TICK_EVIDENCE==='
$newest = Get-ChildItem (Join-Path $harness 'runs') -Directory -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($newest) {
  Write-Output ("RUN " + $newest.Name)
  $jev = Get-ChildItem $newest.FullName -Filter 'jev.jsonl' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  $tick = Get-ChildItem $newest.FullName -Filter 'tick*.jsonl' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  $ctrl = Get-ChildItem $newest.FullName -Filter 'controller*.jsonl' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  foreach ($f in @($jev,$tick,$ctrl)) {
    if ($f) {
      Write-Output ("FILE " + $f.FullName.Replace($harness+'\',''))
      Get-Content $f.FullName -TotalCount 12 | ForEach-Object { Write-Output $_ }
    }
  }
  # Grep purpose continue / cmds
  Get-ChildItem $newest.FullName -Recurse -Include *.jsonl,*.log -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 6 |
    ForEach-Object {
      Write-Output ("SCAN " + $_.Name)
      Select-String -Path $_.FullName -Pattern 'purpose_choice|continue_suppressed|cmds|group_choice|MobileCombat' -SimpleMatch:$false |
        Select-Object -First 15 |
        ForEach-Object { Write-Output $_.Line.Substring(0, [Math]::Min(220, $_.Line.Length)) }
    }
}

Write-Output '===DONE==='
git -C $harness log -1 --format='%h %s'
