$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\natha\code\jev-plays-starcraft-2'
Write-Output '===PRE==='
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git fetch origin harness/ld-validate-fallback
git checkout harness/ld-validate-fallback
git pull --ff-only origin harness/ld-validate-fallback
Write-Output '===POST==='
git rev-parse --short HEAD
git log -1 --oneline
Select-String -Path '.\jev_sc2\view.py' -Pattern 'validate_commands_with_rejects|target_not_visible|attack_move' |
  Select-Object -First 12 | ForEach-Object { $_.Line.Trim() }
