# Ubuntu 安装部署使用说明

> 官方桌面版 ISO 安装步骤 · 通用 + mjbk 参数

[文档首页](../../文档首页.html) › 资料 › Ubuntu 安装部署使用说明　|　[同级：graphify 部署使用说明 →](../AI/graphify部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

本文档指导使用**官方 Ubuntu 桌面版 ISO** 安装 Ubuntu，可手动图形化安装到任意机器（台式机 / 服务器 / 测试机）。
已备好两套 LTS 镜像：**24.04.4**（主力）与 **22.04.5**（备用）。
开发服务器 **mjbk**（IP 记为 `<mjbk-IP>`）的固定参数集中收录在第 5 节，安装到 mjbk 时按表填写即可。
`<mjbk-IP>` / `<网关>` / `<SSH账号>` 具体值见《[本地资源](../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`（`MJBK_IP` / `MJBK_SSH_USER`）。

> **注意：全盘安装会清空目标机器现有系统与全部数据，操作前确认无需要保留的内容。**

## 2. 前置准备 <a id="prereq"></a>

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| U 盘 | ≥ 8GB（会被清空） | 制作 Ubuntu 启动盘（桌面版 ISO 较大，4GB 盘装不下） |
| ISO 镜像 | 已下载到本地 | 见下表，均来自清华 TUNA 镜像，已通过 SHA256 校验 |
| Rufus | Windows 上安装 | `winget install Rufus.Rufus` 或官网 rufus.ie |
| 网线 / 显示器 | 各一根（一台） | 服务器用有线接入路由器；安装过程需接显示器操作 |

### ISO 镜像清单

| 文件 | 大小 | 定位 | SHA256 |
| --- | --- | --- | --- |
| `ubuntu-24.04.4-desktop-amd64.iso` | 6.20 GB | 主力（LTS，支持到 2029 年 4 月） | `3a4c9877b483ab46d7c3fbe165a0db275e1ae3cfe56a5657e5a47c2f99a99d1e` |
| `ubuntu-22.04.5-desktop-amd64.iso` | 4.44 GB | 备用（LTS，支持到 2027 年 4 月） | `bfd1cee02bc4f35db939e69b934ba49a39a378797ce9aee20f6e3e3e728fefbf` |

> 下载地址（清华 TUNA）：`https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/24.04/` 与
> `https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/22.04/`，镜像站目录内同时提供
> `SHA256SUMS` 校验文件。安装前建议在 Windows 上核对：
> `Get-FileHash "ISO所在目录\xxx.iso" -Algorithm SHA256`。

## 3. 制作启动盘（Rufus） <a id="usb"></a>

1. 插入 U 盘（内容会被清空）。
2. 打开 Rufus：
  - 设备：选择 U 盘
  - 引导类型选择：点「选择」→ 选中本地已下载的 `ubuntu-24.04.4-desktop-amd64.iso`（或备用 22.04.5）
  - 分区类型：**GPT**；目标系统：**UEFI（非 CSM）**（默认即可，近十年机型均为 UEFI）
  - 点「开始」→ 弹出提示选「以 ISO 镜像模式写入」（推荐）→ 等待完成

## 4. 安装 Ubuntu 桌面版 <a id="install"></a>

以下为通用安装步骤，24.04.4 与 22.04.5 的安装向导基本一致；mjbk 的固定参数见第 5 节，遇到对应项时照表填写。

### 4.1 开机启动 <a id="install-boot"></a>

1. 目标机器关机，插入启动 U 盘。
2. 开机，反复按 **F12** 进入启动菜单（若无效，开机按 Del/F2 进 BIOS，在 Boot 菜单把 U 盘调到第一位）。
3. 选择含 "UEFI" 字样的 U 盘启动项，回车。
4. 出现 GRUB 菜单后，回车选择 **Try or Install Ubuntu**。

### 4.2 安装向导步骤 <a id="install-wizard"></a>

1. **欢迎界面**：左侧选语言「简体中文」，点「安装 Ubuntu」（也可先点「试用 Ubuntu」进系统查看硬件，确认后再双击桌面的「安装 Ubuntu」）。
2. **键盘布局**：默认 English (US) 即可，中文输入法安装系统后另配；点「继续」。
3. **网络连接**：选择有线网卡，默认 DHCP 自动获取；若需固定 IP（如 mjbk），点网卡右侧的齿轮手动配置：IPv4 → 手动 → 填 IP / 掩码 / 网关 / DNS，点「应用」。可暂用 DHCP，装完再改（见第 10 节静态 IP 条目）。
4. **代理服务器**：留空，点「完成」。
5. **镜像源**：默认官方源在国内慢，下拉选择「中国」后镜像地址会换成国内源；也可点「高级」手工填清华源 `http://mirrors.tuna.tsinghua.edu.cn/ubuntu/`。此时安装器会向网络请求软件包列表，需保持联网。
6. **磁盘分区**（⚠ 此步会清空目标盘）：
  - 全盘安装：选「擦除磁盘并安装 Ubuntu」→「继续」；如需加密或 LVM，点「高级功能」勾选（mjbk 不做加密）。
  - 自定义分区：选「手动安装」，按需建立 EFI 分区（512MB，FAT32，esp 标志）与根分区（剩余空间，ext4 挂载 /）。
7. **用户设置**：填姓名、计算机名（即主机名，mjbk 填 `mjbk`）、用户名（mjbk 填 `<SSH账号>`）、密码；下方选「要求我的密码才能登录」。创建的用户属于 sudo 管理员组，后续服务器操作无需再设 root。
8. **时区**：安装器自动定位，可手动输入「Shanghai」选择上海（Asia/Shanghai）。
9. **开始安装**：点「安装」后等待约 10-20 分钟（进度条阶段完成会提示拔掉 U 盘），完成后点「立即重启」。

> 安装向导全程需要显示器交互；重启提示「请移除安装介质」时拔出 U 盘，否则可能再次进入安装界面。

### 4.3 安装完成首次登录 <a id="install-after"></a>

1. 重启进入系统后，用第 4.2 步创建的用户密码登录桌面。
2. 确认网络连通（右上角网络图标正常、无警告）。
3. 首次更新（可选但建议）：

```bash
sudo apt update && sudo apt upgrade -y
```

## 5. mjbk 服务器参数速查 <a id="mjbk-params"></a>

以下参数用于将开发服务器 mjbk（`<mjbk-IP>`）装为固定配置，安装向导中照表填写即可：

| 项目 | 参数值 |
| --- | --- |
| 镜像 | 主力 `ubuntu-24.04.4-desktop-amd64.iso`（24.04 LTS） |
| 网络 | 静态 IP `<mjbk-IP>/24`，网关 `<网关>`，DNS `114.114.114.114`（有线网卡） |
| apt 镜像源 | `http://mirrors.tuna.tsinghua.edu.cn/ubuntu/` |
| 磁盘 | 全盘安装（512GB SSD 系统盘）；1TB HDD 数据盘挂载 `/mnt/data`（ext4，步骤见 6.3）；2T NVMe SSD 挂载 `/mnt/ssd2t`（ext4，步骤见 6.3.1） |
| 主机名 | `mjbk` |
| 用户名 | `<SSH账号>`（密码见《[本地资源](../../用户文档/本地资源.md)》） |
| 时区 | Asia/Shanghai（上海） |
| 键盘 / 语言 | English (US) / 简体中文 |

> 账号密码等机器凭据统一维护在《[本地资源](../../用户文档/本地资源.md)》中，本文档不重复记录。

> **当前状态（2026-08-15）**：mjbk 已按上表完成安装——系统为 Ubuntu 24.04.4 LTS 桌面版，
> 静态 IP、时区、主机名均已核实；mjpc 的 ed25519 公钥免密登录已配置；apt 源已换清华源并通过
> `apt-get update` 验证；1TB HDD 数据盘已格式化（ext4）并挂载 `/mnt/data`（fstab 自动挂载）；
> 2T NVMe SSD 已格式化（ext4）并挂载 `/mnt/ssd2t`（fstab 自动挂载），Docker data-root 与 GitLab 数据均已迁至其上；
> 笔记本合盖不休眠设置见第 8 节。

## 6. 安装后验证与基础配置 <a id="verify"></a>

1. 确认目标机器网线已插好，桌面右上角网络图标正常。
2. mjbk 场景下，在 mjpc 上验证网络与 SSH：

```bash
ping <mjbk-IP>
ssh <SSH账号>@<mjbk-IP>
```

3. 登录后确认基本环境：

```bash
cat /etc/os-release | head -2
hostname -I
sudo apt-get update -qq && echo APT-OK
```

4. 服务器用途需启用 SSH 服务（桌面版默认不装，必须手动安装）：

```bash
sudo apt install openssh-server -y
sudo systemctl enable --now ssh
sudo ufw allow 22/tcp
```

> 桌面版自带 GNOME 桌面，日常管理可远程桌面（设置 → 共享 → 远程桌面）；命令行管理推荐直接 SSH。

### 6.1 SSH 免密登录（mjpc → mjbk，推荐） <a id="verify-ssh"></a>

日常管理使用公钥免密，避免每次输密码。在 mjpc（Windows PowerShell）上操作：

1. 若无密钥先生成：`ssh-keygen -t ed25519`（一路回车即可，默认存 `~/.ssh/`）。
2. 把公钥装到 mjbk：

```bash
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <SSH账号>@<mjbk-IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

3. 验证：`ssh <SSH账号>@<mjbk-IP>` 直接进入即成功。

### 6.2 apt 镜像源确认 / 更换为清华源 <a id="verify-apt"></a>

安装向导第 4.2 步若未选清华源（默认选「中国」会落到官方 `cn.archive.ubuntu.com`），装完后可再改。Ubuntu 24.04 的源文件是 DEB822 格式：

```bash
sudo cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak
sudo sed -i 's|http://cn.archive.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|; s|http://security.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|' /etc/apt/sources.list.d/ubuntu.sources
sudo apt-get update
```

> mjbk 已完成此配置（4 个仓库全部命中清华源），确认命令：`grep URIs /etc/apt/sources.list.d/ubuntu.sources`。

### 6.3 数据盘分区与挂载（机械盘 / 原 Windows D 盘） <a id="verify-disk"></a>

笔记本常见双盘：系统盘（SSD）装 Ubuntu，另一块机械盘（HDD）作数据盘（容器数据卷、GitLab 数据、备份等大容量、读多写少的数据）。以下以 mjbk 的 1TB HDD（`/dev/sda`）为例。

1. 查看磁盘与文件系统：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
```

2. 原 Windows D 盘通常为 NTFS 或 BitLocker 加密卷（`TYPE="BitLocker"`），Linux 无法直接挂载；确认盘内数据无用后重建分区并格式化（**注意：会清空该盘全部数据**）：

```bash
sudo parted /dev/sda --script mklabel gpt
sudo parted /dev/sda --script mkpart primary ext4 0% 100%
sudo mkfs.ext4 -L bms-data /dev/sda1
```

3. 创建挂载点并挂载：

```bash
sudo mkdir -p /mnt/data
sudo mount /dev/sda1 /mnt/data
```

4. 写入 `/etc/fstab` 实现开机自动挂载（用 UUID，避免盘符漂移）：

```bash
echo "UUID=$(sudo blkid -s UUID -o value /dev/sda1) /mnt/data ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab
```

5. 验证：

```bash
df -h /mnt/data
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT /dev/sda
```

> mjbk 已完成此配置：`/dev/sda1`（931.5G，ext4，卷标 `bms-data`）挂载于 `/mnt/data`，fstab 按 UUID 自动挂载。

### 6.3.1 2T NVMe SSD 挂载（2026-08-15，原 Windows 系统盘） <a id="verify-ssd"></a>

笔记本第三块盘：**2T NVMe SSD**（`/dev/nvme1n1`，Fanxiang S770）——原 Windows 系统盘残留（NTFS 分区表含 EFI/MSR/恢复分区），确认无保留数据后整盘重建并挂载为 `/mnt/ssd2t`，承接 Docker data-root（镜像/容器/全部命名卷）与 GitLab 数据（仓库读写性能最优，规划 4.2）：

```bash
# 1. 整盘重建 GPT 分区表 + 单分区（1MiB 对齐；⚠ 会清空该盘全部数据）
sudo parted /dev/nvme1n1 --script mklabel gpt
sudo parted /dev/nvme1n1 --script mkpart primary ext4 1MiB 100%

# 2. 格式化（卷标 ssd2t）
sudo mkfs.ext4 -L ssd2t /dev/nvme1n1p1

# 3. 挂载
sudo mkdir -p /mnt/ssd2t
sudo mount -o noatime /dev/nvme1n1p1 /mnt/ssd2t

# 4. fstab 自动挂载（用 UUID，避免盘符漂移）
echo "UUID=$(sudo blkid -s UUID -o value /dev/nvme1n1p1) /mnt/ssd2t ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab
sudo mount -a

# 5. 验证
df -h /mnt/ssd2t
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT /dev/nvme1n1
```

> mjbk 已完成：`/dev/nvme1n1p1`（1.8T，ext4，卷标 `ssd2t`）挂载于 `/mnt/ssd2t`，fstab 自动挂载验证通过。
> 随后 Docker data-root 迁至 `/mnt/ssd2t/docker`、GitLab 数据迁至 `/mnt/ssd2t/gitlab`（迁移过程见《[DockerEngine部署使用说明](../开发服务器/DockerEngine部署使用说明.md)》2.4 与《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》第 2 节）。

### 6.4 远程桌面（xrdp） <a id="verify-rdp"></a>

远程桌面使用 **xrdp**（独立 Xorg 会话、系统账号认证、分辨率随窗口自适应）。mjbk 已配置完成：

```bash
# 1. 安装
sudo apt install -y xrdp xorgxrdp dbus-x11

# 2. 会话配置（GNOME on X11，独立 dbus，避免与现有图形会话冲突）
sudo tee /etc/xrdp/startwm.sh << EOF
#!/bin/sh
unset DBUS_SESSION_BUS_ADDRESS
unset XDG_RUNTIME_DIR
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=GNOME
exec dbus-launch --exit-with-session /usr/bin/gnome-session
EOF
sudo chmod +x /etc/xrdp/startwm.sh

# 3. 启用 xrdp（并放行防火墙）
sudo systemctl enable --now xrdp
sudo ufw allow from <内网网段> to any port 3389 proto tcp
```

客户端连接（mjpc）：`mstsc` → 计算机 `<mjbk-IP>` → xrdp 登录界面输入 `<SSH账号>` / 密码 → 进入独立桌面，分辨率随窗口动态调整。

> **弃用说明**：Ubuntu 24.04 自带 GNOME 远程桌面（`gnome-remote-desktop`）曾尝试但弃用——
> 镜像模式分辨率固定为物理屏；headless 模式（系统级服务）为实验功能，登录后停在 GDM 界面、桌面空白；
> 且凭据依赖 gnome-keyring（自动登录场景锁定易失效）。故统一改用 xrdp。

> 排障要点：xrdp 会话 1 秒退出查 `sudo tail /var/log/xrdp-sesman.log`；
> 退出码 127 = 缺 `dbus-x11`；退出码 1 = dbus 冲突（按第 2 步隔离会话环境）。

## 7. 备份与恢复（Timeshift 系统快照） <a id="backup"></a>

服务器环境（系统、配置、已装软件）装坏后需要能快速还原。mjbk 使用 **Timeshift**（rsync 模式）做整系统快照，快照存数据盘 HDD（`/mnt/data`），系统装坏时用安装 U 盘启动即可恢复到快照时间点。

### 7.1 安装与配置（mjbk 已完成） <a id="backup-config"></a>

1. 安装（清华源已配置，直接安装）：

```bash
sudo apt install -y timeshift
```

2. 确认快照存放设备 UUID（数据盘，如 HDD `/dev/sda1`）：

```bash
sudo blkid -s UUID -o value /dev/sda1
```

3. 写入配置 `/etc/timeshift/timeshift.json`（关键字段）：

```json
{
  "backup_device_uuid": "<数据盘 UUID>",
  "do_first_run": "false",
  "schedule_daily": "true",
  "count_daily": "5",
  "exclude": ["/mnt/data/**", "/mnt/ssd2t/**", "/var/lib/docker/**", "/snap/**"]
}
```

4. 创建首个全量快照：

```bash
sudo timeshift --create --comments "初始快照" --scripted
```

5. 自动调度：Timeshift 自动创建 `/etc/cron.d/timeshift-hourly`，每小时执行 `timeshift --check --scripted`——按 `schedule_daily` 每天创建一份，超出 `count_daily` 的旧快照自动清理。
6. 验证：`sudo timeshift --list` 应显示快照列表。

> Timeshift 快照固定存放在备份设备根目录的 `timeshift/snapshots/`（mjbk 为 `/mnt/data/timeshift/snapshots/`）。
> 排除项必须包含数据盘挂载点（`/mnt/data/**`、`/mnt/ssd2t/**`），否则快照会递归备份自身；
> `/mnt/ssd2t/**` 自 2026-08-15 起必须排除（Docker data-root 与 GitLab 数据已迁入，容量大且非系统状态）。
> mjbk 当前已创建初始快照 `2026-08-10_21-30-58`（约 9.2GB），此后每日自动快照、保留 5 份。

### 7.2 系统还原 <a id="backup-restore"></a>

1. 用制作好的 Ubuntu 安装 U 盘启动，在 GRUB 菜单选择 **Try or Install Ubuntu**，进入「试用 Ubuntu」桌面。
2. 打开终端执行 `sudo timeshift --restore`（或图形界面打开 Timeshift 程序点「恢复」）。
3. 选择要恢复的快照（按日期时间识别），确认恢复目标设备后开始还原，完成后重启。

> 恢复会覆盖当前系统到快照时间点，快照之后的新增内容会丢失；还原前确认数据盘已正确识别（HDD 快照在其上、NVMe SSD 挂载点被排除，均不会被覆盖）。

## 8. 笔记本（mjbk）作为服务器注意事项 <a id="laptop"></a>

mjbk 是笔记本（i7-8750H + GTX 1060），作为 7×24 服务器需处理两个默认行为：合盖休眠与合盖黑屏。

### 8.1 合盖不休眠（已配置） <a id="lid-sleep"></a>

默认合盖会挂起（GNOME 电源插件层直接触发 suspend，仅改 logind 不够）。需在 logind 与 GNOME 两层同时设置：

```bash
# 1. logind 层：合盖不执行电源动作
sudo sed -i 's/^#HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sudo sed -i 's/^#HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind

# 2. GNOME 层：合盖不动作、不关屏（注意此键没有 ignore 值，用 nothing；SSH 中设置需带用户总线）
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
gsettings set org.gnome.settings-daemon.plugins.power lid-close-ac-action nothing
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action nothing
gsettings set org.gnome.settings-daemon.plugins.power lid-close-suspend-with-external-monitor false
```

> GNOME 层若仍为 `suspend`（默认值），合盖依然会休眠；必须改为 `nothing`。修改后合盖屏幕保持常亮，不再触发关屏。

### 8.2 合盖后屏幕黑屏的恢复 <a id="lid-black"></a>

历史故障：合盖打开后完全黑屏（背光与面板均正常，但显示输出未唤醒，nouveau 驱动典型问题）。恢复步骤：

1. 先尝试唤醒显示（SSH 远程执行）：

```bash
sudo env DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority xset dpms force on
sudo chvt 1 && sleep 1 && sudo chvt 2
```

2. 无效则重启图形会话（桌面会退出，重新登录即可；SSH 不受影响）：

```bash
sudo systemctl restart gdm3
```

> 按 8.1 配置为 `nothing` 后合盖不再关屏，此问题不再出现；本小节仅作故障排查参考。

## 9. 服务部署衔接 <a id="deploy"></a>

系统就绪后，由自动化脚本完成后续部署（仓库 `deploy/setup/install-all.sh`），内容包括：

- apt 清华源、基础工具、Docker Engine（清华 docker-ce 源 + 国内镜像加速）
- MySQL、PostgreSQL、Redis、MinIO、RocketMQ、ElasticSearch（Docker Compose）
- GitLab CE + gitlab-runner
- 防火墙（ufw）放行、时区 Asia/Shanghai

> 部署脚本与 Compose 文件从代码仓库获取（`deploy/` 目录），部署详情见《[开发服务器部署使用说明](../开发服务器/开发服务器部署使用说明.md)》。

## 10. 常见问题 <a id="trouble"></a>

| 问题 | 处理 |
| --- | --- |
| 开机不出现启动菜单 | U 盘需为 UEFI 启动（Rufus 选 GPT + UEFI）；尝试 Del/F2 进 BIOS 手动改启动顺序；Secure Boot 开/关均可启动 |
| 有线网卡未识别 | 确认网线已插且路由器灯亮；多数 Intel/Realtek 有线网卡内核原生支持；若确实无驱动，记录网卡型号反馈处理 |
| 镜像源访问慢 | 安装第 4.2 步必须改国内镜像源，否则安装过程可能很慢或失败；装完后按第 6.2 节更换 |
| 安装后 ping 不通 | 检查网线、路由器；`ip addr` 查看网卡 IP；动态 IP 与预期不符时按下条改静态 IP |
| 改静态 IP | 安装后修改 netplan：`sudo nano /etc/netplan/50-cloud-init.yaml`，将 dhcp4 改为静态 `addresses / routes / nameservers`，然后 `sudo netplan apply` |
| SSH 连接被拒 | 桌面版默认未装 OpenSSH，先执行第 6 节第 4 步安装启用；确认 ufw 放行 22 端口 |
| 合盖后休眠 / 黑屏 | 按第 8.1 节设置 logind + GNOME 两层；已黑屏按第 8.2 节恢复（重启 gdm3） |
| 忘记 root / sudo 密码 | 桌面版平时用普通用户 + sudo，无需 root 密码；忘记普通用户密码需在 GRUB 进恢复模式重置 |

## 11. 关联文档 <a id="related"></a>

- 《[本地资源](../../用户文档/本地资源.md)》：机器硬件与账号信息
- 《[开发服务器部署使用说明](../开发服务器/开发服务器部署使用说明.md)》：部署后服务使用与运维
- 《[Redis 部署使用说明](../开发服务器/Redis部署使用说明.md)》/《[PostgreSQL 部署使用说明](../开发服务器/PostgreSQL部署使用说明.md)》：常见服务部署参考
- 《[开发部署规划](../../规划/开发部署规划.html)》：开发环境整体方案
- 《[文档生成规范](../../规范/文档生成规范.html)》：本文档遵循的格式规范

> 本文档为 AI 生成 · 依《文档生成规范》编写 · ISO 来自清华 TUNA 镜像（SHA256 已校验，存放于项目外本地目录） · 更新日期：2026-08-15（新增 2T NVMe SSD 挂载与 Timeshift 排除项）