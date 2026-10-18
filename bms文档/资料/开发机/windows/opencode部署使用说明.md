# opencode 部署使用说明

> mjpc 开发机 Windows 侧 opencode（CLI + 桌面端）部署与使用口径 · 2026-10-16 本机采集（CLI 与桌面端均为 2.0.29）；2026-10-18 复核（桌面端自更新至 2.0.32，启用局域网 / 手机访问、共享服务固定监听 `0.0.0.0:45278`）

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › opencode 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[CodeBuddy部署使用说明 →](CodeBuddy部署使用说明.md)　[VSCode部署使用说明 →](VSCode部署使用说明.md)　[linux 侧同名文档 →](../linux/opencode部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** Windows 侧（Windows 11 专业版，与 Ubuntu 26.04 双系统同机）上 opencode v2 的部署与使用：CLI 与桌面端的安装、路径落点、共享后台服务、工作区配置与插件、凭据、常用命令与排障。

同机 Ubuntu 侧同名文档《[opencode部署使用说明](../linux/opencode部署使用说明.md)》记录 v1 → v2 迁移沿革、配置字段对照、Web / 手机访问与 GPU / sudo 沙箱排障等；两侧是同一产品与同一套配置格式，差异只在系统路径与进程形态，Windows 侧以本文为准。

> **取值说明**：开发用户为 `minjian`，用户目录统写作 `~`（即 `C:\Users\minjian`）；路径按 Windows 写法；账号、密码与令牌类信息不在本文记录，以《[本地资源](../../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 现状概览与路径速查 <a id="env"></a>

### 2.1 现状速览 <a id="status-now"></a>

| 实体 | 版本 | 安装位置 | 启动方式 |
| --- | --- | --- | --- |
| CLI | 2.0.29 | `~\.opencode\bin\opencode.exe`（约 203 MB；同目录 `opencode2.cmd` 为转发到同一二进制的兼容别名） | 终端执行 `opencode`（新开终端） |
| 桌面端 | 2.0.32 | `%LOCALAPPDATA%\Programs\@opencodedesktop\`（`OpenCode.exe`；卸载器 `Uninstall OpenCode.exe`） | 开始菜单 **OpenCode**（AppID `ai.opencode.desktop`） |

两者**升级通道独立、版本号可不一致**：CLI 走 `opencode upgrade` 或手动换二进制（见 [3.1 节](#cli-install)），桌面端由内置自更新器跟进（2026-10-16 检到 2.0.30、2026-10-18 实测已升至 2.0.32；CLI 仍为 2.0.29，见 [4.2 节](#desktop-verify)）。

### 2.2 版本与路径速查 <a id="env-paths"></a>

| 项 | 取值 |
| --- | --- |
| 安装方式 | curl（官方安装脚本；`opencode uninstall --dry-run` 显示 `Installation method: curl`） |
| CLI 二进制 | `~\.opencode\bin\opencode.exe`（`opencode v2.0.29`） |
| CLI 别名 | `~\.opencode\bin\opencode2.cmd`（内容为 `@echo off` + 转发 `opencode.exe`） |
| PATH 登记 | `~\.opencode\bin` 已在**用户 PATH**（装后须新开终端生效） |
| 桌面端程序目录 | `%LOCALAPPDATA%\Programs\@opencodedesktop\`（`OpenCode.exe` 文件版本 2.0.29） |
| 桌面端用户数据 | `%APPDATA%\ai.opencode.desktop\`（`logs\`、`cli\2.0.29-x64\`、`opencode.settings`） |
| 数据目录 | `~\.local\share\opencode\`（`opencode.db`：凭据与会话库，实测约 17 MB） |
| 配置目录 | `~\.config\opencode\`（实测仅 `service.json`——共享服务密码；无全局 `opencode.json`） |
| 状态目录 | `~\.local\state\opencode\`（`service.json`、`locks\`） |
| 缓存目录 | `~\.cache\opencode\`（`bin\`） |
| 共享后台服务 | 桌面端内嵌 `opencode-cli.exe`（`%APPDATA%\ai.opencode.desktop\cli\2.0.29-x64\`），监听 `127.0.0.1:49374`，随桌面端启停 |
| 工作区配置 | `D:\Develop\bizs\.opencode\opencode.json`；插件 `D:\Develop\bizs\.opencode\plugins\bg.js` |
| 临时目录 | `%TEMP%\opencode`（即 `debug paths` 的 `tmp`） |

> 路径速查的权威来源是 `opencode debug paths`（打印 home / data / cache / config / state / tmp / db 等全部落点，见[验证](#verify)）。

## 3. 命令行 CLI <a id="cli"></a>

### 3.1 安装与升级与卸载 <a id="cli-install"></a>

本机经官方 **curl 安装脚本**安装（`uninstall --dry-run` 自证安装方式），二进制为 `~\.opencode\bin\opencode.exe`（v2 官方分发路径，与 linux 侧一致），约 203 MB 自包含单文件。

升级两条路：

```powershell
# 1) 官方升级命令（本机安装方式为 curl；--method 可选 curl / npm / pnpm / bun / yarn / vp / brew / winget）
opencode upgrade                # 升到最新版
opencode upgrade 2.0.30         # 升到指定版本
```

```text
# 2) 手动换二进制（本机未实测，步骤与 linux 侧同构）：下载对应版本包 → 解压出 opencode.exe → 覆盖
#    %USERPROFILE%\.opencode\bin\opencode.exe（先退出使用中的终端与桌面端内嵌服务，或先备份旧文件）
官方 CDN：  https://opencode.ai/files/bin/<版本>/opencode-windows-x64.zip
npmmirror：https://registry.npmmirror.com/@opencode/cli-windows-x64/-/cli-windows-x64-<版本>.tgz
```

> 2026-10-16 对上述两个下载地址做过 HEAD 探测（均可达）：官方 zip 返回 200、`application/zip`、约 96 MB；npmmirror 包 302 → 200、约 95 MB（镜像 latest 已到 2.0.30）。网络不畅时优先 npmmirror 镜像。

卸载：

```powershell
opencode uninstall --dry-run    # 预览将要移除的内容（实测列：cache、后台服务与持久终端状态；二进制需手动删除）
opencode uninstall --force      # 跳过确认执行（旗标仅 --dry-run / --force，--help 实测）
```

### 3.2 PATH 登记 <a id="cli-path"></a>

`~\.opencode\bin` 已登记在**用户 PATH**（`[Environment]::GetEnvironmentVariable('Path','User')` 实测含该项，顺序在 Microsoft Store 别名目录之后无碍——该目录下是 `opencode.exe` 实体文件而非别名桩）。

> `opencode` 须在**新开终端**里调用：登记 / 安装之前开着的终端不会刷新环境变量（本机实测此类旧终端报「无法将 opencode 识别为…」）；应急可用全路径 `& "$env:USERPROFILE\.opencode\bin\opencode.exe" --version`。

## 4. 桌面端 <a id="desktop"></a>

### 4.1 安装与用户数据 <a id="desktop-install"></a>

- 官方 Windows 桌面端安装包为 `opencode-desktop-win-x64.exe`（用户级安装、无需管理员；无 winget 等包管理器来源，升级由内置更新器承担）；
- 程序目录 `%LOCALAPPDATA%\Programs\@opencodedesktop\`（`OpenCode.exe`、`resources\`、`Uninstall OpenCode.exe`）；开始菜单条目 **OpenCode**（AppID `ai.opencode.desktop`）；
- 用户数据 `%APPDATA%\ai.opencode.desktop\`：
  - `logs\<时间戳>\`（`main.log` 等，启动与自更新证据，见 [4.2 节](#desktop-verify)）；
  - `cli\<版本>-x64\`（各版本内嵌 CLI，现为 `2.0.29-x64`）；
  - `opencode.settings`（首启引导完成标记、窗口 ID、背景色）。

### 4.2 启动确认与自更新 <a id="desktop-verify"></a>

正常姿态（2026-10-16 实测）：

| 证据 | 取值 |
| --- | --- |
| `main.log` | `main window visible`（窗口已绘制） |
| `main.log` | `v2 CLI background service ready { version: '2.0.29', probed: false, url: 'http://127.0.0.1:49374', hostname: '127.0.0.1', port: '49374' }` |
| 进程 | `OpenCode.exe`（主进程 + 渲染 / GPU 子进程）与内嵌 `opencode-cli.exe`（监听 `127.0.0.1:49374`） |
| 自更新器 | 检到官方 2.0.30，已下载 `%LOCALAPPDATA%\@opencodedesktop-updater\pending\opencode-desktop-win-x64.exe`（`updater state: downloading → ready`，待重启安装） |

核实命令：

```powershell
$d = Get-ChildItem "$env:APPDATA\ai.opencode.desktop\logs" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Select-String -Path (Join-Path $d.FullName 'main.log') -Pattern 'main window visible|background service ready|has been downloaded'
Get-Process OpenCode, opencode-cli -ErrorAction SilentlyContinue | Select-Object Name, Id, Path
Get-NetTCPConnection -LocalPort 49374 -State Listen
```

## 5. 配置与插件 <a id="config"></a>

### 5.1 配置落点 <a id="config-paths"></a>

| 层级 | 路径 | 说明 |
| --- | --- | --- |
| 全局 | `~\.config\opencode\` | 全局配置目录（实测仅 `service.json`，无全局 `opencode.json`） |
| 工作区 | `D:\Develop\bizs\.opencode\opencode.json` | bizs 工作区项目级配置（覆盖全局） |
| 插件 | `D:\Develop\bizs\.opencode\plugins\` | 插件目录（自动发现，无需登记） |

> 基座仓（`D:\Develop\bizs\bms`）内**没有** `opencode.json` 与 `.opencode\`（实测）——工作区级配置就在工作区根 `D:\Develop\bizs\.opencode\`。配置为 v2 原生格式（`providers` / `mcp.servers` 等），与 v1 的字段对照见 linux 侧文档「配置（v2 原生格式）」节。

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

- 默认模型 `llamacpp/qwen3.8-27b-ud-q4-k-m` 由 `llamacpp` provider 提供，指向本机 `http://127.0.0.1:8080/v1` 的 llama-server（推理服务部署见《[llamacpp部署使用说明](../../AI/llamacpp部署使用说明.md)》）；
- 原先登记的 MCP `mjw-vision`（识图）与配套的 MCP 超时配置已于 2026-10-16 退役移除（所用模型已普遍多模态）；今后如需再登记 MCP，超时字段照 `"mcp": { "timeout": { "catalog": …, "execution": … } }` 配。

### 5.3 插件 <a id="plugins"></a>

```powershell
opencode plugin list    # 实测：ID bg   VERSION local   SOURCE D:\Develop\bizs\.opencode\plugins\bg.js
```

- `bg.js` 为 opencode v2 插件 API 实现，提供 `bg_run` / `bg_status` / `bg_stop` / `gl_watch_pipeline` 四个后台任务工具（下载 / 构建 / ssh / 安装类长操作异步执行、秒级查状态）；
- **`.opencode\plugins\` 目录会被自动发现，无需在 `opencode.json` 登记**（bg.js 文件头自述口径）；
- 全局未装插件；插件改动后须**完全重启**客户端（TUI / 桌面端）再验证。

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
opencode service status    # http://127.0.0.1:49374
opencode service get       # {}（无用户级覆盖，默认值生效）
```

- 服务配置子命令含 `start` / `restart` / `status` / `stop` / `get` / `set` / `unset`（2.0.29 实测）；服务密码默认随机生成，存于 `~\.config\opencode\service.json`（键 `password`），取值以《[本地资源](../../../用户文档/本地资源.md)》为准、不入本文；
- 本机未改监听地址（`service get` 为空 ⇒ 默认 `127.0.0.1`，仅本机可达）；改监听、配对与手机 / 公网访问的键位口径见 linux 侧文档「Web 与手机访问」节。

## 7. 常用命令 <a id="usage"></a>

```powershell
opencode                                 # 在当前目录打开全屏 TUI
opencode D:\Develop\bizs                 # 指定目录打开
opencode run "帮我梳理这个仓库"           # 非交互执行一条消息（脚本可用）
opencode models                          # 列出可用模型（实测非交互亦可，输出含 llamacpp/* 与 opencode-go/*）
opencode mcp list                        # MCP 服务器与连接状态
opencode plugin list                     # 插件清单
opencode auth list                       # 凭据连接状态
opencode service status                  # 共享后台服务状态
opencode debug paths                     # 打印各路径（db/home/data/config/cache/state）
opencode -c                              # 继续上一次会话
opencode --standalone                    # 用私有服务运行（隔离变量，不共用后台服务）
```

- CLI 在项目目录运行时读该项目配置（bizs 工作区即 `D:\Develop\bizs\.opencode\opencode.json`），默认模型 `llamacpp/qwen3.8-27b-ud-q4-k-m`；
- 与 linux 侧同款「一个共享后台服务 + 多客户端」形态：默认所有本地客户端连同一个 `127.0.0.1:49374`，排障时用 `--standalone` 起私有服务隔离变量。

## 8. 验证 <a id="verify"></a>

```powershell
# CLI
opencode --version                          # opencode v2.0.29
where.exe opencode                          # C:\Users\minjian\.opencode\bin\opencode.exe
opencode debug paths                        # data/config/state/cache/db 等路径

# 桌面端
(Get-Item "$env:LOCALAPPDATA\Programs\@opencodedesktop\OpenCode.exe").VersionInfo |
  Select-Object ProductName, ProductVersion                     # OpenCode / 2.0.29.0
Get-NetTCPConnection -LocalPort 49374 -State Listen             # 共享服务监听（归属 opencode-cli.exe）

# 会话侧
opencode auth list                          # OpenCode Go / OpenCode Console：stored
opencode plugin list                        # bg local  D:\Develop\bizs\.opencode\plugins\bg.js
opencode mcp list                           # 逐项看连接状态（bizs 工作区当前无 MCP 登记）
opencode service status                     # http://127.0.0.1:49374
```

## 9. 常见问题与故障排查 <a id="trouble"></a>

> **历史（2026-10-16）**：原登记的 MCP `mjw-vision`（识图）曾因内嵌服务进程里 `python3` 命中 Microsoft Store 商店别名桩而连接失败；同日认定「所用模型已普遍多模态、识图桥不再需要」并**整体退役**（工作区配置登记、脚本、配套文档一并移除）。今后再登记依赖 `python3` 的 MCP 时仍须留意同一坑（新开终端 `python3` 正常、内嵌进程可能命中别名桩）；IDE 侧同类口径见《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》「排障入口」节。

### 9.1 终端里 `opencode` 命令找不到 <a id="cli-missing"></a>

- 用户 PATH 已登记 `~\.opencode\bin`；**在登记 / 安装之前开着的终端不会刷新**（本机实测此类终端报「无法将 opencode 识别为…」）⇒ 新开终端；
- 应急：用全路径 `& "$env:USERPROFILE\.opencode\bin\opencode.exe" --version`；核实 `where.exe opencode` 应只列出 `C:\Users\minjian\.opencode\bin\opencode.exe`。

### 9.2 CLI 与桌面端版本号不一致 <a id="version-skew"></a>

- 属**正常**：两者升级通道独立——CLI 手动或 `opencode upgrade`，桌面端由内置自更新器跟进；
- 桌面端自更新证据看 `main.log`（`Checking for update` → `Found version <新版本>` → `New version <新版本> has been downloaded to …`；本机 2.0.30 已下载、待重启安装）。

### 9.3 端口 49374 冲突 / 共享服务异常 <a id="port-49374"></a>

- 共享服务默认监听 `127.0.0.1:49374`，由桌面端内嵌 CLI 托管、随桌面端启停（本机实测监听进程即 `%APPDATA%\ai.opencode.desktop\cli\2.0.29-x64\opencode-cli.exe`）；
- 另有独立 `opencode serve` 常驻时会占用同一端口：先 `Get-NetTCPConnection -LocalPort 49374 -State Listen` 看归属，再用 `opencode service status` / `restart` 处置；不希望共用后台服务时用 `opencode --standalone`。

## 10. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc Windows 侧开发设施汇总（opencode 在其中的定位）
- 《[opencode部署使用说明](../linux/opencode部署使用说明.md)》：linux 侧同名文档（v1 → v2 迁移、配置字段对照、Web 与手机访问、GPU / sudo 沙箱排障）
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：另一 AI 编码工具（Windows 侧；MCP 登记与浏览器真机验证）
- 《[VSCode部署使用说明](VSCode部署使用说明.md)》：编辑器与 `.vscode` 双平台配置口径
- 《[llamacpp部署使用说明](../../AI/llamacpp部署使用说明.md)》：`llamacpp` provider 的后端推理服务
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定
- 《[本地资源](../../../用户文档/本地资源.md)》：mjpc 相关机器信息取值（已 gitignore）

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc（Windows 侧）本机核实结果（opencode CLI / 桌面端 2.0.29、路径与共享服务实测、MCP mjw-vision 退役）
