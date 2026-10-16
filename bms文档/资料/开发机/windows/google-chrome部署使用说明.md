# google-chrome 部署使用说明

> mjpc 开发机 Windows 侧 Google Chrome（企业版 MSI 安装；Playwright 真机验证与 IDE 浏览器断点的首选内核）部署与使用 · 2026-10-16 本机采集

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › google-chrome 部署使用说明　|　[同级：playwright部署使用说明 →](playwright部署使用说明.md)　[VSCode部署使用说明 →](VSCode部署使用说明.md)　[开发机部署使用说明总览 →](开发机部署使用说明总览.md)　[linux 侧同名文档 →](../linux/google-chrome部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** Windows 侧（Windows 11 专业版）上 **Google Chrome** 的部署与使用口径：为什么用**企业版 MSI** 安装、自动更新由谁承担、与系统自带 Edge 的分工、独立 profile 与远程调试端口自检，以及它与 [Playwright](playwright部署使用说明.md) / [VS Code](VSCode部署使用说明.md) 调试链路的关系。

配套文档：

- 《[playwright部署使用说明](playwright部署使用说明.md)》：Playwright 走**系统 Chrome**（不下载 ms-playwright 内核）的口径
- 《[VSCode部署使用说明](VSCode部署使用说明.md)》：`launch.json` 的 Windows 平台覆盖指到本文的 `chrome.exe` 路径
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：IDE 内浏览器真机验证（Playwright MCP）的登记与用法
- 《[google-chrome部署使用说明](../linux/google-chrome部署使用说明.md)》：linux 侧同名文档（apt 官方源安装）

> **取值说明**：路径按 Windows 写法；凭据类信息不在本文记录。

## 2. 背景与结论 <a id="background"></a>

Windows 侧存在**两个** Chromium 系浏览器，用途不同：

| 类别 | 来源 | 版本 | 本机取舍 |
| --- | --- | --- | --- |
| 系统 Microsoft Edge | 随 Windows 自带（`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`） | **155.0.4283.60** | 保留（系统组件）；Playwright 需要时可 `--browser=msedge` |
| **系统 Google Chrome** | **企业版 MSI**（离线安装包，系统级） | **155.0.8059.85** | **首选**：Playwright 真机验证 + IDE 浏览器断点 |

**结论**：Chrome 作为 Windows 侧唯一的「首选浏览器内核」；Edge 并存不冲突；Playwright 自带的 ms-playwright Chromium **不下载**（见[playwright部署使用说明](playwright部署使用说明.md)「浏览器内核口径」节）。

选择**企业版 MSI** 的理由：

- 系统级安装（`C:\Program Files`）与 MSI 卸载登记，安装/卸载走标准 Windows Installer（`MsiExec`），便于集中管理与核对；
- 自动更新由独立的 **Google Updater**（用户级计划任务）承担，可通过 Google Update 组策略统一接管（本机未设策略，见[3.2](#update)）；
- 供自动化与 IDE 使用**系统 Chrome** 内核，免去下载 Playwright 浏览器内核（省磁盘；本机 `%LOCALAPPDATA%\ms-playwright` 为空）。

## 3. 技术环境与更新 <a id="environment"></a>

### 3.1 版本与路径速查 <a id="env-quick"></a>

| 项 | 取值 |
| --- | --- |
| 版本 | **Google Chrome 155.0.8059.85**（程序目录内含同名版本子目录 `155.0.8059.85\`） |
| 可执行文件 | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| 安装形态 | **企业版 MSI**：卸载登记 `WindowsInstaller=1`、卸载串 `MsiExec.exe /X{0228B730-26AA-39E9-B2E1-0FC0E3EA58C8}` |
| 注册表卸载登记 | `DisplayName = Google Chrome`、`DisplayVersion = 155.0.8059.85`、`Publisher = Google LLC` |
| 开始菜单 | 条目 **Google Chrome**（AppID `Chrome`） |
| 更新服务 | 用户级 **Google Updater 157.0.8089.0**（`%LOCALAPPDATA%\Google\GoogleUpdater\157.0.8089.0\updater.exe`） |
| 更新计划任务 | `GoogleUpdaterTaskUser157.0.8089.0{…}`（State `Ready`）；**无** `gupdate` / `gupdatem` 服务（新版更新器为用户级计划任务形态） |
| 更新客户端登记 | `HKLM\SOFTWARE\WOW6432Node\Google\Update\Clients\{8A69D345-D564-463c-AFF1-A69D9E530F96}` → `name=Google Chrome`、`pv=155.0.8059.85` |
| 用户数据目录 | `%LOCALAPPDATA%\Google\Chrome\User Data`（**实测尚未生成**：Chrome 迄今以独立 `--user-data-dir` 启动；首次交互启动会自动创建） |
| 主要用途 | ① Playwright 真机验证（`--browser=chrome`）；② IDE 浏览器断点；③ 日常浏览 |

### 3.2 更新通道 <a id="update"></a>

本机 Chrome 的更新由**用户级 Google Updater** 承担（计划任务按周期检查、静默下载与安装），**未下发任何 Google Update 策略**（实测 `HKLM:\SOFTWARE\Policies\Google\Update`、`HKLM:\SOFTWARE\Policies\Google\Chrome` 均无键）——即自动更新按默认开启。

```powershell
# 核实更新器与计划任务
Get-ScheduledTask -TaskName 'GoogleUpdater*' | Select-Object TaskName, State
# 核实更新客户端登记的当前版本
Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Google\Update\Clients\{8A69D345-D564-463c-AFF1-A69D9E530F96}' |
  Select-Object name, pv
```

需要接管自动更新（延后 / 停用 / 指定通道）时，按 Google Update 的企业策略下发（本机未做）；策略键位与取值以 Google 官方文档为准。

### 3.3 与 linux 侧对比 <a id="env-diff"></a>

| 维度 | Windows（本文） | linux（[同名文档](../linux/google-chrome部署使用说明.md)） |
| --- | --- | --- |
| 安装形态 | 企业版 MSI（离线安装包） | `google-chrome-stable` deb，apt 官方源 |
| 可执行文件 | `C:\Program Files\Google\Chrome\Application\chrome.exe` | `/usr/bin/google-chrome` |
| 更新通道 | 用户级 Google Updater（计划任务） | 随 `apt upgrade` |
| 用户数据目录 | `%LOCALAPPDATA%\Google\Chrome\User Data` | `~/.config/google-chrome/` |
| 备用内核 | Edge（系统自带，`--browser=msedge`） | snap Chromium（备用） |
| Playwright 口径 | **一致**：走系统 Chrome（`--browser=chrome`），不装 ms-playwright 内核 | 同 |

## 4. 使用 <a id="usage"></a>

### 4.1 IDE 浏览器断点 <a id="usage-ide"></a>

`bms/.vscode/launch.json` 的浏览器调试项已做 Windows 平台覆盖（`windows.runtimeExecutable`），js-debug 用绝对路径启动本机 Chrome：

```jsonc
// bms/.vscode/launch.json（节选）
"runtimeExecutable": "/usr/bin/google-chrome",
"windows": { "runtimeExecutable": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" }
```

可用断点能力：页面 JS、Vue 组件源码（`webRoot` 指向 `bms/frontend/apps/desktop/src`，sourcemap 由 Vite 提供）。工作区根 `.vscode/` 的对应项仍是 Linux 口径，Windows 下用基座根那套（见《[VSCode部署使用说明](VSCode部署使用说明.md)》「运行与调试（双平台口径）」节）。

### 4.2 Playwright 真机验证 <a id="usage-playwright"></a>

```powershell
cd D:\Develop\bizs
playwright-cli open --browser=chrome http://localhost:5173/login-check.html
playwright-cli close
```

口径：**首选 `--browser=chrome`**（系统 Chrome，不依赖 ms-playwright 内核）；`--browser` 取值限 `chrome` / `firefox` / `webkit` / `msedge`（**不接受 `chromium`**）。长会话首选 CodeBuddy 的 Playwright MCP（`--browser chrome`），选型与用法见《[playwright部署使用说明](playwright部署使用说明.md)》。

### 4.3 独立 profile 与远程调试端口 <a id="usage-debug-port"></a>

自动化与调试**一律用独立 `--user-data-dir`**（不污染日常 profile）；调试端口自检（CDP）实测可用：

```powershell
$probe = Join-Path $env:TEMP 'chrome-probe-9231'
Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList `
  '--headless=new', '--no-first-run', '--disable-gpu', '--remote-debugging-port=9231', "--user-data-dir=$probe", 'about:blank'
Start-Sleep -Seconds 6
Invoke-RestMethod http://127.0.0.1:9231/json/version | ConvertTo-Json -Compress   # 应返回 Browser / Protocol-Version
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*\Google\Chrome\*' } | Stop-Process -Force
Remove-Item -Recurse -Force $probe -ErrorAction SilentlyContinue
```

2026-10-16 实测返回 `"Browser": "Chrome/155.0.8059.85"`、`"Protocol-Version": "1.3"`。

## 5. 验证 <a id="verify"></a>

```powershell
# 1) 版本（chrome.exe 不向控制台打印版本，用 VersionInfo 或注册表核实）
(Get-Item 'C:\Program Files\Google\Chrome\Application\chrome.exe').VersionInfo | Select-Object ProductVersion, ProductName
# 2) MSI 安装登记
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' |
  Where-Object DisplayName -eq 'Google Chrome' |
  Select-Object DisplayName, DisplayVersion, Publisher, WindowsInstaller
# 3) 远程调试可用性自检：见 4.3 的命令块
```

## 6. 常见问题 <a id="troubleshoot"></a>

| 现象 | 处理 |
| --- | --- |
| `chrome --version` 没有输出 / 弹出一个窗口 | Chrome 是 GUI 程序，**不向控制台打印版本**；用[第 5 节](#verify)的 `VersionInfo` 或卸载登记查版本 |
| 想核实 / 限制自动更新 | 更新由用户级 Google Updater 承担（`Get-ScheduledTask -TaskName 'GoogleUpdater*'` 可见）；本机未设策略，需要接管时按 Google Update 企业策略下发（见[3.2](#update)） |
| 与 Edge 冲突吗 | 不冲突：各自的可执行文件、profile 与更新通道；Playwright 用 `--browser=chrome`（首选），需要时也可 `--browser=msedge` |
| 调试端口连不上 / 提示 profile 正在使用 | 同一 `--user-data-dir` 被别的实例占用；自动化务必给**独立目录**（如 `%TEMP%` 下），再用 `Invoke-RestMethod http://127.0.0.1:<端口>/json/version` 自检（见[4.3](#usage-debug-port)） |
| 代理 | 本机系统代理**未启用**（`ProxyEnable=0`、无 PAC），Chrome 直连；需要代理时给自动化实例加 `--proxy-server=...`，勿动日常 profile |

## 7. 关联文档 <a id="related"></a>

- 《[playwright部署使用说明](playwright部署使用说明.md)》：Playwright 走系统 Chrome 的内核口径与命令
- 《[VSCode部署使用说明](VSCode部署使用说明.md)》：浏览器断点的平台覆盖（`launch.json`）
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：IDE 浏览器真机验证（Playwright MCP）的登记与用法
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc Windows 侧开发设施汇总
- 《[google-chrome部署使用说明](../linux/google-chrome部署使用说明.md)》：linux 侧同名文档（apt 安装与 snap Chromium 备用口径）
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc（Windows 侧）安装与验证结果
