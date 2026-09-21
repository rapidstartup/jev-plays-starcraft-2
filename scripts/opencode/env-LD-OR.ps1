# Idempotent env for LD-OR: OpenRouter Jev (clean A/B vs TypeSafe).
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
if (-not $env:OPENROUTER_API_KEY) { Write-Output 'ENV_LD-OR_RED missing OPENROUTER_API_KEY'; exit 1 }

$env:JEV_VIA = 'openrouter'
$env:JEV_MODEL = 'typesafe/jev-1.13'
$env:JEV_TIMEOUT_MS = '15000'
$env:JEV_MEMORY_MODE = 'none'
$env:GUIDE_ENABLED = '1'
$env:GUIDE_MODEL = 'google/gemini-2.5-flash'
$env:GUIDE_EVERY_N_TICKS = '8'

Write-Output 'ENV LD-OR via=openrouter model=typesafe/jev-1.13 timeout_ms=15000 memory=none guide=google/gemini-2.5-flash'
