# bg-status.ps1 - 秒级查询后台任务状态（运行中/已结束 + 日志尾部）
param(
  [Parameter(Mandatory=$true)][string]$Name,
  [string]$Base = (Join-Path $env:USERPROFILE ".bg")
)
$safe = $Name -replace '[\\/:*?"<>|]', '_'
$StateFile = Join-Path $Base "$safe.json"
$OutFile = Join-Path $Base "$safe.out.log"
$ErrFile = Join-Path $Base "$safe.err.log"
if (-not (Test-Path $StateFile)) { Write-Output "NOT_FOUND name=$Name base=$Base"; exit 1 }
$s = Get-Content $StateFile -Raw | ConvertFrom-Json
$alive = Get-Process -Id $s.pid -ErrorAction SilentlyContinue
if ($alive) {
  Write-Output "RUNNING name=$Name pid=$($s.pid) 已运行 $([int]((Get-Date) - $alive.StartTime).TotalSeconds) 秒"
  if (Test-Path $OutFile) { Get-Content $OutFile -Tail 5 -ErrorAction SilentlyContinue }
} else {
  $outText = if (Test-Path $OutFile) { Get-Content $OutFile -Raw -ErrorAction SilentlyContinue } else { "" }
  Write-Output "FINISHED name=$Name 输出行数=$((($outText -split "`n") | Measure-Object).Count)"
  Get-Content $OutFile -Tail 8 -ErrorAction SilentlyContinue
  if ((Test-Path $ErrFile) -and (Get-Item $ErrFile).Length -gt 0) { Write-Output "--- stderr ---"; Get-Content $ErrFile -Tail 5 -ErrorAction SilentlyContinue }
}
