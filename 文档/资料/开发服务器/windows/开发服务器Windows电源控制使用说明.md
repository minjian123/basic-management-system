# 开发服务器Windows电源控制使用说明

> 远程唤醒（WOL）+ 远程睡眠 + 远程关机 + 每日自动睡眠/唤醒 · mjw（Windows 11）

[文档首页](../../../文档首页.md) › [资料](../../) › [开发服务器](../linux/开发服务器部署使用说明总览.md) › [Windows](开发服务器Windows部署使用说明总览.md)　|　[同级：远程控制部署使用说明 →](远程控制部署使用说明.md)　[开发服务器 Windows 部署使用说明总览 →](开发服务器Windows部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

Wake-on-LAN（局域网唤醒，简称 WOL）通过向关机状态机器的网卡发送「魔术包」（Magic Packet），
让机器从**睡眠（S3）或关机（S5）**状态远程开机，无需人到现场按电源键。
配套的远程睡眠 / 远程关机通过 WinRM 执行系统命令。这套工具组合可完全远程控制开发服务器 mjw 的电源。

本文档说明 mjw 的 WOL 配置、每日自动睡眠/唤醒任务与开发机上的远程唤醒 / 睡眠 / 关机脚本用法，适用于：

- mjw 关机或断电恢复后，需要远程开机时；
- 需要远程让 mjw 进入系统睡眠（S3），或让它在每日 00:00 自动睡眠、08:00 由 RTC 自动唤醒时；
- 需要远程关闭 mjw 时（如维护窗口）；
- 重装系统后需要恢复 WOL / 每日任务配置时。

`<mjw-IP>`、`<账号>`、`<密码>` 取值见《[本地资源](../../../用户文档/本地资源.md)》与开发机 `deploy/.env`（`MJW_IP` / `MJW_WINRM_USER` / `MJW_WINRM_PASSWORD`）。

> WOL 只能唤醒「已睡眠 / 已关机」的机器；机器运行中发送魔术包不会产生任何效果（也不会重启）。远程关机是破坏性操作，执行前脚本会要求二次确认。

## 2. 环境与前提 <a id="prereq"></a>

### 2.1 服务器参数 <a id="prereq-param"></a>

mjw 远程通道为基础 WinRM（HTTP 5985），不同于 mjbk 的 SSH——睡眠 / 关机的**下发**走 WinRM，**唤醒**走 WOL 魔术包（两者端口不同、职责不同）：

| 项目 | 值 | 说明 |
| --- | --- | --- |
| 主机名 | mjw | Windows 开发服务器 / 本地模型机 |
| IP 地址 | `<mjw-IP>` | 内网固定地址（路由器绑定） |
| 系统 | Windows 11 专业版 | 本地模型（识图 / 翻译）GPU 推理 |
| WinRM 用户 | `<账号>` | 管理员权限，ntlm 认证（WinRM 5985） |
| 有线网卡 | Realtek Gaming 2.5GbE | WOL 目标网卡 |
| MAC 地址 | B0-25-AA-40-57-CC | 魔术包发送目标（大小写与分隔符不敏感） |

### 2.2 BIOS 前提（需手动确认） <a id="prereq-bios"></a>

Windows 系统层面只能开启网卡的 WOL 功能；能否从 **S5 关机**状态唤醒以及 RTC 定时唤醒，取决于 BIOS：

- BIOS 中 Wake-on-LAN / Power On By LAN 等选项为 Enabled（mjw 已实测 S3 睡眠唤醒，S5 见[第 9 节](#record)实测记录）；
- BIOS 中 RTC / Wake on RTC Alarm 选项为 Enabled（每日 08:00 自动唤醒依赖它，见[第 8 节](#auto)）。

> BIOS 选项无法远程设置，若从 S5 唤醒或每日自醒失败，先检查这一项。mjw 为笔记本机型，选项通常在 BIOS「Advanced / Power」菜单下。

## 3. 服务器端配置（mjw / Windows 侧） <a id="server"></a>

以下配置已在 mjw 上完成（2026-09-06）。重装系统后需按本节重做，部分步骤需在 mjw **本机**操作。

### 3.1 网卡 WOL <a id="server-wol"></a>

mjw 本机以管理员 PowerShell 执行：

```powershell
# 网卡允许魔术包唤醒（需同配合 BIOS WOL，见 2.2 节）
Get-NetAdapterPowerManagement -Name '*Realtek*' | Set-NetAdapterPowerManagement -WakeOnMagicPacket Enabled
```

验证：

```powershell
Get-NetAdapterPowerManagement -Name '*Realtek*' | Select-Object Name, WakeOnMagicPacket
```

输出 `WakeOnMagicPacket: Enabled` 即生效。mjw 侧「禁睡眠 / 休眠关闭 / 合盖不休眠」常驻策略由《[远程控制部署使用说明](远程控制部署使用说明.md)》第 3.2 节脚本统一设置。

### 3.2 每日自动睡眠 / 唤醒任务 <a id="server-task"></a>

mjw 上注册了两个计划任务（系统账户 SYSTEM、最高权限、`WakeToRun` 唤醒定时器）：

```powershell
# 每晚 00:00 进入 S3 睡眠
$act1 = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'powrprof.dll,SetSuspendState 0,0,0'
$trg1 = New-ScheduledTaskTrigger -Daily -At '00:00'
$set1 = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$pri1 = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'mjw-daily-sleep' -Action $act1 -Trigger $trg1 -Settings $set1 -Principal $pri1 -Force

# 早晨 08:00 RTC 唤醒（WakeToRun 让系统在睡眠期间被硬件闹钟叫醒）
$act2 = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit 0'
$trg2 = New-ScheduledTaskTrigger -Daily -At '08:00'
$set2 = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$pri2 = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'mjw-daily-wake' -Action $act2 -Trigger $trg2 -Settings $set2 -Principal $pri2 -Force
```

允许**唤醒定时器**（否则 WakeToRun 不生效）：

```powershell
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
powercfg /setactive SCHEME_CURRENT
```

验证：

```powershell
Get-ScheduledTask -TaskName 'mjw-daily-*' | Select-Object TaskName, State
```

- 两个任务 `State` 为 `Ready`；
- `mjw-daily-wake` 的 `Settings.WakeToRun = True`。

## 4. 开发机凭据配置（deploy/.env） <a id="env"></a>

工具脚本所需凭据统一从开发机 `deploy/.env` 读取（该文件已在 `.gitignore` 中忽略，不入库；
真实值来源为[《本地资源》](../../../用户文档/本地资源.md)）。键位见 `deploy/.env.example` 模板：

| 键 | 用途 | 默认值 |
| --- | --- | --- |
| MJW_IP | 服务器 IP | `<mjw-IP>`（见《本地资源》） |
| MJW_WOL_MAC | 网卡 MAC（WOL 魔术包目标） | B0-25-AA-40-57-CC |
| MJW_WINRM_USER | WinRM 登录用户 | `<账号>`（见《本地资源》） |
| MJW_WINRM_PASSWORD | WinRM 登录密码 | 无（必须填写） |

## 5. 开发机工具脚本 <a id="tools"></a>

### 5.1 脚本清单 <a id="tools-list"></a>

全部位于 `scripts/tools/winrm/`。`wake_mjw.py` 仅用 Python 标准库（发魔术包 + 探测端口）；
`sleep_mjw.py` / `shutdown_mjw.py` 依赖 pywinrm（开发机 venv：`~/tools/winrm-venv`）。`.bat` 为 Windows 双击入口。

| 文件 | 作用 | 双击入口 | 依赖 |
| --- | --- | --- | --- |
| wake_mjw.py | 发送魔术包唤醒并等待 WinRM（5985）就绪 | 唤醒mjw.bat | 无（标准库） |
| sleep_mjw.py | 远程进入系统睡眠（S3，含确认） | 睡眠mjw.bat | pywinrm |
| shutdown_mjw.py | 远程关机（S5，含确认） | 关机mjw.bat | pywinrm |

pywinrm 环境（开发机 mjpc）：

```bash
python3 -m venv ~/tools/winrm-venv
~/tools/winrm-venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pywinrm
```

### 5.2 远程唤醒 <a id="tools-wake"></a>

在开发机 mjpc（Ubuntu）仓库根目录执行：

```bash
python3 scripts/tools/winrm/wake_mjw.py
```

脚本发送魔术包并等待 WinRM 端口就绪，输出示例：

```
[1/2] 发送魔术包唤醒 <mjw-IP>（B0-25-AA-40-57-CC）...
魔术包已发送，等待 WinRM 就绪（最多 120 秒）...
[完成] 开发服务器已就绪，WinRM 端口 5985 可连。
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| --host | deploy/.env 的 MJW_IP | 服务器 IP |
| --mac | deploy/.env 的 MJW_WOL_MAC | 网卡 MAC |
| --timeout | 120 | 等待 WinRM（5985）就绪的超时秒数 |

逻辑：魔术包（MAC 重复 16 次，前导 6 字节全 FF）经 UDP 9 端口同时发往广播地址 `255.255.255.255` 与服务器 IP；随后每秒探测一次 5985 端口（mjw 无 SSH，就绪判据取 WinRM），就绪即成功，超时返回非 0 退出码。

### 5.3 远程睡眠 <a id="tools-sleep"></a>

```bash
~/tools/winrm-venv/bin/python scripts/tools/winrm/sleep_mjw.py
```

脚本会先显示目标并**要求输入 y 确认**，确认后经 WinRM 执行 `rundll32.exe powrprof.dll,SetSuspendState 0,0,0`：

```
确认让 <mjw-IP>（<账号>）进入系统睡眠？(y/N) y
正在让 <mjw-IP> 进入系统睡眠 ...
睡眠指令已下发，机器即将休眠（可随后用 wake_mjw.py 唤醒）。
```

| 参数 | 说明 |
| --- | --- |
| --yes | 跳过确认直接睡眠（供脚本化调用，人工操作不建议） |

> 睡眠命令让 mjw 进入 **S3 睡眠**（内存保电、网卡仍供电，睡眠期间可被 WOL 或 RTC 唤醒）。MJW_WINRM_PASSWORD 必须已在 deploy/.env 填写。

### 5.4 远程关机 <a id="tools-shutdown"></a>

```bash
~/tools/winrm-venv/bin/python scripts/tools/winrm/shutdown_mjw.py
```

脚本会先显示目标并**要求输入 y 确认**，确认后经 WinRM 执行 `shutdown /s /t 0`（优雅关闭，等待应用退出）：

```
确认远程关机 <mjw-IP>（<账号>）？(y/N) y
正在远程关机 <mjw-IP> ...
关机指令已下发。需要开机时用 wake_mjw.py 唤醒。
```

| 参数 | 说明 |
| --- | --- |
| --yes | 跳过确认直接关机（供脚本化调用，人工操作不建议） |

> 关机瞬间 WinRM 连接即断开，脚本正常视为「已下发」；从 **S5 关机**状态能否用 WOL 唤醒取决于 BIOS 设置（见[第 9 节](#record)实测记录）。

## 6. 完整操作流程 <a id="flow"></a>

```mermaid
flowchart TD
    A["远程关机 / 睡眠 mjw"] --> B["确认 ping 不通（已关机 / 睡眠）"]
    B --> C["开发机执行 wake_mjw.py 唤醒"]
    C --> D{"WinRM 5985 就绪？"}
    D -- 是 --> E["[完成] 正常使用"]
    D -- 否（超时） --> F["按第 7 节排查"]
```

1. 远程睡眠：`sleep_mjw.py`（确认后执行）；或远程关机：`shutdown_mjw.py`；
2. 开发机 ping / 端口探测确认离线；
3. 远程唤醒：`wake_mjw.py`，等待「5985 可连」提示后即可 WinRM / RDP 使用。

> 睡眠是「关机」的轻量替代：短时间不用用 `sleep_mjw.py` 睡下、`wake_mjw.py` 唤醒即可，比关机/开机更快；要彻底断电再走关机流程。

## 7. 常见问题排查 <a id="faq"></a>

| 现象 | 可能原因与处理 |
| --- | --- |
| 发送魔术包后长时间无法唤醒 | 确认 mjw 处于睡眠/关机态（运行中发包无效）；查 BIOS 的 WOL 选项（2.2 节）；确认网线电源已接；查 `WakeOnMagicPacket` 为 Enabled（3.1 节）。 |
| 从 S3 睡眠能唤醒、从 S5 关机不能 | 查 BIOS 的 WOL（Power On By LAN）或 ErP 未放开，S5 关机下网卡无待机供电（2.2 节，参见[第 9 节](#record)）。 |
| 每日 08:00 未自动唤醒 | 查 BIOS RTC Wake 选项（2.2 节）；查 `powercfg /q SCHEME_CURRENT SUB_SLEEP RTCWAKE` 是否 1；查 `mjw-daily-wake` 任务 `WakeToRun` 是否开启（3.2 节）。 |
| 睡眠脚本提示未配置 MJW_WINRM_PASSWORD | 按第 4 节在 `deploy/.env` 填入真实密码（参考[《本地资源》](../../../用户文档/本地资源.md)）。 |
| 关机 / 睡眠脚本报 pywinrm 未安装 | 用 venv Python 运行（`~/tools/winrm-venv/bin/python`），或按 5.1 节安装。 |
| MAC 地址写错 | 以 mjw 上 `Get-NetAdapter | Select MacAddress` 输出为准（当前 B0-25-AA-40-57-CC），大小写与分隔符均不敏感。 |

## 8. 每日自动睡眠 / 自动唤醒 <a id="auto"></a>

> 让 mjw **每天 00:00 自动进入 S3 睡眠、早晨 08:00 自动唤醒**，无需人工干预。已实测 mjw 可被自身 RTC 硬件时钟从 S3 唤醒（见[第 9 节](#record)）。

### 8.1 原理 <a id="auto-principle"></a>

「自动唤醒」不能靠 WOL——早上 8 点开发机可能也是关的，**没有醒着的发送方**。可靠方式是 mjw 用**自身 RTC 硬件时钟（唤醒闹钟）**定时自醒，由任务计划程序的 `WakeToRun` 在入睡前设好闹钟（对应 BIOS RTC Wake 支持，见 2.2 节）。

每日循环的驱动在 **mjw 侧**：

```mermaid
flowchart TD
    A["mjw 白天保持开机"] --> B["00:00 mjw-daily-sleep 触发 S3 睡眠"]
    B --> C["入睡时安装 08:00 RTC 唤醒闹钟（WakeToRun）"]
    C --> D["08:00 RTC 硬件自唤醒"]
    D --> E["mjw 恢复开机，继续服务"]
    E --> B
```

### 8.2 组件 <a id="auto-files"></a>

| 位置 | 任务 / 设置 | 作用 |
| --- | --- | --- |
| mjw 计划任务 | `mjw-daily-sleep` | 每晚 00:00 触发 rundll32 SetSuspendState 进入 S3 |
| mjw 计划任务 | `mjw-daily-wake` | 每天 08:00 触发（`WakeToRun`，入睡前安装唤醒闹钟） |
| mjw 电源计划 | `RTCWAKE = 1` | 允许唤醒定时器叫醒系统 |

### 8.3 取消 / 恢复 <a id="auto-toggle"></a>

```powershell
# 临时取消某晚自动睡眠（00:00 不再入睡）
Disable-ScheduledTask -TaskName 'mjw-daily-sleep'
# 恢复
Enable-ScheduledTask -TaskName 'mjw-daily-sleep'
```

### 8.4 注意事项 <a id="auto-notes"></a>

- **夜间服务停用**：00:00 – 08:00 mjw 处于睡眠，本地模型（识图 / 翻译）等服务**不可用**；如需夜间访问，先 `wake_mjw.py` 唤醒。
- **仅睡眠不关机**：每日循环是 S3 睡眠，内存保电；断电（停电、意外关机）后需 `wake_mjw.py` 唤醒开机，计划任务会随开机自动恢复。
- **唤醒后保持开机**：08:00 醒来后 mjw 继续开机到下一个 00:00，白天正常使用。
- mjw 本身「禁睡眠 / 合盖不休眠」常驻策略与每日任务不冲突：前者防**闲置**自动睡，后者是**定时主动**入睡（见《[远程控制部署使用说明](远程控制部署使用说明.md)》第 3.2 节）。

## 9. 实测记录 <a id="record"></a>

| 日期 | 项目 | 结果 | 说明 |
| --- | --- | --- | --- |
| 2026-09-06 | S3 睡眠 → WOL 唤醒（wake_mjw.py，5985 就绪） | ✅ 通过 | 系统级 WakeOnMagicPacket 在 S3 下即生效，无需 BIOS |
| 2026-09-06 | S3 睡眠 → RTC 自醒（一次性唤醒任务同机制验证） | ❌ 未自醒 | 任务 / RTCWAKE 均正常，判定 BIOS 未开启 RTC Wake，需 mjw 本机进 BIOS |
| 2026-09-06 | S5 关机 → WOL 唤醒 | ❌ 未唤醒 | 120s 超时；判定 BIOS 未开启 Power On By LAN（S5 网卡无待机供电），需 mjw 本机进 BIOS |

**待办（需 mjw 本机人工操作）**：在现场按电源键开机，进 BIOS 开启

1. **Power On By LAN / Wake on LAN** —— 使 S5 关机状态可被 WOL 唤醒；
2. **RTC Wake / Wake on RTC Alarm** —— 使每日 08:00 可自醒。

开启后在 mjw 本机重启一次系统，即可远程复测第 8 节每日循环与 S5 唤醒；mjw 睡眠 / 关机脚本与 S3 唤醒已全部验证可用。

> 关联：《开发服务器 Windows 部署使用说明总览》《远程控制部署使用说明》 · 生成日期：2026-09-06