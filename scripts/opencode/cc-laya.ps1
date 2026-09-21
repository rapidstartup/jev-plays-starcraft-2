# CC-LAYA smoke: Laya Router.system_one on CPU. Rerunnable.
# Reuses the nanojev venv (torch + transformers); laya is a pure pip package.
$ErrorActionPreference = 'Stop'
$harnessRoot = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$cc = if ($env:JEV_COPYCATS_ROOT) { $env:JEV_COPYCATS_ROOT } else { Join-Path (Split-Path -Parent $harnessRoot) 'jev-copycats' }
$repo = Join-Path $cc 'nanojev'
Set-Location $repo
$py = (Join-Path $repo '.venv-nano\Scripts\python.exe')
if (-not (Test-Path $py)) { Write-Output 'CC-LAYA_BLOCKED run cc-nano.ps1 first (needs .venv-nano)'; exit 1 }
& $py -m pip install laya
& $py -c "import time, json; from laya import Router; r=Router(preload=True); s='Refund the duplicate charge today or we cancel.'; q={'department':{'type':'choice','instructions':'Which department should handle this request?','criteria':{'billing':'invoices, payments, refunds','technical':'bugs, outages, system errors','sales':'pricing, new contracts'}}}; t=time.perf_counter(); ans=r.system_one(s,q); print('time=%.2fs' % (time.perf_counter()-t)); print(json.dumps(ans, default=str)[:300])"
Write-Output 'CC-LAYA smoke done'
