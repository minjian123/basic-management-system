# 校验 scripts/tools/boot/ 下脚本的编码与语法（改动脚本后必须运行）
#
# 为什么需要：Windows 侧 .ps1 若为「无 BOM 的 UTF-8」，Windows PowerShell 5.1
# 会按系统 ANSI（中文环境 GBK）解码，中文注释/字符串被解码坏后破坏语法，脚本
# 直接解析失败（实测可达 67 个解析错误）。许多编辑器/工具写回文件时会丢失 BOM，
# 因此每次编辑后都要重新校验并补回 BOM。
#
# 用法（管理员非必需）：powershell -File 校验脚本编码.ps1

$ErrorActionPreference = 'Continue'
$dir = $PSScriptRoot
$ps51 = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$fail = 0

Write-Host "校验目录: $dir" -ForegroundColor Cyan
Write-Host ''

function Test-Bom([string]$p) {
    $b = [System.IO.File]::ReadAllBytes($p)
    return ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)
}

foreach ($f in Get-ChildItem $dir -File) {
    switch ($f.Extension) {
        '.ps1' {
            $hasBom = Test-Bom $f.FullName
            $cmd = "`$e=`$null; [void][System.Management.Automation.Language.Parser]::ParseFile('$($f.FullName)',[ref]`$null,[ref]`$e); if(`$e){`$e.Count}else{0}"
            $errs = (& $ps51 -NoProfile -Command $cmd 2>&1 | Select-Object -Last 1)
            $ok = $hasBom -and ("$errs" -eq '0')
            if (-not $ok) { $fail++ }
            $color = if ($ok) { 'Green' } else { 'Red' }
            Write-Host ("  {0,-34} BOM={1,-6} PS5.1错误={2}  {3}" -f $f.Name, $hasBom, $errs, $(if ($ok) { 'OK' } else { '<== 需修复' })) -ForegroundColor $color
            if (-not $hasBom) {
                Write-Host "     修复：把文件另存为 UTF-8 带 BOM（或运行本目录的修复逻辑）" -ForegroundColor Yellow
            }
        }
        '.sh' {
            $txt = [System.IO.File]::ReadAllText($f.FullName)
            $crlf = $txt -match "`r`n"
            $ok = -not $crlf
            if (-not $ok) { $fail++ }
            Write-Host ("  {0,-34} CRLF={1,-6}  {2}" -f $f.Name, $crlf, $(if ($ok) { 'OK' } else { '<== 应为 LF' })) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
        }
        default {
            Write-Host ("  {0,-34} (跳过)" -f $f.Name) -ForegroundColor DarkGray
        }
    }
}

Write-Host ''
if ($fail -eq 0) { Write-Host '全部通过。' -ForegroundColor Green }
else { Write-Host "$fail 个文件需修复。" -ForegroundColor Red; exit 1 }
