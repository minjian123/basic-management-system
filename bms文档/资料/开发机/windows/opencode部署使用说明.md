# opencode 部署使用说明

> mjpc 开发机 Windows 侧 opencode（CLI + 桌面端）部署与使用口径 · 2026-10-16 本机采集（CLI 与桌面端均为 2.0.29）；2026-10-18 复核（桌面端自更新至 2.0.32，启用局域网 / 手机访问、共享服务固定监听 `0.0.0.0:45278`）；**2026-10-25 全量卸载重装至 2.1.4**（CLI 与桌面端版本对齐、数据与配置归零重建，见 [2.3 节](#status-2026-10-25)）

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › opencode 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[CodeBuddy部署使用说明 →](CodeBuddy部署使用说明.md)　[VSCode部署使用说明 →](VSCode部署使用说明.md)　[linux 侧同名文档 →](../linux/opencode部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** Windows 侧（Windows 11 专业版，与 Ubuntu 26.04 双系统同机）上 opencode v2 的部署与使用：CLI 与桌面端的安装、路径落点、共享后台服务、工作区配置与插件、凭据、常用命令与排障。

同机 Ubuntu 侧同名文档《[opencode部署使用说明](../linux/opencode部署使用说明.md)》记录 v1 → v2 迁移沿革、配置字段对照、Web / 手机访问与 GPU / sudo 沙箱排障等；两侧是同一产品与同一套配置格式，差异只在系统路径与进程形态，Windows 侧以本文为准。

> **取值说明**：开发用户为 `minjian`，用户目录统写作 `~`（即 `C:\Users\minjian`）；路径按 Windows 写法；账号、密码与令牌类信息不在本文记录，以《[本地资源](../../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 现状概览与路径速查 <a id="env"></a>

### 2.1 现状速览 <a id="status-now"></a>

| 实体 | 版本 | 安装位置 | 启动方式 |
| --- | --- | --- | --- |
| CLI | 2.1.4 | `~\.opencode\bin\opencode.exe`（约 235 MB；同目录 `opencode2.cmd` 为转发到同一二进制的兼容别名） | 终端执行 `opencode`（新开终端） |
| 桌面端 | 2.1.4 | `%LOCALAPPDATA%\Programs\@opencodedesktop\`（`OpenCode.exe`；卸载器 `Uninstall OpenCode.exe`） | 开始菜单 **OpenCode**（AppID `ai.opencode.desktop`） |

两者**升级通道独立、版本号可不一致**：CLI 走 `opencode upgrade` 或手动换二进制（见 [3.1 节](#cli-install)），桌面端由内置自更新器跟进（更新源 `https://opencode.ai/update/api/latest/desktop/opencode/`）。**2026-10-25 全量重装后两者已对齐到 2.1.4**，历史偏差（CLI 2.0.29 / 桌面端 2.0.32～2.1.4）不复存在。

### 2.2 版本与路径速查 <a id="env-paths"></a>

| 项 | 取值 |
| --- | --- |
| 安装方式 | CLI：手动换二进制（npmmirror `@opencode/cli-windows-x64` 包解压后覆盖）；桌面端：官方 NSIS 安装包（`opencode-desktop-win-x64.exe`）。**2026-10-25 起**两者均按此重装（此前 CLI 为 curl 脚本安装） |
| CLI 二进制 | `~\.opencode\bin\opencode.exe`（`opencode v2.1.4`，246,919,560 B） |
| CLI 别名 | `~\.opencode\bin\opencode2.cmd`（内容为 `@echo off` + 转发 `opencode.exe`） |
| PATH 登记 | `~\.opencode\bin` 已在**用户 PATH**（装后须新开终端生效） |
| 桌面端程序目录 | `%LOCALAPPDATA%\Programs\@opencodedesktop\`（`OpenCode.exe` 文件版本 2.1.4） |
| 桌面端用户数据 | `%APPDATA%\ai.opencode.desktop\`（`logs\`、`cli\2.1.4-x64\`、`opencode.settings`） |
| 数据目录 | `~\.local\share\opencode\`（`opencode.db`：凭据与会话库，**2026-10-25 重装后归零**，首次启动自动重建） |
| 配置目录 | `~\.config\opencode\`（同目录含 `opencode.json`（全局配置，**重装后为空**）、`service.json`（共享服务密码与监听覆盖值：`hostname` / `port`）、`plugins\`） |
| 状态目录 | `~\.local\state\opencode\`（`service.json`、`locks\`） |
| 缓存目录 | `~\.cache\opencode\`（`bin\`） |
| 共享后台服务 | 桌面端内嵌 `opencode-cli.exe`（`%APPDATA%\ai.opencode.desktop\cli\2.1.4-x64\`），监听 `0.0.0.0:45278`，随桌面端启停（局域网 / 手机访问见 [6.1 节](#web-access)） |
| 工作区配置 | 工作区根 `.opencode\` 已于 2026-10-25 删除（原 `D:\Develop\bizs\.opencode\opencode.json` 的 llamacpp provider 随环境重装移出）；如需恢复项目级模型配置须重建该文件 |
| 临时目录 | `%TEMP%\opencode`（即 `debug paths` 的 `tmp`） |

> 路径速查的权威来源是 `opencode debug paths`（打印 home / data / cache / config / state / tmp / db 等全部落点，见[验证](#verify)）。

### 2.3 2026-10-25 全量卸载重装 <a id="status-2026-10-25"></a>

因 CLI 与桌面端版本长期偏差、且用户级插件与数据积压，做了一次**完全卸载 + 干净重装**（用户拍板：数据不备份、配置全清）。口径与结果：

| 项 | 处置 |
| --- | --- |
| 卸载范围 | CLI + 桌面端全部；先杀进程（`opencode-cli.exe` 孤儿进程占 `0.0.0.0:45278`）再跑官方卸载器 `Uninstall OpenCode.exe /currentuser /S` |
| 清除目录 | `~\.opencode`、`~\.config\opencode`、`~\.local\share\opencode`、`~\.local\state\opencode`、`~\.cache\opencode`、`%APPDATA%\ai.opencode.desktop`、`%LOCALAPPDATA%\opencode`、`%LOCALAPPDATA%\@opencodedesktop-updater`、`~\.bg`、`%TEMP%\opencode`——合计约 **1.45 GB** |
| 数据 | `opencode.db`（101 MB / 527 会话 / 8585 消息 / 4 条凭据）**直接清空不备份**；重装后 `opencode auth list` 为空，需重新 `opencode auth login` |
| 保留项 | 用户 PATH 的 `~\.opencode\bin` 登记、Windows 防火墙规则 `opencode web`（TCP 45278 / LocalSubnet） |
| CLI 装法 | npmmirror `https://registry.npmmirror.com/@opencode/cli-windows-x64/-/cli-windows-x64-2.1.4.tgz`（111.3 MB）解压 `package\bin\opencode.exe` 覆盖到 `~\.opencode\bin\` |
| 桌面端装法 | 官方 `https://opencode.ai/files/bin/2.1.4/opencode-desktop-win-x64.exe`（238.8 MB），**sha256 校验** `96ecb831c8746a0fbefd1d6e0ef7cf9c5fb2061a28f521dd412ac45767b3aecd`，`/S` 静默安装 |
| 服务重建 | `opencode service set hostname 0.0.0.0` + `set port 45278`；密码由服务启动时随机重新生成 |
| 验证 | `opencode --version` → v2.1.4；`opencode service status` → `http://0.0.0.0:45278`；本机与局域网 `http://192.168.0.124:45278/` 均 HTTP 200；`opencode run` 非交互调用 3.2s 返回 |

> **重装后必须重做的两件事**：① `opencode auth login` 重新登录（凭据随数据库清空）；② 若要恢复工作区级模型配置，重建 `D:\Develop\bizs\.opencode\opencode.json`（llamacpp provider 三个本地模型条目）。
>
> **踩坑记录（重要）**：在 DSH 等 Electron 宿主里启动桌面端时，宿主注入的 `ELECTRON_RUN_AS_NODE=1` 会让 `OpenCode.exe` 退化为纯 Node 进程、**启动即静默退出（exit 0，不建用户数据目录、不监听端口）**。判断方法：`OpenCode.exe --help` 若打印的是 Node.js 帮助（而非应用帮助），即命中此坑。处置：启动前 `Remove-Item Env:ELECTRON_RUN_AS_NODE`（或用资源管理器 / 开始菜单等不带该变量的方式启动）。

## 3. 命令行 CLI <a id="cli"></a>

### 3.1 安装与升级与卸载 <a id="cli-install"></a>

**2026-10-25 起**本机改用手动换二进制方式重装（npmmirror 包解压覆盖），二进制仍为 `~\.opencode\bin\opencode.exe`（v2 官方分发路径，与 linux 侧一致），约 235 MB 自包含单文件。此前（2026-10-16 首装）为官方 curl 安装脚本方式。

升级两条路：

```powershell
# 1) 官方升级命令（--method 可选 curl / npm / pnpm / bun / yarn / vp / brew / winget）
opencode upgrade                # 升到最新版
opencode upgrade 2.1.4          # 升到指定版本
```

```text
# 2) 手动换二进制（2026-10-25 实测可行）：下载对应版本包 → 解压出 opencode.exe → 覆盖
#    %USERPROFILE%\.opencode\bin\opencode.exe（先退出使用中的终端与桌面端内嵌服务，或先备份旧文件）
官方 CDN：  https://opencode.ai/files/bin/<版本>/opencode-windows-x64.zip
npmmirror：https://registry.npmmirror.com/@opencode/cli-windows-x64/-/cli-windows-x64-<版本>.tgz
#   npmmirror 包内路径为 package\bin\opencode.exe，解压后直接覆盖目标即可
```

> 2026-10-25 实测：npmmirror `cli-windows-x64-2.1.4.tgz` 111.3 MB（6.2s 下完），解压出 `opencode.exe` 246,919,560 B、`--version` 返回 `opencode v2.1.4`；官方 `opencode.ai/files/bin/2.1.4/opencode-windows-x64.zip` 亦可达（200，117 MB）。**镜像 latest 与官方版本可能不同步**（当时镜像 latest 已是 2.1.4）；网络不畅时优先 npmmirror。

卸载：

```powershell
opencode uninstall --dry-run    # 预览将要移除的内容（实测列：cache、后台服务与持久终端状态；二进制需手动删除）
opencode uninstall --force      # 跳过确认执行（旗标仅 --dry-run / --force，--help 实测）
```

> 上述命令只清 cache / 服务状态，**二进制与其余目录需手动删**；2026-10-25 全量卸载的实际清除清单见 [2.3 节](#status-2026-10-25)。

### 3.2 PATH 登记 <a id="cli-path"></a>

`~\.opencode\bin` 已登记在**用户 PATH**（`[Environment]::GetEnvironmentVariable('Path','User')` 实测含该项，顺序在 Microsoft Store 别名目录之后无碍——该目录下是 `opencode.exe` 实体文件而非别名桩）。

> `opencode` 须在**新开终端**里调用：登记 / 安装之前开着的终端不会刷新环境变量（本机实测此类旧终端报「无法将 opencode 识别为…」）；应急可用全路径 `& "$env:USERPROFILE\.opencode\bin\opencode.exe" --version`。

## 4. 桌面端 <a id="desktop"></a>

### 4.1 安装与用户数据 <a id="desktop-install"></a>

- 官方 Windows 桌面端安装包为 `opencode-desktop-win-x64.exe`（用户级安装、无需管理员；**winget 源 `SST.OpenCodeDesktop` 只收录到 1.19.4，无 2.x**，故 2.x 须走官方直链 `https://opencode.ai/files/bin/<版本>/opencode-desktop-win-x64.exe`，升级由内置更新器承担）；
- 程序目录 `%LOCALAPPDATA%\Programs\@opencodedesktop\`（`OpenCode.exe`、`resources\`、`Uninstall OpenCode.exe`）；开始菜单条目 **OpenCode**（AppID `ai.opencode.desktop`）；
- 用户数据 `%APPDATA%\ai.opencode.desktop\`：
  - `logs\<时间戳>\`（`main.log` 等，启动与自更新证据，见 [4.2 节](#desktop-verify)）；
  - `cli\<版本>-x64\`（各版本内嵌 CLI，现为 `2.1.4-x64`）；
  - `opencode.settings`（首启引导完成标记、窗口 ID、背景色）。

### 4.2 启动确认与自更新 <a id="desktop-verify"></a>

正常姿态（2026-10-16 实测）：

| 证据 | 取值 |
| --- | --- |
| `main.log` | `main window visible`（窗口已绘制） |
| `main.log` | `v2 CLI background service ready { version: '2.0.29', probed: false, url: 'http://127.0.0.1:49374', hostname: '127.0.0.1', port: '49374' }` |
| 进程 | `OpenCode.exe`（主进程 + 渲染 / GPU 子进程）与内嵌 `opencode-cli.exe`（监听 `127.0.0.1:49374`） |
| 自更新器 | 检到官方 2.0.30，已下载 `%LOCALAPPDATA%\@opencodedesktop-updater\pending\opencode-desktop-win-x64.exe`（`updater state: downloading → ready`，待重启安装） |

2026-10-18 复核（桌面端升至 2.0.32，启用局域网 / 手机访问）：

| 证据 | 取值 |
| --- | --- |
| 监听 | 内嵌 `opencode-cli.exe` 监听 `0.0.0.0:45278`（`opencode service status` 打印 `http://0.0.0.0:45278`；`Get-NetTCPConnection -LocalPort 45278 -State Listen` 的 LocalAddress 为 `0.0.0.0`） |
| 局域网可达 | 非回环网卡地址 `http://<本机内网IP>:45278/` 返回 HTTP 200（详见 [6.1 节](#web-access)） |
| `main.log` | `v2 CLI background service ready { probed: false, url: 'http://127.0.0.1:45278', hostname: '127.0.0.1', port: '45278' }`——**该行的 `hostname` 字段未反映 `service set hostname` 覆盖值**（2.0.32 / 2.1.4 实测），判断实际监听以 `opencode service status` / `Get-NetTCPConnection` 为准 |

2026-10-25 重装后复核（2.1.4）：

| 证据 | 取值 |
| --- | --- |
| 进程 | `OpenCode.exe` 主进程 + 4 个渲染 / GPU 子进程 + 内嵌 `opencode-cli.exe`（实测 6 个进程共存） |
| 监听 | `opencode service status` → `http://0.0.0.0:45278`；`Get-NetTCPConnection -LocalPort 45278 -State Listen` 的 LocalAddress 为 `0.0.0.0`，归属 `%APPDATA%\ai.opencode.desktop\cli\2.1.4-x64\opencode-cli.exe` |
| 可达性 | 本机 `http://127.0.0.1:45278/` 与局域网 `http://192.168.0.124:45278/` 均返回 HTTP 200 |
| 自更新器 | 启动即报 `Update for version 2.1.4 is not available (latest version: 2.1.4)`——已是当前最新 |
| **坑位** | 在 Electron 宿主（如 DSH）里启动时，宿主注入的 `ELECTRON_RUN_AS_NODE=1` 会让 `OpenCode.exe` 退化为纯 Node 进程、**启动即静默退出**；判据是 `OpenCode.exe --help` 打印 Node.js 帮助而非应用帮助。详见 [2.3 节](#status-2026-10-25) |

核实命令：

```powershell
$d = Get-ChildItem "$env:APPDATA\ai.opencode.desktop\logs" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Select-String -Path (Join-Path $d.FullName 'main.log') -Pattern 'main window visible|background service ready|has been downloaded'
Get-Process OpenCode, opencode-cli -ErrorAction SilentlyContinue | Select-Object Name, Id, Path
Get-NetTCPConnection -LocalPort 45278 -State Listen
```

## 5. 配置与插件 <a id="config"></a>

### 5.1 配置落点 <a id="config-paths"></a>

| 层级 | 路径 | 说明 |
| --- | --- | --- |
| 全局 | `~\.config\opencode\opencode.json` | **全局配置**：`plugins` 数组登记用户级插件（绝对路径）；同目录 `service.json` 为共享服务配置 |
| 工作区 | `D:\Develop\bizs\.opencode\opencode.json` | bizs 工作区项目级配置：**只放项目自身的模型 / 供应商**（覆盖全局同名项） |
| 用户级插件 | `~\.config\opencode\plugins\` | 用户级插件目录（经全局 `plugins` 登记加载，**不是**工作区插件） |

> 基座仓（`D:\Develop\bizs\bms`）内**没有** `opencode.json` 与 `.opencode\`（实测）——工作区级配置就在工作区根 `D:\Develop\bizs\.opencode\`；工作区 `.opencode\` 现只含 `opencode.json`（通用插件已上移用户级）。配置为 v2 原生格式（`providers` / `mcp.servers` / `plugins` 等），与 v1 的字段对照见 linux 侧文档「配置（v2 原生格式）」节。

### 5.2 工作区配置实例（bizs） <a id="config-bizs"></a>

```jsonc
// D:\Develop\bizs\.opencode\opencode.json（节选）
"model": "llamacpp/qwen3.8-27b-ud-q4-k-m",
"providers": {
  "llamacpp": {
    "package": "@opencode/ai/providers/openai-compatible",
    "settings": { "baseURL": "http://127.0.0.1:8080/v1", "apiKey": "local" }
    // 三个本地模型条目：qwen3.8-27b-ud-q4-k-m / qwen3.8-27b-q4-k-m / qwen3.8-27b-uncensored-q4-k-m
  }
}
```

- 默认模型 `llamacpp/qwen3.8-27b-ud-q4-k-m` 由 `llamacpp` provider 提供，指向本机 `http://127.0.0.1:8080/v1` 的 llama-server（推理服务部署见《[llamacpp部署使用说明](../../AI/linux/llamacpp部署使用说明.md)》）；
- 原先登记的 MCP `mjw-vision`（识图）与配套的 MCP 超时配置已于 2026-10-16 退役移除（所用模型已普遍多模态）；今后如需再登记 MCP，超时字段照 `"mcp": { "timeout": { "catalog": …, "execution": … } }` 配。

## 6. 凭据与共享服务 <a id="auth"></a>

- v2 起**凭据保存在 SQLite 数据库内**（`~\.local\share\opencode\opencode.db`），`auth.json` 是其历史来源、v2 不写回；实测连接状态：

```powershell
opencode auth list
# OpenCode Go       OpenCode Go      stored
# OpenCode Console  <账号标签>        stored（账号标签不记录）
```

- 重连：`opencode auth login`（交互式选择 provider）；TUI / 桌面端内用 `/connect`；
- **共享后台服务**：桌面端启动时拉起内嵌 CLI 的 `serve --service`，所有本地客户端（TUI / 桌面端 / Web）共用；实测：

```powershell
opencode service status    # http://0.0.0.0:45278
opencode service get       # {"hostname":"0.0.0.0","port":45278,"password":"<取值见本地资源>"}（2026-10-18 起有用户级覆盖，此前为空）
```

- 服务配置子命令含 `start` / `restart` / `status` / `stop` / `get` / `set` / `unset`（2.0.29 实测）；服务密码默认随机生成，存于 `~\.config\opencode\service.json`（键 `password`），取值以《[本地资源](../../../用户文档/本地资源.md)》为准、不入本文；
- 本机已改监听地址并**固定端口**：`hostname` = `0.0.0.0`、`port` = `45278`（2026-10-18 启用局域网 / 手机访问）；手机、局域网与公网访问的完整口径见 [6.1 节](#web-access)，键位说明见 linux 侧文档「Web 与手机访问」节。

### 6.1 Web 与手机访问（局域网 / 手机 App） <a id="web-access"></a>

opencode v2 自带 Web UI，由**同一个共享后台服务**（`opencode serve --service`）提供，与 TUI / 桌面端共用会话与配置，默认开启、密码保护。Windows 侧该服务**由桌面端拉起、随桌面端启停**（不常驻、不自启，无 Windows 服务 / 计划任务）：桌面端开着服务就在，关掉即停。

**访问入口（opencode pair）**

```powershell
opencode pair
```

命令打印三样东西：

- **一次性配对链接**（形如 `http://<主机>:45278/auth/connect/...`，**5 分钟内有效、用一次即失效**）；
- **用户名 / 密码**（用户名固定 `opencode`，密码取值见《[本地资源](../../../用户文档/本地资源.md)》）；
- **二维码**（用 OpenCode 手机 / 桌面 App 扫描，或把链接粘进 App 的服务器地址栏）；**手机端没有 App 时（如鸿蒙）不必装客户端**——用系统相机 / 浏览器扫码即可，扫开即登录 Web UI。

浏览器打开链接即写入会话 cookie 并载入 Web UI，**会话有效 30 天**；改服务器密码会让所有会话立即登出。

**本机现状与生效步骤（2026-10-18 启用）**

共享服务默认只监听 `127.0.0.1`（仅本机可达）。Windows 侧已改为局域网可达并**固定端口**——不固定时端口随桌面端版本变化（实测 2.0.29 为 49374、2.0.30 及以后为 45278；45278 低于 Windows 保留段 49152+，可安全长期占用，不随升级漂移）：

```powershell
# 监听所有网卡 + 固定端口（两条都改配置，会停掉后台服务；本机服务由桌面端托管，重启桌面端生效）
opencode service set hostname 0.0.0.0
opencode service set port 45278
```

生效判据（Windows 2.0.32 实测）：`opencode service status` 打印 `http://0.0.0.0:45278`、`Get-NetTCPConnection -LocalPort 45278 -State Listen` 的 LocalAddress 为 `0.0.0.0`；**判断实际监听不要只看桌面端 `main.log` 的 `background service ready`**——该行 `hostname` 字段实测仍打印 `127.0.0.1`，不反映配置覆盖（见 [4.2 节](#desktop-verify)）。

配对时用本机局域网地址生成链接（不带 `--url` 时链接指向 `127.0.0.1`，手机打不开）：

```powershell
opencode pair --url http://<本机内网IP>:45278
```

手机侧三种进法（**都不需要装 App**）：① 系统相机 / 浏览器扫二维码，打开链接即登录；② 浏览器直接打开该链接；③ 浏览器访问 `http://<本机内网IP>:45278` 后输入用户名 / 密码。`<本机内网IP>` 与密码见《[本地资源](../../../用户文档/本地资源.md)》。

> **扫码链接一次性、5 分钟过期**：不在手机旁边时先别出码；**首次登录后把 `http://<本机内网IP>:45278` 存为书签**（会话 30 天），之后无需再扫码。手机与电脑须在同一局域网（同一 WiFi）。

**出码脚本（配对二维码）**

配对链接与二维码由仓库内脚本 [`bms/scripts/tools/opencode/配对二维码.py`](../../../../scripts/tools/opencode/配对二维码.py) 一键生成（Python 单一实现，Linux `配对二维码.sh` / Windows `配对二维码.bat` 薄包装），自动探测本机局域网 IP 与服务端口：

```powershell
python scripts/tools/opencode/配对二维码.py               # 出 PNG（<临时目录>\opencode\pair-qr.png）并打印链接
python scripts/tools/opencode/配对二维码.py --open         # 出码后立即用系统图片查看器打开，直接扫屏幕
python scripts/tools/opencode/配对二维码.py --ascii        # 终端字符二维码（不依赖看图）
python scripts/tools/opencode/配对二维码.py --print-only   # 只要链接，不出图
```

- 依赖 `segno`（纯 Python 二维码库，无编译依赖，见同目录 `requirements.txt`）：`pip install segno -i https://pypi.tuna.tsinghua.edu.cn/simple`（本机 2026-10-18 已装 segno 1.6.6）；
- 脚本先读 `opencode service status`：共享服务仍只监听 `127.0.0.1` 时**直接提示改监听命令并退出**（不产出手机不可达的码），确需强行出码加 `--force`；
- 默认输出到临时目录（不落仓库），指定路径用 `--out <路径>`。

**防火墙（Windows 侧差异）**

Windows 防火墙三个配置文件入站默认拒绝，未放行端口时手机连不上（对应 linux 侧的 ufw 放行）。规则须在**本机管理员终端**执行（桌面端会话内无法提权，同 linux 侧 sudo 沙箱结论）：

```powershell
New-NetFirewallRule -DisplayName 'opencode web' `
  -Description 'opencode v2 共享后台服务（Web UI / 手机 App 配对）；仅放行本地子网' `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 45278 -RemoteAddress LocalSubnet -Profile Any
```

规则**仅放行本地子网**（同 WiFi），不暴露到其他网段；2026-10-18 已落地（取值见《[本地资源](../../../用户文档/本地资源.md)》），脚本留存 `%TEMP%\opencode\opencode-firewall-rule.ps1`（临时目录，重装 / 换系统后按上文命令重建）。核对：

```powershell
Get-NetFirewallRule -DisplayName 'opencode web' | Select-Object DisplayName, Enabled, Direction, Action, Profile
Get-NetFirewallAddressFilter -AssociatedNetFirewallRule (Get-NetFirewallRule -DisplayName 'opencode web') | Select-Object RemoteAddress
```

**公网访问（外出 / 移动网络）**

不在同一网络时，用官方内置的 OpenTunnel 临时把服务暴露到公网：

```powershell
opencode pair --remote
```

首次执行会询问是否把服务暴露到互联网（流量端到端加密，仍需服务器密码）；非交互环境须加 `--yes` 才继续。**建议按需临时开启**，不用时关闭：

```powershell
opencode service set remote false
```

> **经 SSH 端口转发（备选）在 Windows 侧不适用**：本机 Windows 侧未安装 OpenSSH 服务端（`Get-Service sshd` 无此服务）；该备选走同机 linux 侧（见 linux 侧文档「Web 与手机访问」节）。

**服务器密码与配置项**

服务密码默认由 opencode 随机生成，存于 `~\.config\opencode\service.json`；本机实际取值见《[本地资源](../../../用户文档/本地资源.md)》（不写入本文档）。改密码：

```powershell
opencode service set password '<新密码>'
```

常用配置项（改完都需重启服务生效，改设置会停掉后台服务）：

| 键 | 作用 | 示例 |
| --- | --- | --- |
| `hostname` | 监听地址 | `0.0.0.0`（所有网卡）/ `127.0.0.1`（仅本机） |
| `port` | 固定端口（Windows 平台默认 45278） | `45278` |
| `password` | 服务器密码 | `'<新密码>'` |
| `cors` | 允许的跨源来源 | `https://app.example.com` |
| `env` | 传给服务进程的环境变量 | `OPENCODE_LOG_LEVEL DEBUG` |
| `remote` | 是否开启 OpenTunnel 远程通道 | `false` |

> **独立前台服务（备选）**：需要脱离桌面端单独跑时用 `opencode serve`：
>
> ```powershell
> opencode serve --hostname 0.0.0.0 --port 45278
> ```
>
> 输出 `server listening on ...` 与 `server password ...`；客户端用 `opencode --server http://127.0.0.1:45278` 连接。本机日常不用这种方式——服务随桌面端启停即可。

**排障速查**

| 现象 | 处置 |
| --- | --- |
| 本机能开、手机连不上 | 多为防火墙未放行 45278（本机回环不受 Windows 防火墙入站规则约束，故「本机通、手机不通」先查防火墙） |
| 手机端装不了 App（鸿蒙等） | 不装客户端：用系统相机 / 浏览器扫码，或浏览器直接访问局域网地址登录（见本节「出码脚本」出码） |
| 配对链接打开报失效 | 链接一次性且 5 分钟过期，重新执行 `opencode pair --url http://<本机内网IP>:45278` |
| 手机 App 里保存的地址突然连不上 | 端口被桌面端升级换代改默认值所致；已固定 `port 45278` 后不再发生，未固定则按本节「固定端口」处置 |
| 本机也访问不到 | 桌面端是否在运行（服务随桌面端启停）：`opencode service status`，必要时重启桌面端 |

## 7. 常用命令 <a id="usage"></a>

```powershell
opencode                                 # 在当前目录打开全屏 TUI
opencode D:\Develop\bizs                 # 指定目录打开
opencode run "帮我梳理这个仓库"           # 非交互执行一条消息（脚本可用）
opencode models                          # 列出可用模型（实测非交互亦可，输出含 llamacpp/* 与 opencode-go/*）
opencode mcp list                        # MCP 服务器与连接状态
opencode auth list                       # 凭据连接状态
opencode service status                  # 共享后台服务状态
opencode pair --url http://<本机内网IP>:45278   # 打印 Web 配对链接与二维码（手机 App 扫码；见 6.1 节）
opencode debug paths                     # 打印各路径（db/home/data/config/cache/state）
opencode -c                              # 继续上一次会话
opencode --standalone                    # 用私有服务运行（隔离变量，不共用后台服务）
```

- CLI 在项目目录运行时读该项目配置（bizs 工作区即 `D:\Develop\bizs\.opencode\opencode.json`），默认模型 `llamacpp/qwen3.8-27b-ud-q4-k-m`；
- 与 linux 侧同款「一个共享后台服务 + 多客户端」形态：所有本地客户端连同一个共享服务（本机 `127.0.0.1:45278`），排障时用 `--standalone` 起私有服务隔离变量。

## 8. 验证 <a id="verify"></a>

```powershell
# CLI
opencode --version                          # opencode v2.1.4
where.exe opencode                          # C:\Users\minjian\.opencode\bin\opencode.exe
opencode debug paths                        # data/config/state/cache/db 等路径

# 桌面端
(Get-Item "$env:LOCALAPPDATA\Programs\@opencodedesktop\OpenCode.exe").VersionInfo |
  Select-Object ProductName, ProductVersion                     # OpenCode / 2.1.4.0
Get-NetTCPConnection -LocalPort 45278 -State Listen             # 共享服务监听（归属 opencode-cli.exe；LocalAddress 应为 0.0.0.0）

# 会话侧
opencode auth list                          # 2026-10-25 重装后为空，需 opencode auth login 重新登录
opencode service status                     # http://0.0.0.0:45278
```

## 9. 常见问题与故障排查 <a id="trouble"></a>

> **历史（2026-10-16）**：原登记的 MCP `mjw-vision`（识图）曾因内嵌服务进程里 `python3` 命中 Microsoft Store 商店别名桩而连接失败；同日认定「所用模型已普遍多模态、识图桥不再需要」并**整体退役**（工作区配置登记、脚本、配套文档一并移除）。今后再登记依赖 `python3` 的 MCP 时仍须留意同一坑（新开终端 `python3` 正常、内嵌进程可能命中别名桩）；IDE 侧同类口径见《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》「排障入口」节。

### 9.1 终端里 `opencode` 命令找不到 <a id="cli-missing"></a>

- 用户 PATH 已登记 `~\.opencode\bin`；**在登记 / 安装之前开着的终端不会刷新**（本机实测此类终端报「无法将 opencode 识别为…」）⇒ 新开终端；
- 应急：用全路径 `& "$env:USERPROFILE\.opencode\bin\opencode.exe" --version`；核实 `where.exe opencode` 应只列出 `C:\Users\minjian\.opencode\bin\opencode.exe`。

### 9.2 CLI 与桌面端版本号不一致 <a id="version-skew"></a>

- 属**正常**：两者升级通道独立——CLI 手动或 `opencode upgrade`，桌面端由内置自更新器跟进；
- 桌面端自更新证据看 `main.log`（`Checking for update` → `Found version <新版本>` → `New version <新版本> has been downloaded to …`）；
- **2026-10-25 重装后两者已对齐 2.1.4**，若再出现偏差按本节两条通道分别升级即可。

### 9.3 端口 45278 冲突 / 共享服务异常 <a id="port-45278"></a>

- 共享服务本机已**固定监听 `0.0.0.0:45278`**（`service set hostname` / `port`，见 [6.1 节](#web-access)），由桌面端内嵌 CLI 托管、随桌面端启停（本机实测监听进程即 `%APPDATA%\ai.opencode.desktop\cli\2.1.4-x64\opencode-cli.exe`）；
- 另有独立 `opencode serve` 常驻时会占用同一端口：先 `Get-NetTCPConnection -LocalPort 45278 -State Listen` 看归属，再用 `opencode service status` / `restart` 处置；不希望共用后台服务时用 `opencode --standalone`；
- **孤儿进程**：桌面端异常退出后 `opencode-cli.exe` 可能残留并继续占 45278（父进程已不存在），重装 / 重启服务前先 `Get-Process opencode-cli | Stop-Process -Force`。

### 9.4 桌面端启动即静默退出（Electron 宿主环境） <a id="electron-run-as-node"></a>

**现象**：`OpenCode.exe` 启动后立即退出（exit 0），不创建 `%APPDATA%\ai.opencode.desktop\`、不监听 45278、无任何日志输出。

**根因**：从 Electron 宿主（如 DSH、某些 IDE 集成终端）启动时会继承 `ELECTRON_RUN_AS_NODE=1`，Electron 应用被降级为纯 Node 运行，主进程逻辑根本不执行。

**判据**：`& "$env:LOCALAPPDATA\Programs\@opencodedesktop\OpenCode.exe" --help` 若打印 **Node.js 帮助**（含 `Usage: node [options] [ script.js ]`）而非应用帮助，即命中此坑。

**处置**：启动前清除该变量再起：

```powershell
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
Start-Process "$env:LOCALAPPDATA\Programs\@opencodedesktop\OpenCode.exe"
```

日常用开始菜单 / 资源管理器双击启动不受影响（不经宿主环境）。

## 10. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc Windows 侧开发设施汇总（opencode 在其中的定位）
- 《[opencode部署使用说明](../linux/opencode部署使用说明.md)》：linux 侧同名文档（v1 → v2 迁移、配置字段对照、Web 与手机访问、GPU / sudo 沙箱排障）
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：另一 AI 编码工具（Windows 侧；MCP 登记与浏览器真机验证）
- 《[VSCode部署使用说明](VSCode部署使用说明.md)》：编辑器与 `.vscode` 双平台配置口径
- 《[llamacpp部署使用说明](../../AI/linux/llamacpp部署使用说明.md)》：`llamacpp` provider 的后端推理服务
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定
- 《[本地资源](../../../用户文档/本地资源.md)》：mjpc 相关机器信息取值（已 gitignore）

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc（Windows 侧）本机核实结果（opencode CLI / 桌面端 2.0.29、路径与共享服务实测、MCP mjw-vision 退役）；2026-10-18 复核并升级记录（桌面端 2.0.32、启用局域网 / 手机访问、共享服务固定 `0.0.0.0:45278` 与 Windows 防火墙放行）；同日通用化改造（通用插件 / 脚本上移用户级 `~\.config\opencode\` 与 `~\.local\share\opencode\`，全局 `opencode.json` 登记 ops / bg 插件）；同日工具收敛（注销 FastCtx 本地 MCP、`ops.js` 仅保留 `ops_bash`）；2026-10-19 插件下线（删除 `ops.js` 与其登记、删除 FastCtx 残留脚本与二进制）；**2026-10-25 全量卸载重装至 2.1.4**（CLI 与桌面端版本对齐、数据与配置归零重建、bg 工具链全链退役、补录 Electron 宿主 `ELECTRON_RUN_AS_NODE` 坑位）
