# Idempotent env for LD-LJ: LocalJev (:8080) -> Ollama qwen3.5:4b on .10.
$ErrorActionPreference = 'Stop'
$root = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
if (-not (Test-Path (Join-Path $root 'jev_sc2'))) { $root = 'C:\Users\natha\code\jev-plays-starcraft-2' }
Set-Location $root

$raw = Get-Content (Join-Path $root '.env') -Raw -ErrorAction SilentlyContinue
foreach ($k in @('OPENROUTER_API_KEY','JEV_API_KEY','OPENJEV_API_KEY','CODIV_API_KEY','TYPESAFE_API_KEY')) {
  if ($raw -match ("(?m)^" + $k + "=([^\r\n]+)")) {
    $v = $Matches[1].Trim()
    if ($v) { Set-Item -Path ("env:" + $k) -Value $v }
  }
}
# .env.local (git-ignored) overrides .env when present — holds djev/OpenRouter rotation keys.
$local = Get-Content (Join-Path $root '.env.local') -Raw -ErrorAction SilentlyContinue
if ($local) {
  foreach ($k in @('OPENROUTER_API_KEY','JEV_API_KEY','OPENJEV_API_KEY','CODIV_API_KEY','TYPESAFE_API_KEY','DJEV_API_KEY')) {
    if ($local -match ("(?m)^" + $k + "=([^\r\n]+)")) {
      $v = $Matches[1].Trim()
      if ($v) { Set-Item -Path ("env:" + $k) -Value $v }
    }
  }
  Write-Output 'ENV note: .env.local overrides applied (names only, values hidden)'
}
# LocalJev bearer lives in the localjev checkout; promote to OPENJEV_API_KEY (no echo).
# Portable: sibling `jev-copycats` next to the harness root, or $env:JEV_COPYCATS_ROOT.
$ccRoot = if ($env:JEV_COPYCATS_ROOT) { $env:JEV_COPYCATS_ROOT } else { Join-Path (Split-Path -Parent $root) 'jev-copycats' }
$ljEnv = Get-Content (Join-Path $ccRoot 'localjev\.env') -Raw -ErrorAction SilentlyContinue
if (-not $ljEnv) { $ljEnv = Get-Content 'C:\Users\natha\code\jev-copycats\localjev\.env' -Raw -ErrorAction SilentlyContinue }
if ($ljEnv -match '(?m)^LOCALJEV_API_KEY=([^\r\n]+)') {
  $ljKey = $Matches[1].Trim()
  if ($ljKey) { $env:OPENJEV_API_KEY = $ljKey }
}
if (-not $env:OPENJEV_API_KEY) { Write-Output 'ENV_LD-LJ_RED missing LocalJev bearer'; exit 1 }

$env:JEV_VIA = 'openjev'
$env:OPENJEV_BASE_URL = 'http://127.0.0.1:8080'
$env:JEV_MODEL = 'openjev-latest'
$env:JEV_TIMEOUT_MS = '120000'
$env:JEV_MEMORY_MODE = 'none'
$env:GUIDE_ENABLED = '1'
$env:GUIDE_MODEL = 'google/gemini-2.5-flash'
$env:GUIDE_EVERY_N_TICKS = '8'

Write-Output 'ENV LD-LJ via=openjev base=127.0.0.1:8080 (upstream qwen3.5:4b on .10) model=openjev-latest timeout_ms=120000 memory=none'
