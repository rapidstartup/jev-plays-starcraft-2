# Idempotent env for LD-JEFF: jeff (log an-markewich GLiFormer) SystemOne server on :8010.
# jeff speaks the official typesafe-sdk wire format, so the harness uses JEV_VIA=openjev
# with OPENJEV_BASE_URL pointed at it. Key is the local dev key.
$ErrorActionPreference = 'Stop'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root

# jeff auth key (server started with JEFF_API_KEYS=devkey).
$env:OPENJEV_API_KEY = 'devkey'
$env:JEV_VIA = 'openjev'
$env:OPENJEV_BASE_URL = 'http://192.168.0.10:8010'
$env:JEV_MODEL = 'jev-latest'
$env:JEV_TIMEOUT_MS = '60000'
$env:JEV_MEMORY_MODE = 'none'
$env:GUIDE_ENABLED = '1'
$env:GUIDE_MODEL = 'google/gemini-3.8-flash'
$env:GUIDE_EVERY_N_TICKS = '8'
Write-Output 'ENV LD-JEFF via=openjev base=192.168.0.10:8010 model=jev-latest (gliformer-base-v1) timeout_ms=60000 memory=none'
