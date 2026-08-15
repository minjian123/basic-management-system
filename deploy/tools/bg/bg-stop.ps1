# bg-stop.ps1 - 停止后台任务
param(
  [Parameter(Mandatory=$true)][string]$Name,
  [string]$Base = (Join-Path $env:USERPROFILE ".bg")
)
$safe = $Name -replace '[\\/:*?"<>|]', '_'
$StateFile = Join-Path $Base "$safe.json"
if (-not (Test-Path $StateFile)) { Write-Output "NOT_FOUND name=$Name base=$Base"; exit 1 }
$s = Get-Content $StateFile -Raw | ConvertFrom-Json
$p = Get-Process -Id $s.pid -ErrorAction SilentlyContinue
if ($p) { Stop-Process -Id $s.pid -Force; Write-Output "STOPPED name=$Name pid=$($s.pid)" } else { Write-Output "ALREADY_FINISHED name=$Name" }
