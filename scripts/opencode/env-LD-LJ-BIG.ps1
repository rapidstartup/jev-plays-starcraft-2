# Idempotent env for LD-LJ-BIG: LocalJev on the big box (192.168.0.10:8080) over LAN.
# LocalJev speaks the Jev /v1/systemone wire format and is backed by local
# Ollama qwen3.5:4b on the 24GB box. Model id on the wire is 'localjev-latest'.
$ErrorActionPreference = 'Stop'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root
$raw = Get-Content (Join-Path $root '.env') -Raw -ErrorAction SilentlyContinue
if ($raw -match '(?m)^OPENROUTER_API_KEY=([^\r\n]+)') { $env:OPENROUTER_API_KEY = $Matches[1].Trim() }
$env:OPENJEV_API_KEY = 'local'
$env:JEV_VIA = 'openjev'
$env:OPENJEV_BASE_URL = 'http://192.168.0.10:8080'
$env:JEV_MODEL = 'localjev-latest'
$env:JEV_SYSTEMONE_MODEL = 'localjev-latest'   # send the wire id verbatim
$env:JEV_TIMEOUT_MS = '120000'
$env:JEV_MEMORY_MODE = 'none'
$env:GUIDE_ENABLED = '1'
$env:GUIDE_MODEL = 'google/gemini-2.5-flash'
$env:GUIDE_EVERY_N_TICKS = '8'
Write-Output 'ENV LD-LJ-BIG via=openjev base=192.168.0.10:8080 model=localjev-latest (qwen3.5:4b) timeout_ms=120000 memory=none'
