# Steamcommunity_302 部署使用说明

> mjpc 开发机 Steamcommunity_302（Steam 社区加速反代）V15.0.2 部署与使用实录 · 2026-08-28

[文档首页](../../文档首页.md) › 资料 › 开发机 › Steamcommunity_302 部署使用说明　|　[同级：防火墙部署使用说明 →](防火墙部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS）上 Steamcommunity_302 V15.0.2 的部署过程、目录与端口约定、日常运维与卸载方法。302 通过本地反代（hosts 改写 + 127.0.0.1:443 转发）解决 Steam 社区/商店在国内网络下访问不稳定、加载慢的问题。

上游发布页：https://www.dogfight360.com/blog/18682/（版本更新与已知问题以该页为准）。

本机为**非 SteamOS 的桌面 Linux**，按该页「SteamDeck/Linux 运行注意」口径部署；V15 起 Linux 为单文件 AppImage 封装（前后端分离，后端安装为 systemd 系统服务）。

## 2. 环境准备 <a id="env"></a>

| 项 | 要求 | 本机现状 |
| --- | --- | --- |
| 系统 | Linux x86_64，桌面版 | Ubuntu 26.04.1 LTS |
| 证书工具 certutil | 包 `libnss3-tools`（根证书导入系统 NSS 库） | 部署时补装 |
| Netfilter 队列库 | 包 `libnetfilter-queue1`（DNS 重定向模式用；hosts 模式可不装，建议装上备用） | 部署时补装 |
| 防火墙工具 | iptables / nftables / firewalld / ufw 任一（DNS 模式可从设置内指定） | iptables + ufw 已具备 |
| sudo | 服务安装与证书导入需要 root 权限 | 免密 sudo 已配置 |
| FUSE | AppImage 直接运行需要；**本机不可用**（见 7.1） | 走解压运行 |

依赖安装（Debian/Ubuntu 系）：

```bash
sudo apt install -y libnss3-tools libnetfilter-queue1
```

## 3. 部署步骤 <a id="install"></a>

本次部署（2026-08-28）实际执行的完整流程：

### 3.1 下载与校验 <a id="download"></a>

```bash
curl -fL -C - -o Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage \
  "https://www.dogfight360.com/Usbeam/V15/Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage"
sha256sum Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage
# 期望值（发布页 V15.0.2）：
# aa44444bc3611ad370fcab27282ef8c9f30057cf686c16d8f3759e6a983aa81a
```

文件约 115 MB，Cloudflare CDN 直连速度约 29 MB/s，无需镜像加速。

### 3.2 放置安装目录 <a id="place"></a>

```bash
sudo mkdir -p /opt/Steamcommunity_302
sudo mv Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage /opt/Steamcommunity_302/
sudo chmod 755 /opt/Steamcommunity_302/Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage
```

> 官方提示「若需要开机启动服务请勿移动文件」——选定 `/opt/Steamcommunity_302/` 后不要再挪动。

### 3.3 解压 AppImage（本机 FUSE 不可用） <a id="extract"></a>

直接执行 AppImage 报 `Cannot mount AppImage, please check your FUSE setup`，改用官方兜底的解压方式：

```bash
sudo /opt/Steamcommunity_302/Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage --appimage-extract
sudo mv squashfs-root /opt/Steamcommunity_302/   # 解压目录生成在当前工作目录，须移入安装目录
```

解压后关键文件（`/opt/Steamcommunity_302/squashfs-root/`）：

```text
squashfs-root/
├── AppRun                          # 前端 UI 启动器
├── com.dogfight360.steamcommunity302.desktop
└── usr/bin/
    ├── Steamcommunity_302          # 前端（WebKit GUI）
    ├── steamcommunity_302.cli      # 后端控制面
    ├── steamcommunity_302.caddy    # 反代引擎
    ├── s302-service-installer      # systemd 服务安装器
    ├── S302_rules.ini              # 规则集
    └── s302-service-manifest.json  # 版本与资源清单
```

### 3.4 安装后端系统服务 <a id="service"></a>

```bash
# 用法：s302-service-installer install <uid> <auto|usr-local|var-lib>
sudo /opt/Steamcommunity_302/squashfs-root/usr/bin/s302-service-installer install $(id -u minjian) auto
```

安装后生成 systemd 服务 `s302-1000.service`（按 uid 命名），**默认 enabled（开机自启）**，控制面（`steamcommunity_302.cli`）随服务启动并自动检查规则更新。

### 3.5 配置网络服务随守护进程自启 <a id="config"></a>

默认配置中网络服务（caddy 反代）不随守护进程启动（需在 UI 里手动点「启动服务」）。本机无 UI 值守，改为持久自启：

```bash
sudo python3 - <<'EOF'
import json
p = '/var/lib/Steamcommunity_302/config.json'
d = json.load(open(p))
d['settings']['engine']['startOnDaemonLaunch'] = True
json.dump(d, open(p, 'w'), ensure_ascii=False, indent=4)
EOF
sudo systemctl restart s302-1000.service
```

`config.json` 关键默认值：`network.listenIP=127.0.0.1`（仅本机）、`engine.httpPort=80 / httpsPort=443`、`rules.enabled=[Steam_community]`、`hosts.autoModify=true / autoBackup=true`、`dns.enabled=false`（hosts 模式，未开 DNS 重定向）。

### 3.6 启动验证 <a id="verify"></a>

```bash
systemctl status s302-1000.service --no-pager   # active (running)
ss -ltnp | grep -E ':(443|80) '                  # 127.0.0.1:80 / 443 已监听
grep -n 'S302' /etc/hosts                        # hosts 已写入 S302 标记块
curl -sI https://steamcommunity.com/ | head -1   # HTTP/2 200（证书链校验通过）
```

hosts 改写样例（服务自动维护，带 BEGIN/END 标记块与自动备份）：

```text
# S302 BEGIN b2d0bc619b0f20d636f2caf848d413df
127.0.0.1 steamcommunity.com #S302
127.0.0.1 www.steamcommunity.com #S302
# S302 END b2d0bc619b0f20d636f2caf848d413df
```

## 4. 目录与端口约定 <a id="layout"></a>

### 4.1 目录 <a id="dirs"></a>

```text
/opt/Steamcommunity_302/                    # 安装目录（勿移动）
├── Steamcommunity_302_15.0.2_Linux_WebKit_x64.AppImage   # 原始安装包
└── squashfs-root/                          # 解压产物，UI 从此起
/var/lib/Steamcommunity_302/                # 后端私有数据（root 属主）
├── app/versions/15.0.2/                    # 后端可执行文件
├── config.json                             # 后端持久配置
├── certificates/                           # 自签根证书（s302-root-ca.pem）
└── rules/                                  # 规则文件与更新暂存
/home/minjian/.config/Steamcommunity_302/   # 当前用户控制令牌（control.token）
/etc/hosts                                  # S302 标记块 + hosts_S302Backup 备份（保留份数 config hosts.backupRetention，本机为 10）
```

### 4.2 端口 <a id="ports"></a>

| 监听 | 用途 | 暴露面 |
| --- | --- | --- |
| 127.0.0.1:80 / 443 | 反代主入口（hosts 指向） | 仅回环 |
| 127.0.0.1:40289 / 43903 | 控制面辅助端口 | 仅回环 |
| `*`:14870 / `*`:31131 | 后端 caddy 附加监听 | 全接口，被 ufw 默认拒绝挡住（见《[防火墙部署使用说明](防火墙部署使用说明.md)》2.3），本机使用无需放行 |

## 5. 使用 <a id="usage"></a>

### 5.1 前端 UI <a id="ui"></a>

```bash
/opt/Steamcommunity_302/squashfs-root/AppRun
```

UI 内可完成：勾选启用规则、启动/停止服务、CDN 优选、DNS 重定向开关、证书有效期、日志查看、开机自启开关。无 UI 值守时（本机现状）全部走 systemd + config.json 即可，UI 仅在需要调设置时启动。

### 5.2 日常操作速查 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 服务状态 | `systemctl status s302-1000.service --no-pager` |
| 重启（改 config.json 后） | `sudo systemctl restart s302-1000.service` |
| 停止/启动 | `sudo systemctl stop s302-1000.service` / `start` |
| 开机自启开关 | `sudo systemctl disable s302-1000.service` / `enable` |
| 反代连通性 | `curl -sI https://steamcommunity.com/ \| head -1`（期望 HTTP/2 200） |
| hosts 备份 | `/etc/hosts_S302Backup/`（服务自动维护） |
| 后端日志 | `journalctl -u s302-1000.service -f` |

### 5.3 升级 <a id="upgrade"></a>

官方口径：启动旧版本 UI → 停止服务 → 退出 UI → 解压覆盖 → 启动新版本。本机无 UI 值守的等价流程：

```bash
sudo systemctl stop s302-1000.service
# 下载新版本 AppImage 并校验 sha256（同 3.1），替换 /opt/Steamcommunity_302/ 下安装包
sudo /opt/Steamcommunity_302/<新版本>.AppImage --appimage-extract
sudo rm -rf /opt/Steamcommunity_302/squashfs-root && sudo mv squashfs-root /opt/Steamcommunity_302/
sudo /opt/Steamcommunity_302/squashfs-root/usr/bin/s302-service-installer install $(id -u minjian) auto
sudo systemctl restart s302-1000.service
```

升级后按 3.6 验证；`config.json` 位于 `/var/lib/` 不受覆盖影响，设置保留。

## 6. 卸载 <a id="uninstall"></a>

```bash
sudo systemctl disable --now s302-1000.service
sudo rm -rf /var/lib/Steamcommunity_302 /opt/Steamcommunity_302
rm -rf ~/.config/Steamcommunity_302 ~/.cache/Steamcommunity_302
# hosts 的 S302 标记块在服务停止时自动清理；如残留，删除 BEGIN/END 之间行即可
```

彻底移除自签根证书（可选）：`sudo rm /etc/pki/nssdb/*` 后 `sudo certutil -d sql:/etc/pki/nssdb -D -n "s302"`（名称以 `certutil -L` 实查为准）。

## 7. 已知边界与常见问题 <a id="limits"></a>

### 7.1 FUSE 不可用，必须解压运行 <a id="fuse"></a>

本机运行 AppImage 直接报 `Cannot mount AppImage`（FUSE 挂载失败），一律走 `--appimage-extract`（3.3 节）。注意解压目录生成在**命令执行时的工作目录**，须移入安装目录；不要安装 fuse 相关包强行修复——解压方式官方支持且升级更直观。

### 7.2 网络服务默认不随守护进程启动 <a id="startonlaunch"></a>

安装完成后若 `ss` 看不到 127.0.0.1:443 监听，是 `startOnDaemonLaunch=false` 的默认行为（设计为 UI 手动启动），按 3.5 节改配置并重启服务即可，不是故障。

### 7.3 与 ufw 防火墙的关系 <a id="ufw"></a>

302 主入口走回环，ufw 启用前后行为一致；全接口监听 14870/31131 被默认拒绝挡住，属预期。若日后开启 302 的 DNS 重定向模式（iptables 模式），与 ufw 共管 iptables 规则集的注意事项见《[防火墙部署使用说明](防火墙部署使用说明.md)》6.4 节。

### 7.4 浏览器证书信任 <a id="cert"></a>

根证书已由服务自动导入系统 NSS 库（`/etc/pki/nssdb`），系统浏览器与 curl 直接信任。个别发行版 certutil 导入后 Steam 客户端仍报证书错误时，需在游戏内浏览器（Steam 叠加界面 → 网页浏览器 → `chrome://settings/certificates`）手动导入 `/var/lib/Steamcommunity_302/certificates/s302-root-ca.pem`（发布页已知问题 1/2 有完整图文）。

### 7.5 安全边界 <a id="security"></a>

302 会修改 `/etc/hosts` 并签发自签根证书（有效期默认 365 天），本机所有经 hosts 命中域名的 HTTPS 流量由本地 caddy 解密中转。仅在内网/个人机器上按官方发布渠道安装使用；杀毒/安全软件可能将其 hosts 修改行为标记为可疑，属已知误报。

## 8. 关联文档 <a id="related"></a>

- 《[防火墙部署使用说明](防火墙部署使用说明.md)》：mjpc ufw 规则口径（含 302 端口暴露面说明）
- 《[本地资源](../../用户文档/本地资源.md)》：机器与账号信息
- 上游发布页（版本更新、已知问题、卸载步骤原文）：https://www.dogfight360.com/blog/18682/

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-08-28 实际部署与验证结果 · 更新日期：2026-08-28
