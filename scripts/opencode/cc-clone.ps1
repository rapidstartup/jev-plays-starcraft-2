# Clone all P0 copycats next to the harness checkout. Rerunnable (skips existing).
# Target: <harness>\..\jev-copycats  (override with $env:JEV_COPYCATS_ROOT)
$ErrorActionPreference = 'Stop'
$harnessRoot = if ($env:JEV_HARNESS_ROOT) { $env:JEV_HARNESS_ROOT } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$cc = if ($env:JEV_COPYCATS_ROOT) { $env:JEV_COPYCATS_ROOT } else { Join-Path (Split-Path -Parent $harnessRoot) 'jev-copycats' }
New-Item -ItemType Directory -Path $cc -Force | Out-Null
Set-Location $cc
$repos = @(
  @('nanojev', 'https://github.com/TianyuCodings/NanoJev.git'),
  @('jevlike', 'https://github.com/vinnylarouge/jevlike.git'),
  @('semif', 'https://github.com/TheoLeeCJ/SemIf.git'),
  @('litjev', 'https://github.com/zhengxuyu/litjev.git'),
  @('open-jev-dasein', 'https://github.com/daseinlabs/open-jev.git'),
  @('openjev-razorback', 'https://github.com/razorback16/openjev.git'),
  @('nimble', 'https://github.com/bespokelabsai/nimble.git')
)
foreach ($r in $repos) {
  if (Test-Path (Join-Path $cc $r[0])) { Write-Output ("SKIP " + $r[0] + " (exists)") }
  else { git clone --depth 1 $r[1] $r[0]; Write-Output ("CLONED " + $r[0]) }
}
Write-Output ("COPYCATS at " + $cc)
