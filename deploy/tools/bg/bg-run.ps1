# bg-run.ps1 - 通用后台执行器：任何命令立即返回，状态与日志落盘，随时秒查
# 用法:
#   pwsh bg-run.ps1 -Name 下载依赖 -Command "pnpm install" -WorkDir "D:\AI\deepseek\deepseek-harness"
#   pwsh bg-run.ps1 -Name 查服务器 -Command "ssh minjian@192.168.0.107 df -h" -TimeoutSec 60
# 查询: pwsh bg-status.ps1 -Name 下载依赖   停止: pwsh bg-stop.ps1 -Name 下载依赖
# Base 默认 %USERPROFILE%\.bg，可 -Base 覆盖（同一 Base 下按 Name 区分任务）
param(
  [Parameter(Mandatory=$true)][string]$Name,
  [Parameter(Mandatory=$true)][string]$Command,
  [string]$WorkDir = (Get-Location).Path,
  [int]$TimeoutSec = 0,
  [string]$Base = (Join-Path $env:USERPROFILE ".bg")
)
New-Item -ItemType Directory -Force -Path $Base | Out-Null
$safe = $Name -replace '[\\/:*?"<>|]', '_'
$OutFile = Join-Path $Base "$safe.out.log"
$ErrFile = Join-Path $Base "$safe.err.log"
$StateFile = Join-Path $Base "$safe.json"
Remove-Item $OutFile,$ErrFile,$StateFile -ErrorAction SilentlyContinue

$wrap = "Set-Location -LiteralPath '$WorkDir'; $Command"
if ($TimeoutSec -gt 0) { $wrap = "$wrap; exit" }

$p = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile","-Command",$wrap `
  -RedirectStandardOutput $OutFile -RedirectStandardError $ErrFile -WindowStyle Hidden -PassThru
@{ name = $Name; pid = $p.Id; started = (Get-Date -Format "yyyy-MM-dd HH:mm:ss"); command = $Command; out = $OutFile } | ConvertTo-Json | Set-Content $StateFile
Write-Output "BG_STARTED name=$Name pid=$($p.Id)"
Write-Output "状态查询: pwsh $PSScriptRoot\bg-status.ps1 -Name '$Name'"
Write-Output "日志: $OutFile"
