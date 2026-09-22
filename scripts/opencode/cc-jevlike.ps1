# CC-JEVLIKE smoke: doom test_smoke + synthetic quickstart + short Doom play. Rerunnable.
$ErrorActionPreference = 'Stop'
$harnessRoot = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$cc = if ($env:JEV_COPYCATS_ROOT) { $env:JEV_COPYCATS_ROOT } else { Join-Path (Split-Path -Parent $harnessRoot) 'jev-copycats' }
$repo = Join-Path $cc 'jevlike'
Set-Location $repo
if (-not (Test-Path .\.venv-jl\Scripts\python.exe)) {
  uv venv --python 3.12 .venv-jl
  uv pip install --python .venv-jl/Scripts/python.exe -e '.[dev,games]'
}
$py = (Join-Path $repo '.venv-jl\Scripts\python.exe')
Set-Location (Join-Path $repo 'examples\doom')
& $py -m pytest test_smoke.py -q
Set-Location $repo
& $py -m jevlike.data synthetic --output data/synthetic
& $py -m jevlike.train data/synthetic/train.jsonl --validation data/synthetic/validation.jsonl --output runs/synthetic.pt
& $py -m jevlike.eval runs/synthetic.pt data/synthetic/test.jsonl
& $py examples/doom/play.py examples/checkpoints/joint-imitation.pt --episodes 2 --game-seconds 10 --device cpu --output runs/msi-doom.mp4 --trace runs/msi-doom-trace.json
Write-Output 'CC-JEVLIKE smoke done (doom smoke + synthetic eval + 2-episode play in runs/)'
