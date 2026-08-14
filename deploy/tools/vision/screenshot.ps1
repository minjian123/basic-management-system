<#
截图脚本：Edge/Chrome 无头模式将 HTML 或 URL 渲染为 PNG（Windows）。

用法：
  powershell -NoProfile -ExecutionPolicy Bypass -File screenshot.ps1 `
    -Url "file:///D:/Develop/bms/文档/设计/原型设计/02_通用骨架/03_主框架.html" `
    -Out "out.png" [-Width 1440] [-Height 900] [-Budget 3000]

参数：
  Url     必填，file:// 本地路径或 http(s) URL
  Out     必填，PNG 输出路径
  Width   窗口宽度，默认 1440
  Height  窗口高度，默认 900
  Budget  渲染等待毫秒数（动画/角标模拟），默认 3000
#>
param(
  [Parameter(Mandatory = $true)][string]$Url,
  [Parameter(Mandatory = $true)][string]$Out,
  [int]$Width = 1440,
  [int]$Height = 900,
  [int]$Budget = 3000
)

$candidates = @(
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
  "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)
$exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) { Write-Error "未找到 Edge/Chrome"; exit 1 }

$outDir = Split-Path -Parent $Out
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

& $exe --headless --disable-gpu --screenshot="$Out" --window-size="$Width,$Height" --virtual-time-budget=$Budget $Url 2>&1 | Out-Null

if (Test-Path $Out) { Write-Output "OK: $Out" } else { Write-Error "截图失败: $Out"; exit 1 }
