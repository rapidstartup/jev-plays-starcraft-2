# Full run with 50/50 tiled video capture (game left, decision log right).
# Usage: .\scripts\opencode\run-capture.ps1 -EnvScript scripts\opencode\env-decision-openrouter-no-helper.ps1
# Recording uses fragmented mp4 (-movflags frag_keyframe+empty_moov) so the file stays
# playable even if recording is stopped hard. Stills are pulled at the end.
param([string]$EnvScript = 'scripts\opencode\env-decision-openrouter-guide-flash.ps1',
      [string]$Capture = 'desktop')
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\natha\code\jev-plays-starcraft-2'
Set-Location $root
. (Join-Path $root $EnvScript)
if (-not $?) { Write-Output 'RUN_ABORT env red'; exit 1 }

& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\opencode\preflight_decide.py')
if ($LASTEXITCODE -ne 0) { Write-Output 'RUN_ABORT decide preflight red; game not started'; exit 1 }

# Real-time gate: measure an actual game-sized decision and refuse to boot SC2 if
# the backend is too slow to drive a real-time loop (prevents mid-run timeouts ->
# starved agent -> defeats). JEV_REALTIME_MAX_MS defaults to 5000; -1 disables.
$rtMax = if ($env:JEV_REALTIME_MAX_MS) { [int]$env:JEV_REALTIME_MAX_MS } else { 5000 }
if ($rtMax -gt 0) {
  Write-Output ("RUN realtime gate (max_ms=$rtMax) ...")
  & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\opencode\preflight_realtime_gate.py') $rtMax
  if ($LASTEXITCODE -ne 0) { Write-Output 'RUN_ABORT realtime gate red; game not started'; exit 1 }
}

& (Join-Path $root 'scripts\opencode\restart-controller.ps1')
# Snapshot result dirs BEFORE launch: only a NEW dir's result.json counts as ours.
# (A previous combo's fresh result must never be claimed by this run.)
$knownUtc = @{}
Get-ChildItem (Join-Path $root 'runs\202*') -Directory -ErrorAction SilentlyContinue | ForEach-Object { $knownUtc[$_.FullName] = $true }
& (Join-Path $root 'jev-launch-traynor.ps1')
if ($LASTEXITCODE -ne 0) { Write-Output 'RUN_ABORT launcher failed'; exit 1 }

$guideDir = Get-ChildItem (Join-Path $root 'runs\guide-traynor01-*') -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Output ("RUN guideDir=" + $guideDir.FullName)
# Tile game + log window 50/50. The game window can take a minute to appear —
# retry for up to ~2 min before giving up (never start recording untiled quietly).
$tiled = $false
for ($i = 0; $i -lt 12 -and -not $tiled; $i++) {
  if ($i -gt 0) { Start-Sleep -Seconds 10 }
  $tileOut = & (Join-Path $root 'scripts\opencode\layout-screengrab.ps1') 2>&1 | Out-String
  Write-Output $tileOut.Trim()
  if ($tileOut -match 'LAYOUT_OK') { $tiled = $true }
}
if (-not $tiled) { Write-Output 'RUN_WARN tiling failed; recording full screen untiled' }

$ff = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$vid = Join-Path $guideDir.FullName 'screen-capture.mp4'
if ($Capture -eq 'gamewindow') {
  # Capture ONLY the game window: zero desktop leakage by construction.
  # Tiling still applied so a human watcher sees game + log side by side.
  $ffArgs = @('-y','-f','gdigrab','-framerate','30','-i','title=StarCraft II','-c:v','libx264','-pix_fmt','yuv420p','-preset','veryfast','-movflags','+frag_keyframe+empty_moov', $vid)
} else {
  $ffArgs = @('-y','-f','gdigrab','-framerate','30','-i','desktop','-vf','scale=1536:864','-c:v','libx264','-pix_fmt','yuv420p','-preset','veryfast','-movflags','+frag_keyframe+empty_moov', $vid)
}
$fp = Start-Process -FilePath $ff -ArgumentList $ffArgs -WindowStyle Minimized -PassThru
Write-Output ("REC pid=" + $fp.Id + " file=" + $vid)
$fp.Id | Set-Content (Join-Path $guideDir.FullName 'ffmpeg-pid.txt')

