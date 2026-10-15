# 回退 rEFInd 双系统引导改动（需管理员运行）
# 2026-10-15 部署时的回退脚本；按当前固件状态动态定位，不写死 GUID。
$ErrorActionPreference = 'Continue'
$log = 'C:\ProgramData\BootSwitch\rollback.log'
function Log([string]$m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m"
    Write-Host $line
    try { $line | Add-Content -Path $log -Encoding utf8 } catch { }
}
Log '=== rollback started ==='

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Log 'ERROR: 需要管理员权限，请右键“以管理员身份运行”'; exit 1 }

$G = '{8BE4DF61-93CA-11D2-AA0D-00E098032B8C}'
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class UefiRb {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern uint GetFirmwareEnvironmentVariableExW(string lpName, string lpGuid, byte[] pBuffer, uint nSize, out uint pdwAttributes);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool SetFirmwareEnvironmentVariableExW(string lpName, string lpGuid, byte[] pValue, uint nSize, uint dwAttributes);
    public static uint ReadVar(string name, string guid, byte[] buf, uint size, out uint attrs, out int err) {
        uint n = GetFirmwareEnvironmentVariableExW(name, guid, buf, size, out attrs);
        err = Marshal.GetLastWin32Error();
        return n;
    }
    public static int WriteVar(string name, string guid, byte[] val, uint len, uint attrs) {
        return SetFirmwareEnvironmentVariableExW(name, guid, val, len, attrs) ? 0 : Marshal.GetLastWin32Error();
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct LUID { public uint LowPart; public int HighPart; }
    [StructLayout(LayoutKind.Sequential)]
    private struct LUID_AND_ATTRIBUTES { public LUID Luid; public uint Attributes; }
    [StructLayout(LayoutKind.Sequential)]
    private struct TOKEN_PRIVILEGES { public uint PrivilegeCount; public LUID_AND_ATTRIBUTES Privileges; }
    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool OpenProcessToken(IntPtr h, uint acc, out IntPtr tok);
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool LookupPrivilegeValueW(string sys, string name, out LUID luid);
    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool AdjustTokenPrivileges(IntPtr tok, bool dis, ref TOKEN_PRIVILEGES np, uint len, IntPtr prev, IntPtr ret);
    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();
    public static int EnablePrivilege(string name) {
        IntPtr tok;
        if (!OpenProcessToken(GetCurrentProcess(), 0x0020 | 0x0008, out tok)) return Marshal.GetLastWin32Error();
        LUID luid;
        if (!LookupPrivilegeValueW(null, name, out luid)) return Marshal.GetLastWin32Error();
        TOKEN_PRIVILEGES tp = new TOKEN_PRIVILEGES();
        tp.PrivilegeCount = 1; tp.Privileges.Luid = luid; tp.Privileges.Attributes = 0x00000002;
        if (!AdjustTokenPrivileges(tok, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero)) return Marshal.GetLastWin32Error();
        return 0;
    }
}
"@
$null = [UefiRb]
$priv = [UefiRb]::EnablePrivilege('SeSystemEnvironmentPrivilege')
Log "EnablePrivilege rc=$priv"

function Get-V([string]$n) {
    $b = New-Object byte[] 4096; $a = [uint32]0; $e = [int]0
    $len = [UefiRb]::ReadVar($n, $G, $b, [uint32]4096, [ref]$a, [ref]$e)
    if ($len -eq 0) { return $null }
    $d = New-Object byte[] $len; [Array]::Copy($b, $d, $len); return $d
}

# 1) 删除 rEFInd 固件项（按描述动态定位；用 bcdedit /delete，因为 Windows 不允许
#    以 0 长度删除 EFI 变量——实测 SetFirmwareEnvironmentVariableEx 返回 err=87）
$txt = (& bcdedit /enum firmware 2>&1) -join "`n"
$blocks = $txt -split "`r?`n`r?`n"
$removed = 0
foreach ($b in $blocks) {
    if (($b -match '固件应用程序|Firmware Application') -and ($b -match 'refind')) {
        $m = [regex]::Match($b, '(?m)^(标识符|identifier)\s+(\S+)')
        if ($m.Success) {
            $g = $m.Groups[2].Value
            Log "deleting firmware entry $g"
            $o = (& bcdedit /delete $g /f 2>&1) -join ' '
            Log "  -> $o"
            $removed++
        }
    }
}
Log "firmware entries removed: $removed"

# 2) 启动顺序恢复为 Windows -> Ubuntu
$order = @([uint16]0x0000, [uint16]0x0001)
$ob = New-Object byte[] 4
[Array]::Copy([BitConverter]::GetBytes($order[0]), 0, $ob, 0, 2)
[Array]::Copy([BitConverter]::GetBytes($order[1]), 0, $ob, 2, 2)
$eo = [UefiRb]::WriteVar('BootOrder', $G, $ob, [uint32]4, [uint32]0x7)
Log "restore BootOrder (Windows,Ubuntu) err=$eo"

# 3) 清除一次性 BootNext
$null = (& bcdedit /deletevalue '{fwbootmgr}' bootsequence 2>&1)
Log 'cleared BootNext'

# 4) 删除 ESP 上的 rEFInd 目录
$espVol = '\\?\Volume{59c60ed9-37a8-42ac-baa5-263df1b95c3b}\'
try {
    if (Test-Path 'V:\') { $null = & mountvol 'V:' /D 2>&1 }
    $null = & mountvol 'V:' $espVol 2>&1
    if (Test-Path 'V:\EFI\refind') {
        Remove-Item 'V:\EFI\refind' -Recurse -Force -ErrorAction Stop
        Log 'removed V:\EFI\refind'
    } else { Log 'V:\EFI\refind not present' }
    $null = & mountvol 'V:' /D 2>&1
} catch { Log "ESP cleanup error: $($_.Exception.Message)" }

# 5) 删除计划任务与桌面快捷方式
try { Unregister-ScheduledTask -TaskName 'BootSwitch-RebootToUbuntu' -Confirm:$false -ErrorAction Stop; Log 'task removed' } catch { Log "task: $($_.Exception.Message)" }
try {
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) '重启到 Ubuntu.lnk'
    if (Test-Path -LiteralPath $lnk) { Remove-Item -LiteralPath $lnk -Force; Log 'shortcut removed' } else { Log 'shortcut not present' }
} catch { Log "shortcut: $($_.Exception.Message)" }

# 6) 保留脚本目录（含本回退脚本自身与日志），仅删除一键重启脚本
try {
    $tu = 'C:\ProgramData\BootSwitch\ToUbuntu.ps1'
    if (Test-Path $tu) { Remove-Item $tu -Force; Log 'ToUbuntu.ps1 removed' }
} catch { Log "ToUbuntu: $($_.Exception.Message)" }

Log '=== rollback finished; reboot to take effect ==='