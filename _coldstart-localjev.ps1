$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\natha\code\jev-plays-starcraft-2'
$env:JEV_VIA = 'openjev'
$env:OPENJEV_BASE_URL = 'http://127.0.0.1:8080'
$env:JEV_TIMEOUT_MS = '300000'
$env:JEV_MODEL = 'openjev-latest'
$env:MEMORY_MODE = 'none'
$env:GUIDE_ENABLED = '1'
$env:GUIDE_MODEL = 'google/gemini-2.5-flash'
Write-Output '===ENV==='
Write-Output ('JEV_VIA=' + $env:JEV_VIA)
Write-Output ('OPENJEV_BASE_URL=' + $env:OPENJEV_BASE_URL)
Write-Output ('JEV_TIMEOUT_MS=' + $env:JEV_TIMEOUT_MS)
Write-Output ('JEV_MODEL=' + $env:JEV_MODEL)
Write-Output ('MEMORY_MODE=' + $env:MEMORY_MODE)
& .\jev-launch-traynor.ps1