# Wait for the harness result (up to 60 min), polling for result.json.
# Watchdogs: (a) end-screen stall — game clock stalled >5 min means a modal dialog
# (e.g. defeat screen) needs closing: screenshot it, force-quit the game, end the run.
# (b) game gone with no result — harness crashed: finish as incomplete, don't hang.
$forceQuitDone = $false
$deadline = (Get-Date).AddMinutes(60)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 20
  $utc = Get-ChildItem (Join-Path $root 'runs\202*') -Directory -ErrorAction SilentlyContinue | Where-Object { -not $knownUtc.ContainsKey($_.FullName) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($utc -and (Test-Path (Join-Path $utc.FullName 'result.json'))) {
    $age = (Get-Date) - $utc.LastWriteTime
    if ($age.TotalMinutes -lt 30) {
      Write-Output ("RUN result found: " + $utc.FullName)
      Get-Content (Join-Path $utc.FullName 'result.json') -TotalCount 12
      break
    }
  }
  $sc2 = Get-Process SC2* -ErrorAction SilentlyContinue
  if (-not $sc2) {
    # Game gone: if the harness also exited, the run is over — never hang here.
    Start-Sleep -Seconds 30
    $stillGone = -not (Get-Process SC2* -ErrorAction SilentlyContinue)
    $harness = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'jev_sc2 --map' }
    if ($stillGone -and -not $harness) {
      Write-Output 'RUN_END game closed and harness exited without result.json; finishing as incomplete (see run log)'
      break
    }
    continue
  }
  if (-not $forceQuitDone) {
    $runLog = Join-Path $guideDir.FullName 'run.log'
    if (Test-Path $runLog) {
      $stallLines = Select-String -Path $runLog -Pattern 'awaiting_ui_dismiss.*"stalled_for_s":\s*(\d+)' | Select-Object -Last 1
      if ($stallLines -and ($stallLines.Matches.Groups[1].Value -as [int]) -gt 300) {
        Write-Output ("RUN_STUCK end-screen stall >5min (" + $stallLines.Matches.Groups[1].Value + "s); screenshotting then force-quitting game")
        & $ff -y -v error -f gdigrab -framerate 1 -i desktop -vframes 1 (Join-Path $guideDir.FullName 'still-stuck-endscreen.png')
        foreach ($p in $sc2) {
          try { $p.CloseMainWindow() | Out-Null } catch {}
        }
        Start-Sleep -Seconds 10
        $sc2 = Get-Process SC2* -ErrorAction SilentlyContinue
        foreach ($p in $sc2) {
          try { Stop-Process -Id $p.Id -Force; Write-Output ("RUN_STUCK force-quit SC2 pid=" + $p.Id) } catch {}
        }
        $forceQuitDone = $true
      }
    }
  }
}
try { Stop-Process -Id $fp.Id -Force } catch {}
Start-Sleep -Seconds 2
$probe = Join-Path (Split-Path $ff) 'ffprobe.exe'
if (Test-Path $probe) { & $probe -v error -show_entries format=duration -of default=noprint_wrappers=1 $vid }
& $ff -y -v error -sseof -25 -i $vid -vframes 1 (Join-Path $guideDir.FullName 'still-near-victory.png')
& $ff -y -v error -sseof -90 -i $vid -vframes 1 (Join-Path $guideDir.FullName 'still-midgame.png')
Get-ChildItem (Join-Path $guideDir.FullName 'screen-capture.mp4'), (Join-Path $guideDir.FullName '*.png') -ErrorAction SilentlyContinue | Select-Object Name,Length

# Collect done: close the log window + its server so the next run starts clean.
# (The window intentionally stays open during the run for stills; it must not linger.)
Get-Process msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*Jev SC2 Controller*' } | ForEach-Object {
  try { Stop-Process -Id $_.Id -Force; Write-Output ("WIDGET closed pid=" + $_.Id) } catch {}
}
$wservers = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'controller_widget_server\.py' }
foreach ($p in $wservers) {
  try { Stop-Process -Id $p.ProcessId -Force; Write-Output ("WIDGET server closed pid=" + $p.ProcessId) } catch {}
}
Write-Output 'RUN_CAPTURE_DONE'
