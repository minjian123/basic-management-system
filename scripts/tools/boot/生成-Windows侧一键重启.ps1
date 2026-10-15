# 生成 Windows 侧「重启到 Ubuntu」快捷方式与计划任务（需管理员运行）
#
# 用途：重建开发机 mjpc 上的一键重启进 Ubuntu 能力（重装系统或误删后使用）。
# 机制：桌面快捷方式 → 计划任务（SYSTEM，免 UAC）→ 写 UEFI BootNext 指向 Ubuntu → 重启。
#       BootNext 只生效一次，之后回到默认启动顺序。
#
# 注意：本文件必须保存为 UTF-8 **带 BOM**，否则 Windows PowerShell 5.1 会按 GBK 解码中文并报语法错误。
# 完整说明见 bms文档/资料/开发机/双系统引导部署使用说明.md

[CmdletBinding()]
param(
    # Ubuntu 的 UEFI 启动项编号（十六进制，四位）。默认 0001。
    [string]$UbuntuBootNum = '0001',
    # 生成后是否立即做一次端到端自检（写 BootNext 后立刻清除，不重启）
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'

# ---------- 0. 管理员检查 ----------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Error '需要管理员权限，请右键“以管理员身份运行”。'; exit 1 }

Write-Host '== 生成「重启到 Ubuntu」快捷方式与计划任务 ==' -ForegroundColor Cyan
$bsDir = 'C:\ProgramData\BootSwitch'
New-Item -ItemType Directory -Force -Path $bsDir | Out-Null

# ---------- 1. 写入 ToUbuntu.ps1 ----------
$script = @'
param([switch]$Run)

$bsDir = 'C:\ProgramData\BootSwitch'
$log = Join-Path $bsDir 'bootswitch.log'
function Log([string]$m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -Path $log -Encoding utf8 }

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class UefiNext {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool SetFirmwareEnvironmentVariableExW(string lpName, string lpGuid, byte[] pValue, uint nSize, uint dwAttributes);

    public static int Write(string name, string guid, byte[] val, uint len, uint attrs) {
        return SetFirmwareEnvironmentVariableExW(name, guid, val, len, attrs) ? 0 : Marshal.GetLastWin32Error();
    }

    // 写 EFI 变量必须显式启用 SeSystemEnvironmentPrivilege；
    // 即使进程以 SYSTEM/管理员运行也不会自动获得（否则返回 1314）。
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
        tp.PrivilegeCount = 1;
        tp.Privileges.Luid = luid;
        tp.Privileges.Attributes = 0x00000002;
        if (!AdjustTokenPrivileges(tok, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero)) return Marshal.GetLastWin32Error();
        return 0;
    }
}
"@

if (-not $Run) {
    Add-Type -AssemblyName System.Windows.Forms
    $r = [System.Windows.Forms.MessageBox]::Show(
        "确定要重启并进入 Ubuntu 吗？" + [char]13 + [char]10 + [char]13 + [char]10 + "请先保存所有未保存的工作。",
        '重启到 Ubuntu',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question,
        [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
    if ($r -ne [System.Windows.Forms.DialogResult]::Yes) { Log 'cancelled by user'; exit 0 }
    Log 'user confirmed; triggering scheduled task'
    $p = Start-Process -FilePath 'schtasks.exe' -ArgumentList '/run', '/tn', 'BootSwitch-RebootToUbuntu' -Wait -PassThru -WindowStyle Hidden
    Log ("schtasks exit=" + $p.ExitCode)
    exit 0
}

Log 'elevated run: setting BootNext to Ubuntu'
$EFI_GLOBAL = '{8BE4DF61-93CA-11D2-AA0D-00E098032B8C}'

$priv = [UefiNext]::EnablePrivilege('SeSystemEnvironmentPrivilege')
Log ("EnablePrivilege rc=" + $priv)

$err = [UefiNext]::Write('BootNext', $EFI_GLOBAL, [byte[]](__UBUNTU_LO__, __UBUNTU_HI__), 2, 0x7)
Log ("WriteVar BootNext err=" + $err)

if ($err -eq 0) {
    Log 'rebooting in 5 seconds'
    & shutdown.exe /r /t 5 /c 'Rebooting into Ubuntu'
} else {
    Log 'FAILED to set BootNext - aborting reboot'
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "设置下次启动项失败（错误码 $err），已取消重启。请查看日志：" + [char]13 + [char]10 + $log,
        '重启到 Ubuntu 失败',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}
'@

# 注入 Ubuntu 启动项编号（小端）
$num = [Convert]::ToInt32($UbuntuBootNum, 16)
$lo = '0x{0:X2}' -f ($num -band 0xFF)
$hi = '0x{0:X2}' -f (($num -shr 8) -band 0xFF)
$script = $script.Replace('__UBUNTU_LO__', $lo).Replace('__UBUNTU_HI__', $hi)

# 关键：UTF-8 带 BOM
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
$scriptPath = Join-Path $bsDir 'ToUbuntu.ps1'
[System.IO.File]::WriteAllText($scriptPath, $script, $utf8Bom)
Write-Host "  已写入 $scriptPath (BootNext -> $UbuntuBootNum)" -ForegroundColor Green

# 语法自检（用 PS 5.1，即实际执行环境）
$ps51 = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$parseCmd = "`$e=`$null; [void][System.Management.Automation.Language.Parser]::ParseFile('$scriptPath',[ref]`$null,[ref]`$e); if(`$e){`$e.Count}else{0}"
$errCount = (& $ps51 -NoProfile -Command $parseCmd 2>&1 | Select-Object -Last 1)
if ($errCount -ne 0) { Write-Error "生成的脚本有 $errCount 个语法错误（编码或内容问题）"; exit 1 }
Write-Host '  语法自检通过（PowerShell 5.1）' -ForegroundColor Green

# ---------- 2. 计划任务 ----------
# 以 SYSTEM 运行可免 UAC，但 Register-ScheduledTask 默认只给 管理员/SYSTEM 访问权，
# 普通用户（双击快捷方式时的身份）既不能 /run 也不能 /query，表现为「弹了确认框但没反应」。
# 因此注册后必须再用 COM 追加 Authenticated Users 的读+执行权限（实测必需）。
$act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Run"
$pri = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'BootSwitch-RebootToUbuntu' -Action $act -Principal $pri -Settings $set -Force | Out-Null

# 追加普通用户可运行权限（GRGX = Generic Read + Generic Execute）
try {
    $svc = New-Object -ComObject Schedule.Service
    $svc.Connect()
    $taskObj = $svc.GetFolder('\').GetTask('BootSwitch-RebootToUbuntu')
    $sd = $taskObj.GetSecurityDescriptor(0xF)
    if ($sd -notmatch ';;;AU\)') {
        $taskObj.SetSecurityDescriptor(($sd -replace 'D:', 'D:(A;;GRGX;;;AU)'), 0)
        Write-Host '  已授予普通用户运行权限（否则双击无反应）' -ForegroundColor Green
    } else {
        Write-Host '  普通用户运行权限已存在' -ForegroundColor Green
    }
} catch {
    Write-Warning "授予普通用户运行权限失败（双击可能无反应）：$($_.Exception.Message)"
}
Write-Host '  计划任务 BootSwitch-RebootToUbuntu 已注册（SYSTEM，免 UAC）' -ForegroundColor Green

# ---------- 3. 桌面 + 开始菜单快捷方式 ----------
$lnkName = '重启到 Ubuntu.lnk'
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) $lnkName),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$lnkName")
)
$ws = New-Object -ComObject WScript.Shell
foreach ($t in $targets) {
    $lnk = $ws.CreateShortcut($t)
    $lnk.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
    $lnk.WorkingDirectory = $bsDir
    $lnk.Description = '重启并进入 Ubuntu（会先弹确认框，只生效一次）'
    $lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,27"
    $lnk.Save()
    Write-Host "  已创建 $t" -ForegroundColor Green
}

