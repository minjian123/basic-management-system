# XRDP 远程桌面部署使用说明

> mjbk 桌面远程接入部署实录 · 2026-08-11（2026-09-15 补文）

[文档首页](../../../文档首页.md) › [资料](../../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md) › XRDP 远程桌面部署使用说明　|　[← 上一个：达梦 DM8](达梦DM8部署使用说明.md)　|　[下一个：防火墙 →](防火墙部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 是**桌面版** Ubuntu（24.04.4 LTS），除 SSH 命令行接入外，偶尔需要**图形桌面**处理：

- 百度网盘官方客户端登录（登录态 Cookie 供《[百度网盘云备份部署使用说明](百度网盘云备份部署使用说明.md)》的云同步使用）
- 图形化排障（浏览器窗口、证书信任、GUI 工具）
- 系统显示 / 会话相关配置核对

本文档记录 **xrdp + Xorg + GNOME（X11 会话）**方案的部署、会话定制与验证口径。`<mjbk-IP>` 取值见《[本地资源](../../../用户文档/本地资源.md)》。

> 分工：**日常命令一律走 SSH**（《开发服务器部署使用说明总览》§6），远程桌面仅在确须图形界面时启用。

## 2. 组件与端口 <a id="components"></a>

| 组件 | 版本（实测） | 作用 |
| --- | --- | --- |
| `xrdp` | 0.9.24-4 | RDP 服务端（`xrdp.service`） |
| `xorgxrdp` | 1:0.9.19-1 | 提供 Xorg 后端会话（非 VNC 模式） |
| `xrdp-sesman` | 随 `xrdp` 包 | 会话管理（`xrdp-sesman.service`） |
| `pipewire-module-xrdp` / `libpipewire-0.3-modules-xrdp` | 0.2-2 | 音频重定向（可选依赖） |

| 端口 | 监听范围 | 说明 |
| --- | --- | --- |
| 3389 | `*:3389` | RDP 入连，**已由 ufw 对内网 `<内网网段>` 放行**（见《[防火墙部署使用说明](防火墙部署使用说明.md)》规则表「3389/tcp xrdp 远程桌面」） |
| 3350 | `[::1]:3350` | sesman 内部通信，**仅回环**，不外放 |

## 3. 部署步骤 <a id="deploy"></a>

1. 安装组件（清华 TUNA 源已在系统级配置，见《[Ubuntu安装部署使用说明](../../工具/Ubuntu安装部署使用说明.md)》）：

    ```bash
    sudo apt update && sudo apt install -y xrdp
    sudo apt install -y xorgxrdp            # Xorg 后端（GNOME 原生 X11 会话需要）
    ```

2. 确认服务开机自启：

    ```bash
    sudo systemctl enable --now xrdp xrdp-sesman
    systemctl is-enabled xrdp xrdp-sesman     # 期望均为 enabled
    ```

3. 防火墙放行（仅内网段，**不对公网**）：

    ```bash
    sudo ufw allow from <内网网段> to any port 3389 proto tcp comment 'xrdp'
    sudo ufw reload && sudo ufw status numbered
    ```

4. 定制会话脚本（见[第 4 节](#config)），重启服务生效：`sudo systemctl restart xrdp`。

## 4. 会话定制（关键）<a id="config"></a>

桌面版 Ubuntu 默认会话是 **Wayland**，而 xrdp 需要 **X11**；且远程会话不能复用宿主机已存在的 D-Bus / XDG 运行时目录（会黑屏或回落到极简 WM）。故替换 `/etc/xrdp/startwm.sh` 为**隔离 dbus 的 GNOME X11 会话**（当前内容）：

```sh
#!/bin/sh
# xrdp Xorg session: GNOME on X11 with isolated dbus
unset DBUS_SESSION_BUS_ADDRESS
unset XDG_RUNTIME_DIR
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=GNOME
exec dbus-launch --exit-with-session /usr/bin/gnome-session
```

四行各自的作用：

| 行 | 不设的后果 |
| --- | --- |
| `unset DBUS_SESSION_BUS_ADDRESS` | 复用残留总线地址，会话组件（GNOME Shell / 指示器）起不来，表现为登录即退回或黑屏 |
| `unset XDG_RUNTIME_DIR` | 与本机图形会话争抢运行时目录，权限冲突 |
| `XDG_SESSION_TYPE=x11` + `XDG_CURRENT_DESKTOP=GNOME` | 会话被打成 Wayland 或非 GNOME 桌面，与 `xorgxrdp` 后端不匹配 |
| `dbus-launch --exit-with-session` | 会话总线生命周期不随会话退出，残留进程累积 |

配置文件口径（`grep -vE '^\s*#|^\s*$' /etc/xrdp/{xrdp.ini,sesman.ini}`）：

| 文件 | 关键项 | 取值 | 说明 |
| --- | --- | --- | --- |
| `xrdp.ini` | `port` | `3389` | 监听端口（保持默认） |
| `xrdp.ini` | `use_vsock` | `false` | 不走 vsock，纯 TCP |
| `xrdp.ini` | `fork` | `true` | 每连接派生进程 |
| `sesman.ini` | `ListenAddress` / `ListenPort` | `127.0.0.1` / `3350` | 会话管理器只听回环 |
| `sesman.ini` | `UserWindowManager` / `DefaultWindowManager` | `startwm.sh` | 即上一节的定制脚本 |

## 5. 验证 <a id="verify"></a>

| 验证项 | 命令 | 期望 |
| --- | --- | --- |
| 服务状态 | `systemctl is-enabled xrdp xrdp-sesman` | 均为 `enabled` |
| 端口监听 | `ss -lnt \| grep -E ':3389\|:3350'` | `*:3389`（对外）与 `[::1]:3350`（仅回环） |
| 进程 | `pgrep -af xrdp` | `xrdp` 与 `xrdp-sesman` 均在 |
| 会话连入 | 客户端连接 `<mjbk-IP>:3389`，用本机账号登录 | 出现 GNOME 桌面；`echo $XDG_SESSION_TYPE` = `x11` |
| 日志 | `tail -f /var/log/xrdp.log`、会话日志 `~/.xorgxrdp.*.log` | 无 `sesman connect failed` / `cannot create X session` |

> 连入即需**在非内网环境先确认可用**：3389 只对内网段放行，外网一律拒绝。

## 6. 使用说明 <a id="use"></a>

- **客户端**：Windows「远程桌面连接」（`mstsc`）；Linux 用 Remmina（协议 RDP）或 `xfreerdp`。
- **会话语义**：同一个账号的远程会话**会复用/重连**（`ReconnectScript=reconnectwm.sh`）；远程登录与本机桌面登录是**两个不同显示上的会话**，互不干扰但不共享屏幕。
- **典型用途**：图形化登录百度网盘客户端以刷新登录态（云备份依赖其 Cookie），之后无需保持连接即可断开。
- **安全**：仅内网可达；登录失败重试上限 `MaxLoginRetry=4`；root 登录在 `sesman.ini` 为 `AllowRootLogin=true`（本机无公网暴露，保留默认；若变更 exhaust 需同步修改配置）。

## 7. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 状态 | `systemctl status xrdp xrdp-sesman` |
| 重启 | `sudo systemctl restart xrdp`（会话会断，重连即可恢复未注销的会话） |
| 日志 | `sudo journalctl -u xrdp -f`、`tail -f /var/log/xrdp-sesman.log` |
| 修改会话脚本 | 编辑 `/etc/xrdp/startwm.sh` → `sudo systemctl restart xrdp` |
| 当前连接的会话 | `who -u` / `loginctl list-sessions` |
| 关闭远程桌面（释放资源） | `sudo systemctl stop xrdp xrdp-sesman`（开机不自启则再 `disable`） |

## 8. 排障记录 <a id="trouble"></a>

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| 登录后黑屏或直接退回登录框 | GNOME 走 Wayland 会话 / 复用宿主机 D-Bus 总线 | 按[第 4 节](#config)替换 `startwm.sh`（强制 X11 + `dbus-launch` 隔离总线） |
| 只有极简窗口管理器（无顶栏 / 无 Dock） | `XDG_CURRENT_DESKTOP` 未设为 GNOME，或 `xorgxrdp` 未安装 | `apt install -y xorgxrdp` + 显式导出 `XDG_CURRENT_DESKTOP=GNOME` |
| 会话可被连入但 3389 端口 `ss` 看不到 | 服务未 enable / 被 `systemctl` 停止，或 ufw 未放行导致外部连不通（端口仍应 LISTEN） | `systemctl is-enabled xrdp` 与 `ufw status \| grep 3389` 分别核对 |
| 远程登录后本机显示器被占用/锁定 | `MAX`：远程与本机是两个显示上的独立会话，互不影响；若需释放资源可 `loginctl terminate-session <id>` | 属预期语义，非故障 |

## 9. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)》：端口总表与运维入口
- 《[防火墙部署使用说明](防火墙部署使用说明.md)》：3389 放行规则总表与核对
- 《[百度网盘云备份部署使用说明](百度网盘云备份部署使用说明.md)》：需图形界面的主要场景（客户端登录态）
- 《[Ubuntu安装部署使用说明](../../工具/Ubuntu安装部署使用说明.md)》：系统安装、Timeshift 快照
- 平台《开发部署规划》：远程接入方案

> 依《文档生成规范》编写 · 2026-09-15 补文
