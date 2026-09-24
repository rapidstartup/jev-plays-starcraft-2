# Start LocalJev on this box, backed by local Ollama (qwen3.5:4b), serving :8080.
# Idempotent. Exposes POST /v1/systemone (Jev wire-compatible) for the MSI harness.
#
#   .\bigbox-localjev.ps1                 # qwen3.5:4b on :8080
#   .\bigbox-localjev.ps1 -Model qwen3.5:4b -Port 8080 -Key local
param(
  [string]$Model = 'qwen3.5:4b',
  [string]$Upstream = 'http://127.0.0.1:11434/v1',   # Ollama OpenAI-compatible
  [int]$Port = 8080,
  [string]$Key = 'local',
  [int]$TimeoutSec = 300,
  [string]$CopycatsRoot = $env:JEV_COPYCATS_ROOT   # default: sibling of harness
)
$ErrorActionPreference = 'Stop'

$harness = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $CopycatsRoot) { $CopycatsRoot = Join-Path (Split-Path -Parent $harness) 'jev-copycats' }
$repo = Join-Path $CopycatsRoot 'localjev'
$UPSTREAM_KEY = 'ollama'   # Ollama ignores the bearer; any non-empty value is fine

Write-Host "== LocalJev -> $Model via $Upstream (serve :$Port) =="

# 1) clone if missing
if (-not (Test-Path $repo)) {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git not found' }
  New-Item -ItemType Directory -Path $CopycatsRoot -Force | Out-Null
  Write-Host 'cloning githubnext/localjev ...'
  git clone --depth 1 https://github.com/githubnext/localjev.git $repo
}

# 2) deps
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) { throw 'bun not found (install Bun 1.2+)' }
Push-Location $repo
if (-not (Test-Path node_modules)) { Write-Host 'bun install ...'; bun install }

# 3) write .env (Bun auto-loads it)
$envFile = Join-Path $repo '.env'
$envText = @(
  "LOCALJEV_UPSTREAM=$Upstream"
  "LOCALJEV_UPSTREAM_API_KEY=$UPSTREAM_KEY"
  "LOCALJEV_UPSTREAM_MODEL=$Model"
  "LOCALJEV_API_KEY=$Key"
  "LOCALJEV_HOST=0.0.0.0"     # reachable from MSI over the LAN
  "LOCALJEV_PORT=$Port"
  "LOCALJEV_TIMEOUT=$TimeoutSec"
  "LOCALJEV_MAX_INFLIGHT=2"
  "LOCALJEV_MAX_QUEUE=64"
  "LOCALJEV_MALFORMED_RETRIES=2"
  "LOCALJEV_MAX_OUTPUT_TOKENS=2048"
  "LOCALJEV_QUESTIONS_PER_CALL=16"
  "LOCALJEV_OUTCOMES_PER_CALL=128"
) -join "`n"
Set-Content -Path $envFile -Value $envText -Encoding ASCII
Write-Host "wrote $envFile"

# 4) upstream model present?
$ollamaBase = $Upstream -replace '/v1$',''
$ollamaModels = curl.exe -sS -m 10 "$ollamaBase/models" 2>$null
if ($ollamaModels -and ($ollamaModels -notmatch [regex]::Escape(($Model -split ':')[0]))) {
  Write-Warning "model '$Model' not seen in upstream /models - pull it first: ollama pull $Model"
}

# 5) (re)start on the port
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Write-Host "port $Port busy (pid $($existing.OwningProcess)) - leaving it, assuming LocalJev already up"
} else {
  $logOut = Join-Path $repo 'localjev.bigbox.out.log'
  $logErr = Join-Path $repo 'localjev.bigbox.err.log'
  $proc = Start-Process -FilePath 'bun' -ArgumentList @('run','src/index.ts') -WorkingDirectory $repo -WindowStyle Minimized -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru
  Write-Host "started bun pid=$($proc.Id) (logs: $logOut)"
}

# 6) health
$ready = $false
for ($i = 0; $i -lt 24; $i++) {
  Start-Sleep -Seconds 5
  $r = curl.exe -sS -m 5 "http://127.0.0.1:$Port/ready" 2>$null
  if ($r) { Write-Host "READY (~$(($i+1)*5)s) $r"; $ready = $true; break }
}
if (-not $ready) { Write-Warning "not ready yet - check $logOut / $logErr"; Pop-Location; exit 1 }

# 7) a tiny decide to prove the path end-to-end
$body = '{"state":"A marine squad is near the enemy base.","questions":{"a":{"type":"choice","instructions":"Pick the next action.","criteria":{"attack":"Attack-move the squad forward.","hold":"Hold position."}}}}'
$tmp = Join-Path $env:TEMP 'bigbox-localjev-smoke.json'
Set-Content -Path $tmp -Value $body -Encoding ASCII
$sw = [Diagnostics.Stopwatch]::StartNew()
$out = curl.exe -sS -m $TimeoutSec -X POST "http://127.0.0.1:$Port/v1/systemone" -H "Content-Type: application/json" -H "Authorization: Bearer $Key" --data-binary "@$tmp" 2>&1
$sw.Stop()
Write-Host ("decide: " + ($out -join ''))
Write-Host ("decide latency: " + [math]::Round($sw.Elapsed.TotalSeconds,2) + "s")
Pop-Location
Write-Host "LocalJev up on :$Port - point the MSI harness at http://<this-box>:$Port"
