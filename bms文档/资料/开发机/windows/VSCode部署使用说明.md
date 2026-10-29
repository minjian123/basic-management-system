# VS Code 部署使用说明

> mjpc 开发机 Windows 侧 Visual Studio Code（用户级安装 stable 1.142.0）部署、扩展与调试口径 · 2026-10-16 本机采集

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › VS Code 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[google-chrome部署使用说明 →](google-chrome部署使用说明.md)　[playwright部署使用说明 →](playwright部署使用说明.md)　[opencode部署使用说明 →](opencode部署使用说明.md)　[linux 侧同名文档 →](../linux/VSCode部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** Windows 侧（Windows 11 专业版，与 Ubuntu 26.04 双系统同机）上 **Visual Studio Code 官方版**的部署与使用：安装形态与版本、`code` 命令行、用户数据目录、已装扩展、工作区打开口径，以及**运行与调试的双平台口径**（`bms/.vscode/` 的 `launch.json` / `tasks.json` 在 Windows 上走 `pnpm.cmd`、系统 Chrome 绝对路径与 `.venv\Scripts\python.exe` 平台覆盖）。

Ubuntu 侧同名文档《[VSCode部署使用说明](../linux/VSCode部署使用说明.md)》记录 apt 官方源安装与「源代码管理面板看不到仓库」的成因与修复；两侧是同一份工作区配置，差异只在系统路径与平台覆盖。

> **取值说明**：本文路径用 `%APPDATA%` / `%LOCALAPPDATA%` / `%USERPROFILE%` 环境变量写法（开发用户为 `minjian`）；账号与令牌类信息不在本文记录，以本机登录态与《[本地资源](../../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 环境概览 <a id="env"></a>

| 项 | 取值 |
| --- | --- |
| 系统 | Windows 11 专业版（10.0.26300）；CPU i7-13700K / 64 GB；主机名 `MJPC` |
| 应用 | Visual Studio Code 官方版（stable） |
| 版本 | **1.142.0**（commit `6d62b1d5dace93a33b3a6d3eca1317bd5e15bcb1`，x64） |
| 安装形态 | **用户级安装**（User Installer），装于 `%LOCALAPPDATA%\Programs\Microsoft VS Code\`（`Code.exe`、版本目录 `6d62b1d5da\`、卸载器 `unins000.exe`） |
| CLI | `code`（`%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd`；用户 PATH 已含该 `bin` 目录） |
| 用户数据 | `%APPDATA%\Code\`（设置、工作区状态、日志；2026-10-16 快照约 186 MB） |
| 扩展宿主 | `%USERPROFILE%\.vscode\`（`extensions\`、`argv.json`；快照约 225 MB） |
| 界面语言 | 中文（`%USERPROFILE%\.vscode\argv.json` 的 `locale = zh-cn`） |
| 工作区 | `D:\Develop\bizs`（工作区文件 `bizs.code-workspace`，多根） |

## 3. 安装形态与用户数据 <a id="install"></a>

### 3.1 安装形态与升级 <a id="install-form"></a>

本机为**用户级安装**：程序装在当前用户目录（`%LOCALAPPDATA%\Programs\Microsoft VS Code`），不需要管理员权限，升级也不弹 UAC；系统级安装（Program Files）与商店版均未使用。

- 版本核实见[第 6 节](#verify)；卸载用安装目录内的 `unins000.exe`（用户级卸载，**不会**删除 `%APPDATA%\Code` 与 `%USERPROFILE%\.vscode` 用户数据）。
- 升级：应用内更新检查（默认开启），或从官网下载新版 User Setup 覆盖安装；两者都不影响已装扩展与设置。
- 与 CodeBuddy 的关系：同为基于 Electron 的编辑器/IDE，**用户数据目录各自独立**（VS Code 用 `%APPDATA%\Code`；CodeBuddy 的目录见同目录《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》），可并存、互不干扰。

### 3.2 用户数据目录 <a id="dirs"></a>

| 目录 | 内容 | 说明 |
| --- | --- | --- |
| `%APPDATA%\Code\User\settings.json` | 用户设置（本机现有少量项：主题 `One Dark Modern`、`editor.unicodeHighlight.nonBasicASCII=false`、`window.openFoldersInNewWindow=on`） | 对应 linux 侧 `~/.config/Code/User/settings.json` |
| `%APPDATA%\Code\User\workspaceStorage\<hash>\state.vscdb` | 工作区状态（含 SCM 面板的仓库可见性） | 问题口径见《[VSCode部署使用说明](../linux/VSCode部署使用说明.md)》「源代码管理面板看不到仓库」节 |
| `%USERPROFILE%\.vscode\extensions\` | 已装扩展 | 扩展宿主目录 |
| `%USERPROFILE%\.vscode\argv.json` | 持久启动参数（`locale`，本机 `zh-cn`） | linux 侧为 `~/.vscode/argv.json` |

## 4. 扩展管理 <a id="extensions"></a>

### 4.1 已装扩展（2026-10-16 实测） <a id="ext-installed"></a>

`code --list-extensions --show-versions` 实测清单：

| 扩展 | 版本 | 用途 |
| --- | --- | --- |
| `ms-python.python` | 2026.10.0 | Python 解释器管理与调试入口 |
| `ms-python.debugpy` | 2026.6.0 | 调试适配器（`launch.json` 里 `type: debugpy` 的后端调试项依赖它） |
| `ms-python.vscode-pylance` | 2026.4.101 | Python 语言服务（跳转 / 补全 / 类型检查） |
| `ms-python.vscode-python-envs` | 1.40.0 | 环境管理（与 python 扩展配套） |
| `vue.volar` | 3.3.13 | Vue 3 语言支持 |
| `ms-ceintl.vscode-language-pack-zh-hans` | 1.131.2026090407 | 中文语言包 |
| `cweijan.vscode-office` | 4.2.2 | Office 文件预览 |
| `davidanson.vscode-markdownlint` | 0.62.1 | Markdown 规范检查 |

> Python / Vue「五件套」（python、debugpy、pylance、python-envs、volar）已齐。

### 4.2 安装、卸载与建议补装 <a id="ext-cli"></a>

```powershell
code --list-extensions --show-versions      # 列出已装扩展
code --install-extension <发布者.扩展名>    # 从市场安装
code --uninstall-extension <发布者.扩展名>  # 卸载
```

工作区推荐扩展见 `bms/.vscode/extensions.json`（Volar、Python 三件、ESLint、Prettier）；本机未装的可按需补：

```powershell
# md 文档里的 mermaid 图形预览：VS Code 1.142 起由**内置扩展** `mermaid-markdown-features` 提供，无需另装
# （**勿装** `bierner.markdown-mermaid`：两者会抢注同名 `markdown-mermaid.*` 配置键，日志持续刷「无法注册…此属性已注册」；
#   详见 `bms/.vscode/extensions.json` 注释与《文档生成规范》「图形与示意图」节）
# 前端 lint / 格式化（按需）
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
```

## 5. 工作区与调试 <a id="workspace"></a>

### 5.1 打开工作区 <a id="workspace-open"></a>

```powershell
code D:\Develop\bizs\bizs.code-workspace     # 工作区文件打开（推荐）
code D:\Develop\bizs                         # 裸目录打开（等价，状态独立）
```

工作区文件为多根：**工作区（配置）** / **BMS 基座/平台** / **biz 产品** / **mdm 主数据** / **测试资产**。

> 工作区文件打开与裸目录打开会生成**不同的 `workspaceStorage` hash 目录**，各自的编辑器与 SCM 状态互相独立（linux 侧同口径）。

### 5.2 运行与调试（双平台口径） <a id="debug"></a>

「运行和调试」下拉由**被打开根**的 `.vscode/launch.json` 与 `.vscode/tasks.json` 驱动，本仓库有两处落点（内容同套、须同步维护）：工作区根 `D:\Develop\bizs\.vscode\` 与基座根 `D:\Develop\bizs\bms\.vscode\`。

**基座根 `bms/.vscode/` 已做双平台平台覆盖**（Windows 取值实测有效）：

```jsonc
// bms/.vscode/launch.json（节选）
"runtimeExecutable": "pnpm",
"windows": { "runtimeExecutable": "pnpm.cmd" },                      // Node/pnpm 类启动项
"runtimeExecutable": "/usr/bin/google-chrome",
"windows": { "runtimeExecutable": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" },  // 浏览器断点项
"python": "${workspaceFolder}/backend/.venv/bin/python",
"windows": { "python": "${workspaceFolder}/backend/.venv/Scripts/python.exe" },                    // 后端 debugpy 项
```

- 任务统一走 `python3 scripts/tools/dev/*.py`（dev 工具脚本为「Python 单一实现 + Linux `.sh` / Windows `.bat` 薄包装」）：端口自愈 `清理宿主端口.py`、5002 模块产物服务 `确保模块产物服务.py`、后端本地全套 `本地全套.py up/down`；本机的 `python3` 为 `%LOCALAPPDATA%\Programs\Python\Python314\python3.exe`（Python 3.14.4）。
- 后端「本地全套」现为**按各仓声明装载**（固定路径 `deploy/local_stack.toml`；缺省 tenant / platform / identity + mdm 组织主数据，同一 8000 端口 + loopback 别名；寻址经 `[service_client].endpoints` 注入，不依赖系统 hosts）。
- `backend\.venv` 为指向本地依赖仓的 **junction**（外置与还原脚本见 `bms/scripts/tools/deps/`），Windows 下解释器路径为 `.venv\Scripts\python.exe`。
- **产品进程断点**（mdm 等）：产品服务模块与其 venv 都在产品仓，`backend/ops/dev_run.py` 只能 `runpy` 本仓模块，故改由 IDE **原生 `module` 启动 + `envFile`**——`本地全套.py up`（收尾自动）或 `env` 按声明为每个服务写 `<仓>\deploy\.dev-env.<服务键>.local`（别名 / 8000 / 端点覆盖 / 开发密钥），工作区根启动项「后端：产品服务（debugpy · mdm）」即用它：`本地全套.py stop mdm` → 启动该项 → 调试完 `up` 补回。

> **注意（现状）**：工作区根 `D:\Develop\bizs\.vscode\` 的 `launch.json` / `tasks.json` **仍是 Linux 口径**（`bash` 调 `.sh`、`/usr/bin/google-chrome`、`backend/.venv/bin/python`）——Windows 下请在 `bizs.code-workspace` 里选 **「BMS 基座/平台」根**（或单独打开 `bms`）使用基座根那套双平台配置。

## 6. 验证 <a id="verify"></a>

```powershell
code --version                              # 1.142.0 / 6d62b1d5da… / x64
(Get-Command code).Source                   # …\Microsoft VS Code\bin\code.cmd
code --list-extensions --show-versions      # 已装扩展清单
code D:\Develop\bizs\bizs.code-workspace    # 打开工作区
```

## 7. 常见问题 <a id="troubleshoot"></a>

| 现象 | 处理 |
| --- | --- |
| 怎么启动（开始菜单 / 命令行） | 开始菜单条目 **Visual Studio Code**（AppID `Microsoft.VisualStudioCode`）；命令行 `code .`（当前目录）、`code <目录>`；也可直接跑 `%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe` |
| `code` 命令不可用 | 用户 PATH 已含 `…\Microsoft VS Code\bin`；**装完或改了 PATH 后须新开终端**（当前终端不会自动刷新）；仍未生效就用上一行的 `Code.exe` |
| 扩展下载慢 / 失败 | 扩展走 VS Code 市场（与 npm 无关；npmmirror 全局镜像只作用于 pnpm/npm，见 `%USERPROFILE%\.npmrc`）；必要时在用户设置配 `http.proxy`，或用离线包 `code --install-extension <文件.vsix>` |
| 「运行和调试」下拉为空 | VS Code 只读**被打开根**的 `.vscode/`；工作区文件打开时选「BMS 基座/平台」根（双平台版）；工作区根那份当前仍是 Linux 口径（见[5.2](#debug)） |
| Python 报「无法解析导入 sqlalchemy」类 | 工作区设置的 `python.defaultInterpreterPath` 写的是 Linux 形式（`backend/.venv/bin/python`）；手动切换解释器到 `D:\Develop\bizs\bms\backend\.venv\Scripts\python.exe` 即可 |
| 源代码管理面板看不到仓库 / 变更 | 本机 Windows 侧未复现；成因、`state.vscdb` 键与修复脚本见《[VSCode部署使用说明](../linux/VSCode部署使用说明.md)》「源代码管理面板看不到仓库」节（脚本按 Linux 口径探测，Windows 上需以 `--user-data-dir` 显式指向 `%APPDATA%\Code`） |
| 「全套」起好后登录报 **502** | 前端 `/api` 未就近代理，回落到缺省网关 `http://localhost:8088`（本机无此网关）：`frontend\apps\desktop\.env.local` 缺 `VITE_LOCAL_API`——跑一次 `python3 scripts\tools\dev\本地全套.py up`（收尾自动补）或 `本地全套.py env`；**新增 `.env.local` 后须让 vite 重载配置**（重启「前端：宿主 dev」任务）。详见《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》「调试排障」节 |
| 登录后**刷新 / 深链直开**菜单页落 404 | 路由守卫重解析判定的实施期缺陷（`router.hasRoute(path)` 参数实为路由 name），**2026-10-18 已修**；若仍复现先确认宿主代码已更新（`git pull` + 重启 dev 任务）。详见《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》「调试排障」节 |

## 8. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc Windows 侧开发设施汇总（VS Code 在其中的定位）
- 《[VSCode部署使用说明](../linux/VSCode部署使用说明.md)》：linux 侧同名文档（apt 安装、扩展沿用、SCM 面板修复）
- 《[google-chrome部署使用说明](google-chrome部署使用说明.md)》：浏览器断点所用的系统 Chrome（launch.json 的 Windows 覆盖即指向它）
- 《[opencode部署使用说明](opencode部署使用说明.md)》：本机另一 AI 编码工具（Windows 侧 CLI 与桌面端）
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定
- 《[本地资源](../../../用户文档/本地资源.md)》：mjpc 相关机器信息取值（已 gitignore）

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc（Windows 侧）本机核实结果
