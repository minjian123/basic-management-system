# WSL 部署使用说明

> 开发机 mjpc · Windows 侧 WSL2（Ubuntu 26.04.1）与「只读挂载双系统 Ubuntu 盘」

[文档首页](../../文档首页.md) › 资料 › 开发机 › WSL 部署使用说明　|　[双系统引导部署使用说明 ←](双系统引导部署使用说明.md)　[开发机部署使用说明总览（Windows 侧）→](windows/开发机部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

开发机 mjpc 是 Windows 11 与 Ubuntu 双系统机器。本文档记录 **Windows 侧 WSL2 的部署方式**，以及用它**只读挂载双系统 Ubuntu 盘**——即「**不进 Linux 系统，也能在 Windows 下读 Ubuntu 分区里的文件**」这套能力（WSL2 支持把物理盘直接挂进发行版）。

| 想做的事 | 用什么 |
| --- | --- |
| 读 / 比对 Ubuntu 侧的文件（日志、配置、仓库副本、备份） | **本文档**：WSL 只读挂载，不重启、不切系统 |
| 在 Linux 里改文件、跑开发环境、装软件 | 切到 Ubuntu（见《[双系统引导部署使用说明](双系统引导部署使用说明.md)》「一键切换」节） |
| 只看分区与文件系统结构 | Windows「磁盘管理」，或本文档的只读挂载 |

两条刻意的口径：

- **只读**：Windows 侧不需要写 Ubuntu 盘（要写应当进 Linux 侧操作）。只读可避免误写，也避开 Linux 未干净关机时写入带来的不一致风险。
- **按需挂载**：不用时挂载不存在，因此不常驻内存、不占开机资源；需要时双击一次即可（4.2），代价是重启后要重挂。

本文档与《[开发机部署使用说明总览（Windows 侧）](windows/开发机部署使用说明总览.md)》配套——总览汇总 Windows 侧开发设施，本文档只讲 WSL 与「读 Ubuntu 盘」；双系统的引导与切系统见《[双系统引导部署使用说明](双系统引导部署使用说明.md)》。

**取值说明**：`<mjpc-IP>` 等占位符与账号凭据的真实值见《[本地资源](../../用户文档/本地资源.md)》，不在仓库文档中记录。

## 2. 环境与选型依据 <a id="env"></a>

### 2.1 现状 <a id="env-now"></a>

| 项 | 取值 |
| --- | --- |
| WSL | 3.0.3.0（内核 6.18.54.1-1，WSLg 1.0.79），默认版本 2 |
| 发行版 | `Ubuntu-26.04`（Ubuntu **26.04.1 LTS**，与双系统里那套同版本；`/etc/wsl.conf` 为 `[boot] systemd=true`，systemd 已启用） |
| 落盘位置 | `C:\Users\minjian\AppData\Local\wsl\{2d1cf05e-6a37-432c-b93f-f02ea0b5c50a}\ext4.vhdx`（默认位置，初始约 1.45 GB，随使用增长） |
| 默认用户 | `minjian`（uid 1000，在 `sudo` 组；与双系统 Ubuntu 侧**同名同 uid**，读盘权限天然对齐） |
| 挂载对象 | **磁盘 3 分区 2**（Ubuntu 的 ext4 根分区，3.8 TB），只读 |
| 挂载脚本 | `bms/scripts/tools/wsl/挂载Ubuntu盘.py`（+ 同名 `.bat` 双击包装）；桌面快捷方式「挂载 Ubuntu 盘」 |
| 官方镜像留存 | `D:\tools\操作系统\linux\ubuntu\ubuntu-26.04.1-wsl-amd64.wsl`（399 MB，重装可复用） |

### 2.2 为什么不用本地那张桌面 ISO <a id="why-not-iso"></a>

本机 `D:\tools\操作系统\linux\ubuntu\ubuntu-26.04-desktop-amd64.iso` 是**可启动光盘镜像**，而 WSL 发行版是**rootfs 打包**，两者结构不同：桌面 ISO **不能**直接给 `wsl --install` / `wsl --import` 使用，必须先解包 `casper/filesystem.squashfs`（非官方流程、体积大、无更新通道）。

WSL 用的官方镜像**是另一份文件**：`ubuntu-26.04.1-wsl-amd64.wsl`（同为 26.04.1 LTS）。因此本机路线是「下载 WSL 官方镜像 + 官方安装流程」，而不是从桌面 ISO 里掏 rootfs。

### 2.3 为什么经镜像源下载 <a id="why-mirror"></a>

官方源（`releases.ubuntu.com`，也就是 `wsl --install -d Ubuntu-26.04` 默认使用的那份）在国内实测很慢，镜像源则快一个量级：

| 来源 | 实测速度 | 399 MB 折合 |
| --- | --- | --- |
| 官方 `releases.ubuntu.com` | 约 200 KB/s | 约 35 分钟 |
| 阿里云镜像 | 约 210 KB/s | 同量级 |
| **清华 TUNA 镜像** | **约 35 MB/s** | 约 12 秒（本机实测 6.4 秒） |

两条路线的**文件是同一份**：WSL 官方发行版清单（`microsoft/WSL` 仓库的 `distributions/DistributionInfo.json`）给出 `Ubuntu-26.04` 的 Amd64 下载地址与 **SHA256**；清华镜像同步的正是该文件，下载后按该 SHA256 校验即可确认逐字节一致（见 3.1）。因此这不是「换了个来路不明的包」，而是**同一官方镜像换个更快的通道取回**。

### 2.4 挂载口径：只读 <a id="why-ro"></a>

```powershell
wsl --mount \\.\PHYSICALDRIVE3 --partition 2 --options ro
```

- 挂载点是**物理盘**（不是某个 Windows 卷），所以需要**管理员权限**。
- `--options ro` 让内核以只读挂载 ext4：写入会直接报 `Read-only file system`（预期行为，见 5.2）。
- **副作用（重要）**：整盘挂给 WSL 期间，**Windows 访问不到该盘的任何分区**（即磁盘 3 的分区 1 ESP 与分区 2 都读不到，磁盘管理里也动不了）。要动这些分区，先卸载（4.3）。

## 3. 部署 <a id="deploy"></a>

> 顺序即首次部署顺序；重装（比如换了机器/删了发行版）照此重做即可，镜像已留存可跳过 3.1 的下载。

### 3.1 下载官方镜像并校验 <a id="download"></a>

```powershell
$u = 'https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/26.04.1/ubuntu-26.04.1-wsl-amd64.wsl'
$o = 'D:\tools\操作系统\linux\ubuntu\ubuntu-26.04.1-wsl-amd64.wsl'
curl.exe -sL -o $o -w 'downloaded %{size_download} B in %{time_total}s' $u
(Get-FileHash -Algorithm SHA256 -LiteralPath $o).Hash
```

期望值（取自 WSL 官方清单中 `Ubuntu-26.04` 的 Amd64 条目）：`48D56724B5C8E60F24893E83E73BBB58C60B3CA22FBA3DA977075420ACD54104`。

### 3.2 从本地文件安装发行版（官方流程，免交互） <a id="install"></a>

```powershell
wsl --install --from-file 'D:\tools\操作系统\linux\ubuntu\ubuntu-26.04.1-wsl-amd64.wsl' --name Ubuntu-26.04 --no-launch
wsl --list --verbose
```

- **`--from-file` 走的是 WSL 官方安装流程**（相当于把在线安装的镜像换成手边这份），安装后发行版名 `Ubuntu-26.04`、版本 2，落盘在默认位置（2.1）。
- **`--no-launch` 必须加**：官方 Ubuntu 发行版首次启动会**交互式**要求建用户名/密码，无人值守流程会卡在那里；跳过首次启动后，直接由 3.3 建用户。
- 官方 Ubuntu 镜像是稳的：若安装后输出「已成功安装分发」，`wsl --list --verbose` 应能看到 `Ubuntu-26.04`。

### 3.3 建用户并设为默认 <a id="user"></a>

```powershell
wsl -d Ubuntu-26.04 -u root -- useradd -m -s /bin/bash -G sudo minjian
wsl -d Ubuntu-26.04 -u root -- bash -c 'echo minjian:minjian | chpasswd'   # 初始密码同用户名，首次登录后自行 passwd 改
wsl --manage Ubuntu-26.04 --set-default-user minjian
wsl -d Ubuntu-26.04 -- bash -lc 'id'    # 期望：uid=1000(minjian) ... 27(sudo)
```

> 用户**与双系统 Ubuntu 侧同名（`minjian`，uid 也是 1000）**是刻意选择：挂载进来的 `/home/minjian` 目录权限位（`drwxr-x---  minjian minjian`）在 WSL 里天然匹配，不需要 `-u root` 或改权限就能读。

### 3.4 挂载 Ubuntu 数据盘（只读） <a id="mount"></a>

两种方式，日常用第一种：

| 方式 | 操作 |
| --- | --- |
| **桌面快捷方式**（推荐） | 双击桌面 **「挂载 Ubuntu 盘」** → UAC 点「是」→ 弹出控制台打印结果（窗口停在 `Press any key to continue`，按任意键关闭即可） |
| 命令行（管理员） | `python3 bms/scripts/tools/wsl/挂载Ubuntu盘.py`（Windows 亦可双击 `挂载Ubuntu盘.bat`） |

脚本口径（`scripts/tools/wsl/` 目录说明见同目录 `README.md`）：

- **幂等**：已挂载时只校验并打印路径，不会重复挂载；
- 附加参数：`--unmount` 卸载、`--disk/--partition/--distro` 换对象；
- 非管理员运行时**友好拒绝**（退出码 2），不会半途失败；
- 检测到挂载但非只读时会尝试改回只读。

等价的**手工命令**（不想用脚本时）：

```powershell
wsl --mount \\.\PHYSICALDRIVE3 --partition 2 --options ro
```

挂载点形态固定为 `/mnt/wsl/PHYSICALDRIVE3p2`（未改 `/etc/wsl.conf` 的 `automount.root` 时）。

### 3.5 访问路径 <a id="paths"></a>

| 端 | 路径 |
| --- | --- |
| WSL 内 | `/mnt/wsl/PHYSICALDRIVE3p2` |
| Windows 资源管理器 / PowerShell | `\\wsl.localhost\Ubuntu-26.04\mnt\wsl\PHYSICALDRIVE3p2` |

> WSL 未在运行时访问 `\\wsl.localhost\...` 会先拉起发行版，首次有启动延迟。

## 4. 使用 <a id="usage"></a>

### 4.1 日常读文件 <a id="daily"></a>

挂载后两端都能读（**都只读**）：

- **Windows 侧**：资源管理器地址栏输入 `\\wsl.localhost\Ubuntu-26.04\mnt\wsl\PHYSICALDRIVE3p2`，或用 VS Code / 编辑器打开该 UNC 路径；PowerShell 里同样按普通路径用（`Get-ChildItem`、`rg`、`robocopy` 等）。
- **WSL 内**：`ls /mnt/wsl/PHYSICALDRIVE3p2/home/minjian`、`diff`、`rg` 等；也可以在 WSL 内跑脚本对两侧文件做比对。

实测样例（双系统 Ubuntu 的主机名）：

```powershell
Get-Content '\\wsl.localhost\Ubuntu-26.04\mnt\wsl\PHYSICALDRIVE3p2\etc\hostname'   # mjpc
```

### 4.2 挂载生命周期（重启后要重挂） <a id="lifecycle"></a>

```mermaid
flowchart TD
    A["双击桌面「挂载 Ubuntu 盘」"] --> B["UAC 确认"]
    B --> C["wsl --mount 只读挂载磁盘 3 分区 2"]
    C --> D["两端随处可读：WSL 内 /mnt/wsl/PHYSICALDRIVE3p2，Windows 侧 UNC 路径"]
    D --> E{"Windows 重启，或执行过 wsl --shutdown？"}
    E -->|是，挂载失效| A
    E -->|否| D
```

- 挂载**不跨重启**：Windows 重启、（发行版或整机）`wsl --shutdown` 之后挂载都会消失，重跑一次即可（脚本幂等，重复双击无害）。
- 想常驻（开机自动挂载）也可以，但会让 WSL 虚拟机每次开机都驻留（约占 1~2 GB 内存）；本机按需挂载，故不做常驻。

### 4.3 卸载 <a id="unmount"></a>

```powershell
python3 bms/scripts/tools/wsl/挂载Ubuntu盘.py --unmount
# 等价手工命令：wsl --unmount \\.\PHYSICALDRIVE3
```

- **卸载不需要管理员**（本机实测；只有挂载需要）。
- 需要访问磁盘 3 的其它分区（含它的 ESP）、或在磁盘管理里调整该盘之前，**必须先卸载**（2.4 的副作用）。

## 5. 维护与排障 <a id="maintain"></a>

### 5.1 发行版维护 <a id="distro"></a>

| 事项 | 做法 |
| --- | --- |
| 进入发行版 | `wsl -d Ubuntu-26.04`（默认用户 `minjian`；需要 root 时 `-u root`） |
| 系统更新 | 发行版内照常 `sudo apt update && sudo apt upgrade`（默认源在国内偏慢，可换镜像，见下） |
| 换 apt 镜像（可选） | Ubuntu 26.04 用 deb822 格式的 `/etc/apt/sources.list.d/ubuntu.sources`：把其中的 `archive.ubuntu.com`、`security.ubuntu.com` 换成 `mirrors.tuna.tsinghua.edu.cn`（改前先备份该文件） |
| 迁移发行版位置 | 先 `wsl --shutdown`，再 `wsl --manage Ubuntu-26.04 --move D:\wsl\Ubuntu-26.04` |
| 释放内存 | `wsl --shutdown`：WSL2 虚拟机空闲时也会驻留一部分内存，长期不用可关掉 |
| 重建桌面入口 | 见文末「重建桌面快捷方式」代码块 |

**重建桌面快捷方式**（快捷方式丢失或换机时；创建后须置「以管理员身份运行」位）：

```powershell
$ws = New-Object -ComObject WScript.Shell
$lnk = "$env:USERPROFILE\Desktop\挂载 Ubuntu 盘.lnk"
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = 'D:\Develop\bizs\bms\scripts\tools\wsl\挂载Ubuntu盘.bat'
$s.WorkingDirectory = 'D:\Develop\bizs\bms'
$s.IconLocation = "$env:SystemRoot\System32\imageres.dll,27"
$s.Save()
# .lnk 的 LinkFlags 位于 0x14，其第二字节 0x15 的 bit5 = RunAsUser（以管理员身份运行）
$b = [IO.File]::ReadAllBytes($lnk); $b[0x15] = $b[0x15] -bor 0x20; [IO.File]::WriteAllBytes($lnk, $b)
```

### 5.2 常见问题 <a id="trouble"></a>

| 现象 | 原因与处理 |
| --- | --- |
| 双击快捷方式后提示「需要管理员权限」 | UAC 被点了「否」，或该快捷方式丢了「以管理员身份运行」位：重新双击并在 UAC 点「是」（或按 5.1 重建） |
| 写入报 `Read-only file system` | **预期**：这是只读挂载（2.4）；要改文件请进 Ubuntu 系统操作 |
| 重启后 `/mnt/wsl/PHYSICALDRIVE3p2` 不见了 | 挂载不跨重启（4.2）：重跑一次挂载 |
| `wsl --mount` 失败（盘被占用 / 找不到分区） | 先 `wsl --unmount \\.\PHYSICALDRIVE3` 再试；并在「磁盘管理」核对**磁盘号与分区号**（本机为磁盘 3 分区 2） |
| 磁盘 3 的其它分区在 Windows 里打不开 | 整盘已挂给 WSL（2.4 副作用）：先按 4.3 卸载 |
| `wsl -d Ubuntu-26.04` 报发行版不存在 | 发行版被删或未安装：按 3.1~3.3 重装（镜像已留存） |
| 在 WSL 里 `ls /mnt/wsl/...` 提示无权限 | 挂载点属 root：本机两侧用户同名同 uid，正常读取无需提权；若用了别的用户名，需 `-u root` 或改用同名用户 |

### 5.3 与双系统 Ubuntu 的关系 <a id="relation"></a>

- **两套 Ubuntu 相互独立**：WSL 里的 Ubuntu 是独立 rootfs（`ext4.vhdx`），与磁盘 3 上的双系统 Ubuntu **不共享文件系统**；本文档提供的是把后者**挂进来当数据读**。
- 版本同为 **26.04.1 LTS**，命令与包行为接近，适合在 Windows 侧顺手查资料、对配置。
- **不要在 Linux 侧重启/关机的同时读写**：WSL 挂的是同一块物理盘；只读挂载风险很低，但若要在 Linux 侧重启或关机，先按 4.3 卸载更稳妥。
- 常驻 WSL 的内容（装的软件、写的文件）都在 `ext4.vhdx` 里，**不会**回到双系统 Ubuntu，也不占磁盘 3 的空间。

## 6. 关键位置速查 <a id="quickref"></a>

| 用途 | 位置 |
| --- | --- |
| 查看 WSL 状态 | `wsl --status` / `wsl --list --verbose` |
| 发行版 rootfs（WSL 落盘） | `C:\Users\minjian\AppData\Local\wsl\{2d1cf05e-6a37-432c-b93f-f02ea0b5c50a}\ext4.vhdx` |
| 官方镜像留存 | `D:\tools\操作系统\linux\ubuntu\ubuntu-26.04.1-wsl-amd64.wsl` |
| 挂载脚本 | `bms/scripts/tools/wsl/挂载Ubuntu盘.py`（+ `挂载Ubuntu盘.bat`） |
| 桌面入口 | 桌面「挂载 Ubuntu 盘」（勾「以管理员身份运行」） |
| 挂载点（WSL 内） | `/mnt/wsl/PHYSICALDRIVE3p2` |
| Windows 侧访问 | `\\wsl.localhost\Ubuntu-26.04\mnt\wsl\PHYSICALDRIVE3p2` |
| 卸载 | `python3 scripts/tools/wsl/挂载Ubuntu盘.py --unmount` |

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 与《[开发机部署使用说明总览（Windows 侧）](windows/开发机部署使用说明总览.md)》配套