# ---------- 4. 可选自检 ----------
if ($SelfTest) {
    Write-Host '  自检：写入 BootNext 后立即清除（不会重启）...' -ForegroundColor Cyan
    # 注意：自检必须与正式脚本一样显式启用 SeSystemEnvironmentPrivilege，
    # 否则会得到 err=1314 的假失败（SYSTEM/管理员身份并不自动带该权限）。
    $tmp = Join-Path $bsDir 'selftest.ps1'
    $st = @"
`$G = '{8BE4DF61-93CA-11D2-AA0D-00E098032B8C}'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class St {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool SetFirmwareEnvironmentVariableExW(string n, string g, byte[] v, uint s, uint a);
    public static int W(string n, string g, byte[] v, uint s, uint a) { return SetFirmwareEnvironmentVariableExW(n, g, v, s, a) ? 0 : Marshal.GetLastWin32Error(); }
    [StructLayout(LayoutKind.Sequential)] private struct LUID { public uint LowPart; public int HighPart; }
    [StructLayout(LayoutKind.Sequential)] private struct LA { public LUID Luid; public uint Attributes; }
    [StructLayout(LayoutKind.Sequential)] private struct TP { public uint PrivilegeCount; public LA Privileges; }
    [DllImport("advapi32.dll", SetLastError = true)] private static extern bool OpenProcessToken(IntPtr h, uint a, out IntPtr t);
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)] private static extern bool LookupPrivilegeValueW(string s, string n, out LUID l);
    [DllImport("advapi32.dll", SetLastError = true)] private static extern bool AdjustTokenPrivileges(IntPtr t, bool d, ref TP n, uint l, IntPtr p, IntPtr r);
    [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentProcess();
    public static int Enable(string name) {
        IntPtr t; if (!OpenProcessToken(GetCurrentProcess(), 0x20 | 0x8, out t)) return Marshal.GetLastWin32Error();
        LUID l; if (!LookupPrivilegeValueW(null, name, out l)) return Marshal.GetLastWin32Error();
        TP tp = new TP(); tp.PrivilegeCount = 1; tp.Privileges.Luid = l; tp.Privileges.Attributes = 2;
        if (!AdjustTokenPrivileges(t, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero)) return Marshal.GetLastWin32Error();
        return 0;
    }
}
'@
`$p = [St]::Enable('SeSystemEnvironmentPrivilege')
Write-Host "      EnablePrivilege rc=`$p"
`$e = [St]::W('BootNext', `$G, [byte[]]($lo, $hi), 2, 0x7)
Write-Host "      write err=`$e  (0 = 成功)"
"@
    [System.IO.File]::WriteAllText($tmp, $st, $utf8Bom)
    & $ps51 -NoProfile -ExecutionPolicy Bypass -File $tmp
    & bcdedit /deletevalue '{fwbootmgr}' bootsequence | Out-Null
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    Write-Host '  已清除 BootNext，自检结束' -ForegroundColor Green
}

Write-Host ''
Write-Host '完成。双击桌面「重启到 Ubuntu」即可（会先弹确认框）。' -ForegroundColor Cyan
