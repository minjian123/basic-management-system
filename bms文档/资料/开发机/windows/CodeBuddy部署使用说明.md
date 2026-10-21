# CodeBuddy 部署使用说明

> mjpc 开发机 Windows 11 侧 CodeBuddy CN（应用 1.106.1 / 安装器 4.12.2）部署、配置、权限、扩展管理、运行调试与浏览器真机验证（Playwright MCP）实录 · 2026-10-15 安装 / 2026-10-16 事实核实 / 2026-10-21 权限与免确认设置（全 13 类放开）

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › CodeBuddy 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[google-chrome部署使用说明 →](google-chrome部署使用说明.md)　[playwright部署使用说明 →](playwright部署使用说明.md)　[VSCode部署使用说明 →](VSCode部署使用说明.md)　[linux 版 CodeBuddy 部署使用说明 →](../linux/CodeBuddy部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（同机双系统：Ubuntu + Windows 11，本文为 **Windows 侧**）上 **CodeBuddy CN** 的部署与使用：安装形态与版本、用户数据目录、首次配置与权限现状、扩展管理与 HTML 文档预览、**运行与调试（`bms/.vscode/` 双平台启动项与任务）**、**浏览器真机验证（Playwright MCP）** 与排障入口，并单列「[与 linux 版差异](#diff-linux)」一节。

本文档与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》（windows 侧总览）配套；同机 Ubuntu 侧的部署与排障记录见《[CodeBuddy 部署使用说明](../linux/CodeBuddy部署使用说明.md)》（linux 侧）。两侧**同一个 bms 仓库、同一套 `.vscode/` 配置**，差异只在平台取值（见第 11 节）。

**取值说明**：开发用户为 `minjian`，用户目录统写作 `~`（即 `C:\Users\minjian`）；内网地址、账号与口令等凭据不入本文，以《[本地资源](../../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 环境与路径速查 <a id="env"></a>

### 2.1 应用与安装 <a id="env-app"></a>

| 项           | 取值                                                                                     |
| ------------ | ---------------------------------------------------------------------------------------- |
| 系统         | Windows 11 专业版 26H2（Build 26300，x64）                                               |
| 硬件         | i7-13700K / 64 GB / RTX 4090（与 Ubuntu 侧同机硬件）                                     |
| 应用名称     | CodeBuddy CN（`applicationName = buddycn`、`urlProtocol = codebuddycn`）                 |
| 应用版本     | **1.106.1**（stable；commit `425ab70e`，构建日期 2026-10-13）                            |
| 安装器版本   | `4.12.2`（`CodeBuddy CN.exe` 的 ProductVersion；linux 侧 deb 包为 4.12.0）               |
| 安装形态     | **用户级安装器**（装在用户目录、无需管理员；卸载程序 `unins000.exe`）                    |
| 安装目录     | `%LOCALAPPDATA%\Programs\CodeBuddy CN\`（主程序 `CodeBuddy CN.exe`）                     |
| CLI          | **`buddycn`** / **`buddycn.cmd`**（`...\CodeBuddy CN\bin\` 下的包装脚本，置 `ELECTRON_RUN_AS_NODE=1` 转调应用自带 `cli.js`），**已在用户 PATH** |
| 扩展市场     | open-vsx.org（`product.json` → `extensionsGallery.serviceUrl`），非微软市场              |
| 更新地址     | `product.json` → `updateUrl = https://copilot.tencent.com`                               |

> CLI 命令名是 **`buddycn`**（不是 `codebuddy`，PATH 中也没有 `codebuddy`）；`buddycn --help` 与 VS Code CLI 同款，含 `--list-extensions` / `--install-extension` 等（见 [7.2](#ext-install)）。

### 2.2 版本核实命令 <a id="env-cmds"></a>

```powershell
buddycn --version                        # 1.106.1 + commit 425ab70e… + x64
buddycn --list-extensions --show-versions
where.exe buddycn                        # …\CodeBuddy CN\bin\buddycn、…\bin\buddycn.cmd（两行）
python3 -c "import json,os;print(json.load(open(os.path.join(os.environ['LOCALAPPDATA'],'Programs','CodeBuddy CN','resources','app','product.json'),encoding='utf-8'))['version'])"
```

### 2.3 路径速查 <a id="env-paths"></a>

| 用途                              | 路径 / 命令                                                                                  |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| IDE 用户设置（含权限开关）        | `%APPDATA%\CodeBuddy CN\User\settings.json`                                                  |
| 权威设置存储（安全类别 / 自动审批） | `%APPDATA%\CodeBuddy CN\User\globalStorage\state.vscdb`（SQLite，键 `CodeBuddy.settings`）    |
| AI 侧配置（插件登记 / MCP / 技能） | `~\.codebuddy\`（`settings.json`、`mcp.json`、`plugins\`、`skills-marketplace\`）             |
| 扩展宿主                          | `~\.codebuddycn\extensions\`（另有 `argv.json`）                                             |
| 对话与扩展日志                    | `%LOCALAPPDATA%\CodeBuddyExtension\Logs\CodeBuddyIDE\<日期>\<工作区名>__<hash>.log`          |
| IDE 日志 / 崩溃转储               | `%APPDATA%\CodeBuddy CN\logs\<时间戳>\`、`...\CrashReport\`                                  |
| Chrome（调试与 MCP 复用）         | `C:\Program Files\Google\Chrome\Application\chrome.exe`（本机 155.0.8059.85）                |
| Node / pnpm / npx                 | nvm-windows `.nodejs` 目录：node **v24.20.0**、pnpm **11.7.0**、npx 11.19.0                   |
| Python                            | `%LOCALAPPDATA%\Programs\Python\Python314\python.exe`（**3.14.4**，同目录含 `python3.exe`） |
| Python 启动器                     | `%LOCALAPPDATA%\Programs\Python\Launcher\py.exe`                                             |
| uv（后端依赖工具链）              | `%LOCALAPPDATA%\Programs\Python\Python314\Scripts\uv.exe`（**0.12.7**，已入用户 PATH；索引走 TUNA：`%APPDATA%\uv\uv.toml`） |
| Git / Git Bash                    | `C:\Program Files\Git\cmd\git.exe`、`C:\Program Files\Git\bin\bash.exe`                      |
| 终端                              | PowerShell **7.6.7**（`C:\Program Files\PowerShell\7\`）、Windows Terminal（`wt.exe`）；Windows PowerShell 5.1 并存 |
| 工作区 / bms 仓库                 | `D:\Develop\bizs`、`D:\Develop\bizs\bms`                                                     |
| 截图与临时产物                    | 工作区根 `tmp\`（不入库）                                                                     |

> **`python3` 可用**：Python 3.14 安装时把 `%LOCALAPPDATA%\Programs\Python\Python314\`（含 `python.exe` / `python3.exe`）写进**用户 PATH**，顺序在 Microsoft Store 别名目录（`...\WindowsApps`）之前，故**新开的终端里 `python3` 即真实解释器**；沿用旧环境变量的终端可能仍命中商店占位别名（排障见 [10.2](#trouble-entry)）。项目脚本与 IDE 任务统一用 `python3 xxx.py` 口径（与 linux 侧一致）。

## 3. 安装与升级 <a id="install"></a>

### 3.1 安装形态 <a id="install-form"></a>

CodeBuddy CN 通过官网安装器以**用户级**方式安装到 `%LOCALAPPDATA%\Programs\CodeBuddy CN\`（无需管理员、不写系统目录），**没有包管理器来源**（不随 winget / 应用商店升级）：

- 版本核实两处：**安装器版本**取 `CodeBuddy CN.exe` 的 ProductVersion（当前 4.12.2），**应用版本**取 `product.json` 的 `version` 或 `buddycn --version`（当前 1.106.1）——两套编号体系不同，与 linux 侧「deb 包 4.12.0 ↔ 应用 1.106.1」同口径；
- 卸载：运行安装目录下的 `unins000.exe`（或「设置 → 应用」里卸载）。**用户数据独立于安装目录**（见第 4 节），卸载安装目录不影响 `%APPDATA%\CodeBuddy CN`、`~\.codebuddy`、`~\.codebuddycn` 下的登录态与配置；
- CodeBuddy 与 [opencode](opencode部署使用说明.md)、[deepseek-harness](../../AI/linux/deepseek_harness部署使用说明.md) 等 AI 编码工具互不干扰、各自独立部署（opencode / dsh 的本机部署见对应文档，linux 侧同名文档为准）。

### 3.2 升级 <a id="install-upgrade"></a>

```powershell
# 1) 从官网（www.codebuddy.ai）下载新版安装器；或走应用内更新（product.json 的 updateUrl = copilot.tencent.com）
# 2) 运行安装器覆盖安装到同一目录（用户数据保留）
# 3) 重启 IDE；如出现异常先看日志（见 10.2）
# 4) 核实版本
buddycn --version
```

> 升级后若扩展宿主报异常，先「重新加载窗口」；仍异常时按 [7.5](#ext-trouble) 检查扩展目录。

## 4. 用户数据目录 <a id="dirs"></a>

CodeBuddy 的用户数据分散在 **四个目录**（体积为 2026-10-16 本机快照，仅作量级参考；工作区根另有 `.codebuddy/`，本机 Windows 侧尚未生成）：

| 目录                                | 体积  | 内容                                                                                                                                                                                                                                                                                     | 说明                                           |
| ----------------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `%APPDATA%\CodeBuddy CN\`           | 88 MB | `User\settings.json`（**IDE 设置，含权限开关**）、`User\globalStorage\state.vscdb`（权威设置存储）、`logs\<时间戳>\`、`CrashReport\`、`workspaceStorage\`、`Local Storage\`                                         | 与 VS Code 一致的用户数据布局（对应 linux 侧 `~/.config/CodeBuddy CN`） |
| `~\.codebuddycn\`                   | 3 MB  | `extensions\`（已装扩展 + `extensions.json`）、`argv.json`（持久启动参数）                                                                                                                                                                                                              | 扩展宿主目录                                   |
| `~\.codebuddy\`                     | 106 MB | `settings.json`（**插件启用登记**）、`mcp.json`（MCP server 登记）、`plugins\`（插件市场）、`skills-marketplace\`（技能市场）、`inspiration\`、`memery\`（用户级记忆）、`expert-history.json`                                                                                          | CodeBuddy AI 侧配置（与 IDE 设置分开）         |
| `%LOCALAPPDATA%\CodeBuddyExtension\` | 1 MB  | `Logs\CodeBuddyIDE\<日期>\<工作区名>__<hash>.log`（如 `bizs__….log`、`unknown-workspace__….log`）、`Data\`（会话与工作区缓存）                                                                                                                                                        | **对话与扩展运行日志**，排障首选               |

清理建议：`logs\`、`Logs\`、`CrashReport\` 属可清缓存；`User\settings.json`、`~\.codebuddy\settings.json`、`argv.json`、`state.vscdb` 属配置，勿随意删。

## 5. 首次配置 <a id="setup"></a>

| 项                     | 位置 / 键                                                                        | 本机现状（2026-10-16 核实）                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 界面语言               | `~\.codebuddycn\argv.json` → `locale`                                          | `zh-cn`                                                                                                                          |
| 崩溃上报               | `~\.codebuddycn\argv.json` → `enable-crash-reporter`                           | `false`（关闭上报）                                                                                                              |
| 硬件加速               | `~\.codebuddycn\argv.json` → `disable-hardware-acceleration`                   | 注释态（未启用软件渲染）                                                                                                         |
| 插件启用               | `~\.codebuddy\settings.json` → `enabledPlugins`                                | 8 项官方插件：`pptx`、`pdf`、`docx`、`xlsx`、`agent-browser`、`playwright-cli`、`skills-sec-audit`、`find-skills`           |
| 插件 / 技能市场        | `~\.codebuddy\plugins\`、`~\.codebuddy\skills-marketplace\`                    | 已拉取官方市场（版本号见 `~\.codebuddy\.skills-marketplace-version`）                                                            |
| MCP server             | `~\.codebuddy\mcp.json`                                                        | 已登记 **Playwright MCP**（`mcp__playwright__*`，系统 Chrome + 隔离会话）；登记原文与用法见[第 9 节](#browser-mcp)               |
| 补全模型               | `codingcopilot.selectedCompletionModel`                                        | 空值 = 使用默认模型                                                                                                              |
| 提交信息风格           | `codingcopilot.commitMessageStyle` / `codingcopilot.commitMessageLanguage`   | `Auto` / `zh_CN`                                                                                                               |
| 编辑器关联（双击行为） | `%APPDATA%\CodeBuddy CN\User\settings.json` → `workbench.editorAssociations` | 本机 Windows 侧**未设置**（双击 html 默认打开源码）；需要时按 [7.3](#html-preview) 补                                              |

> 登录与账号：以 IDE 内登录态为准（凭据不入文档）；退出登录后插件市场与技能市场会重新校验。

## 6. 权限与免确认设置 <a id="permission"></a>

CodeBuddy 的权限开关都在 **IDE 用户设置** `%APPDATA%\CodeBuddy CN\User\settings.json`（键前缀 `codingcopilot.`），与 `~\.codebuddy\settings.json`（插件登记）不是同一个文件；其中**安全类别**的权威值另存于 `state.vscdb`（见 [6.2](#permission-apply)）。

### 6.1 本机当前取值 <a id="permission-current"></a>

| 位置 / 键                                                                                    | 本机值                                                                                                                                                                                                                                                              | 含义                                                                                       |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `User\settings.json` → `codingcopilot.customBlacklistCommands`                             | `[]`                                                                                                                                                                                                                                                              | 未配置自定义危险命令黑名单                                                                 |
| `User\settings.json` → `codingcopilot.disabledSecurityCategories`                          | 全部 13 类（2026-10-21 起，与 linux 侧一致）                                                                                                                                                                                                                       | 禁用的内置安全检查类别；**该键只是镜像**，权威值在 `state.vscdb`，以权威值为准             |
| `state.vscdb` → `CodeBuddy.settings` → `autoApprovalSettings`                              | `{"enabled": true, "actions": {"readFiles": true, "editFiles": true, "executeCommands": true, "useBrowser": true, "useMcp": true, "openWebViewInVSCode": true, "openMarkDownInVSCode": true}, "maxRequests": -1, "enableNotifications": false, "customBlacklistCommands": [], "disabledSecurityCategories": ["injection", "scriptExec", "powershell", "fileDelete", "gitOps", "permissions", "processControl", "network", "diskOps", "windowsSystem", "systemServices", "userManagement", "custom"]}` | 自动审批**已开启**、各类动作（读文件 / 改文件 / 执行命令 / 浏览器 / MCP）全放行；**13 类安全类别全部放开** ⇒ 命令、删除、git、权限、进程等不再逐条确认 |
| `state.vscdb` → `CodeBuddy.settings` → `chat.autoRunMode`                                  | `RunEverything`                                                                                                                                                                                                                                                   | 对话侧「运行所有内容」；`settings.json` 的 `autoRun` / `autoModifyFile` / `autoRunMode` 由它派生 |
| `User\settings.json` → `codingcopilot.autoRunMode` / `autoRun` / `autoModifyFile`           | `runEverything` / `true` / `true`（2026-10-21 按 linux 口径补写）                                                                                                                                                                                                  | 本版 `genie` 扩展（3.10.0）**未把这三项注册为 IDE 设置项**，实际生效取权威存储 `chat.autoRunMode`；settings.json 中仅为对照 |
| `User\settings.json` → `codingcopilot.safeDeleteEnabled` / `safeDeleteBulkThreshold`       | `safeDeleteEnabled` 未显式设置（默认 `true`）；`safeDeleteBulkThreshold` 为 **5000**（本机既有取值，2026-10-21 确认保留）                                                                                                                                         | 删除操作先移回收站、批量删除达阈值需确认（默认 500，本机放宽到 5000 以减少弹窗）           |

> 安全边界：`autoApprovalSettings.enabled = true`、动作全放行且**13 类安全类别全部放开**，等于允许 AI 不经确认读改文件、执行删除 / git / 权限 / 进程等命令。删除类仍有 `safeDeleteEnabled` 回收站与批量阈值兜底；放开期间建议临时文件放 `%TEMP%`、重要目录靠 git 兜底。收紧办法与生效验证见 [6.2](#permission-apply)、[6.3](#permission-verify)。

> 2026-10-21 已放开全部 13 类：`injection`、`scriptExec`、`powershell`、`fileDelete`、`gitOps`、`permissions`、`processControl`、`network`、`diskOps`、`windowsSystem`、`systemServices`、`userManagement`、`custom`（类别与命令对照见 linux 版「安全类别的真正存储与生效链路」节，两平台内置表一致）。

### 6.2 修改与生效 <a id="permission-apply"></a>

```powershell
# 查看当前权限相关设置（IDE 用户设置）
python3 -c "import json,os;d=json.load(open(os.path.join(os.environ['APPDATA'],'CodeBuddy CN','User','settings.json'),encoding='utf-8'));[print(k,'=',json.dumps(v,ensure_ascii=False)) for k,v in d.items() if k.startswith('codingcopilot.') and any(t in k for t in ['autoRun','autoModify','autoAccept','Security','Blacklist','safeDelete'])]"
```

- **改法**：安全类别改**权威存储**（`state.vscdb`），不要只改 `settings.json`——IDE 冷启动会用权威存储回写它。下面脚本一次完成「备份 → 改库 → 同步 settings.json」，**须先完全退出 CodeBuddy**（任务管理器确认无 `CodeBuddy CN` 进程）后在 PowerShell 执行：

```powershell
@'
import json, os, shutil, sqlite3, time

TARGET = ['injection', 'scriptExec', 'powershell', 'fileDelete', 'gitOps',
          'permissions', 'processControl', 'network', 'diskOps', 'windowsSystem',
          'systemServices', 'userManagement', 'custom']

user = os.path.join(os.environ['APPDATA'], 'CodeBuddy CN', 'User')
settings = os.path.join(user, 'settings.json')
db = os.path.join(user, 'globalStorage', 'state.vscdb')
stamp = time.strftime('%Y%m%d-%H%M%S')

shutil.copy2(settings, settings + '.bak-' + stamp)   # 备份 IDE 设置
shutil.copy2(db, db + '.bak-' + stamp)               # 备份权威存储

conn = sqlite3.connect(db)
data = json.loads(conn.execute("SELECT value FROM ItemTable WHERE key='CodeBuddy.settings'").fetchone()[0])
a = data['autoApprovalSettings']
a['enabled'] = True
a.setdefault('actions', {})
for action in ['readFiles', 'editFiles', 'executeCommands', 'useBrowser',
               'useMcp', 'openWebViewInVSCode', 'openMarkDownInVSCode']:
    a['actions'][action] = True
a['maxRequests'] = -1
a['disabledSecurityCategories'] = TARGET
data['chat']['autoRunMode'] = 'RunEverything'
conn.execute('UPDATE ItemTable SET value=? WHERE key=?',
             (json.dumps(data, ensure_ascii=False), 'CodeBuddy.settings'))
conn.commit()
conn.close()

cfg = json.load(open(settings, encoding='utf-8'))
cfg['codingcopilot.autoRun'] = True
cfg['codingcopilot.autoModifyFile'] = True
cfg['codingcopilot.autoRunMode'] = 'runEverything'
cfg['codingcopilot.autoAcceptWebSearch'] = True
cfg['codingcopilot.customBlacklistCommands'] = []
cfg['codingcopilot.disabledSecurityCategories'] = TARGET
json.dump(cfg, open(settings, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=4)
print('done:', TARGET)
'@ | python -
```

- **生效**：改完**冷启动**（重新运行 `CodeBuddy CN.exe`，不是「重新加载窗口」——重载不重读权威存储）。`autoAcceptWebSearch` 等普通设置仍可只改 `settings.json` 后重载窗口。
- **收紧**：把脚本里的 `TARGET` 换成需要保留的类别（如 `['injection', 'scriptExec', 'powershell']`），同样冷启动生效；只想回滚则把备份副本覆盖回去再冷启动。
- **还原**：备份形如 `User\settings.json.bak-YYYYmmdd-HHMMSS`、`User\globalStorage\state.vscdb.bak-YYYYmmdd-HHMMSS`，覆盖回原路径即可。

### 6.3 生效验证（Windows 取证） <a id="permission-verify"></a>

```powershell
# ① 确认真冷启动：进程启动时间与新的 IDE 日志目录
Get-Process 'CodeBuddy CN' | Sort-Object StartTime -Descending | Select-Object -First 1 Id,StartTime
Get-ChildItem "$env:APPDATA\CodeBuddy CN\logs" -Directory | Sort-Object Name -Descending | Select-Object -First 1

# ② 扩展同步日志：类别列表应为 13 项
$log = Get-ChildItem "$env:LOCALAPPDATA\CodeBuddyExtension\Logs\CodeBuddyIDE" -Recurse -File -Filter *.log |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
Select-String -Path $log -Pattern 'Synced disabledSecurityCategories|Synced autoRun'

# ③ 在对话里跑一条命令（如 echo cb-check）后，看加载条数与决策来源
Select-String -Path $log -Pattern '\[SecurityCheck\] Loaded|Permission decision' | Select-Object -Last 10
```

判断口径：`Synced disabledSecurityCategories to chat mode settings` 后列出 13 类、`[SecurityCheck] Loaded 13 disabled security categories` 即已加载；`Permission decision` 只剩 `auto_run_allow` / `default_allow` 表示免确认，出现 `safety_rule_ask` 说明该类仍被拦。2026-10-21 10:35:11 冷启动实测：`Received IDE settings` 与 `Synced disabledSecurityCategories` 均为 13 类，`Synced autoRun ... true`，末尾 `Successfully synced settings from IDE to plugin`。

## 7. 扩展管理与 HTML 文档预览 <a id="extensions"></a>

### 7.1 扩展目录与市场 <a id="ext-dirs"></a>

| 项           | 取值                                                                                                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 扩展宿主目录 | `~\.codebuddycn\extensions\`（**不是** `~\.vscode\extensions`——那是 VS Code 的目录，装到那儿 CodeBuddy 不加载）                                                                                                                       |
| 扩展登记文件 | `~\.codebuddycn\extensions\extensions.json`                                                                                                                                                                                              |
| 扩展市场     | **open-vsx.org**（与 linux 侧同）；只收录在 open-vsx 发布过的扩展                                                                                                                                                                        |
| 内置扩展     | `%LOCALAPPDATA%\Programs\CodeBuddy CN\resources\app\extensions\`（**101 个**，含 `simple-browser`、`html`、`html-language-features`、`markdown-language-features`、`media-preview`、`mermaid-chat-features`、`lexical-markdown-editor`、`genie`） |
| 已装扩展     | `ms-python.vscode-python-envs@1.20.1`（2026-10-16 快照，仅此一项）                                                                                                                                                                          |
| AI 侧插件    | `~\.codebuddy\settings.json` → `enabledPlugins`（见[第 5 节](#setup)）                                                                                                                                                                   |

> 工作区推荐扩展清单在 `bms/.vscode/extensions.json`（Volar、`ms-python.python` / `ms-python.debugpy` / `ms-python.vscode-pylance`、ESLint、Prettier、`bierner.markdown-mermaid`）——**Windows 侧目前基本未装**：后端断点依赖 `ms-python.debugpy`、md 文档 mermaid 预览依赖 `bierner.markdown-mermaid`，按需用 [7.2](#ext-install) 补装。

### 7.2 安装与卸载扩展（`buddycn` CLI） <a id="ext-install"></a>

CLI 已在用户 PATH，直接在终端使用（用法与 VS Code CLI 一致）：

```powershell
buddycn --list-extensions --show-versions               # 列出已装扩展
buddycn --install-extension <发布者.名称> --force         # 从 open-vsx 安装 / 更新
buddycn --uninstall-extension <发布者.名称>
buddycn --update-extensions                             # 更新全部已装扩展
```

实测注意事项：

- 扩展 ID 必须写成 **`发布者.名称`**；写错会直接报 `Extension 'xxx' not found.`；
- 安装过程**没有进度回显**，网络慢时长时间无输出属正常；判断结果以 `~\.codebuddycn\extensions\` 下是否出现 `发布者.名称-版本-<平台>` 目录为准；
- 安装完成后需「重新加载窗口」才会激活；
- 安装前可先确认市场可达：`curl.exe -I https://open-vsx.org/api/<发布者>/<名称>`（PowerShell 里 `curl` 是 `Invoke-WebRequest` 别名，**要用 `curl.exe`**）。

### 7.3 HTML 预览的三条路 <a id="html-preview"></a>

| 方式                                                  | 触发                                                                                                                                                                                                                       | 适用与限制                                                                                                                                                                                                       |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **内置 HTML 预览编辑器**（默认可用，零配置）     | 双击 html（需先设编辑器关联）；或命令面板 `codebuddyPreview.openPreview`（打开预览）、`codebuddyPreview.openHtmlSource`（打开源码）、`codebuddyPreview.toggleMode`（预览 ↔ 源码切换）                                     | CodeBuddy 内建扩展 `vscode.markdown-language-features`（v1.0.0，随应用发布）注册了 `codebuddy.html.previewEditor`（displayName **HTML Preview**，selector `*.html` / `*.htm`）与 `vscode.markdown.preview.editor`（Markdown Preview） |
| **Live Preview 扩展**（本机 Windows 侧未装）     | 装后：右键 html →**Show Preview**                                                                                                                                                                                    | 按文件所在目录起 http 服务，相对链接跳转与实时刷新更好；结束用 `Live Preview: Stop Server`（安装：`buddycn --install-extension ms-vscode.live-server --force`）                                                   |
| **Simple Browser**（内置命令）                     | `Ctrl+Shift+P` → `Simple Browser: Show` → 填 URL                                                                                                                                                                        | 内置浏览器面板，**只支持 http/https，`file://` 打不开**，需先有静态服务（见 [7.4](#bms-docs)）                                                                                                          |

双击行为由 `%APPDATA%\CodeBuddy CN\User\settings.json` 的编辑器关联决定（本机 Windows 侧当前未设置，双击 html 打开源码）；需要双击即预览时补上：

```json
"workbench.editorAssociations": {
  "*.html": "codebuddy.html.previewEditor",
  "*.htm": "codebuddy.html.previewEditor",
  "*.md": "vscode.markdown.preview.editor",
  "*.markdown": "vscode.markdown.preview.editor"
}
```

### 7.4 本仓库（bms 文档）预览 <a id="bms-docs"></a>

- `bms文档/**/*.html` 布局线框图 / 原型 / 组件原型资产引用同目录（或 `资源/`）的 `文档样式.css`、`mermaid.min.js`：用**内置预览**或 **Live Preview** 打开单个文件即可；
- 若预览出现「样式 / 脚本没加载、mermaid 不渲染」，改用 http 方式（起静态服务后用 Simple Browser 或外部浏览器打开），避免 `file://` 限制；
- md 正文里的 mermaid 需另装 **`bierner.markdown-mermaid`**（open-vsx 有收录）：`*.md` 已关联内置 Markdown 预览，装完扩展重载窗口后预览即渲染（本机 Windows 侧尚未安装）；
- 起静态文档服务（等价 Live Preview 的底座，可手动控制端口与生命周期）：

```powershell
cd D:\Develop\bizs\bms
python3 -m http.server 8765 --directory bms文档    # 访问 http://localhost:8765/
# 用完在终端按 Ctrl+C 结束（Windows 无 pkill）
```

### 7.5 扩展与预览排障 <a id="ext-trouble"></a>

| 现象                                      | 处理                                                                                                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 装扩展报 `Extension '…' not found.`     | ID 或市场问题：ID 必须 `发布者.名称`；用 `curl.exe -I https://open-vsx.org/api/<发布者>/<名称>` 确认 open-vsx 是否收录、网络是否可达                     |
| 装了扩展但不生效                          | 未重载窗口；或装错目录（应为 `~\.codebuddycn\extensions\`，不是 `~\.vscode\extensions`）                                                                |
| 安装命令长时间无回显                      | 属正常（无进度输出）；查 `~\.codebuddycn\extensions\` 是否出现新目录；长时间卡死则结束进程后重试                                                         |
| 双击 html 打开了源码                      | `workbench.editorAssociations` 未设或被改动；按 [7.3](#html-preview) 恢复 `*.html` / `*.htm` → `codebuddy.html.previewEditor`                        |
| 预览页无样式、mermaid 不渲染              | 走 http：Live Preview 或 [7.4](#bms-docs) 的静态服务，别用 `file://`                                                                                     |
| md 里 mermaid 是代码块                    | 未装 `bierner.markdown-mermaid`（或装后未重载窗口）                                                                                                     |

## 8. 运行与调试启动项 <a id="debug"></a>

IDE 的「运行和调试」下拉由 `.vscode/launch.json`（启动项）与 `.vscode/tasks.json`（任务 / 前置任务）驱动；两份配置均已入库（bms 仓 `.vscode/`，工作区根 `.vscode/` 为另一落点）。

### 8.1 位置口径（先看这条） <a id="debug-location"></a>

**VS Code 只读取「被打开的那个根」下的 `.vscode/`，不读取子目录的配置。** 故同一套启动项有两个落点，**改动须同步两处**（与工作区根 `settings.json` 的「双保险」同口径）：

| 落点                          | 生效场景                                                       | 路径写法                                      |
| ----------------------------- | -------------------------------------------------------------- | --------------------------------------------- |
| `D:\Develop\bizs\.vscode\`（**工作区根**） | 裸目录打开 `bizs`；或打开工作区文件 `bizs.code-workspace` 的「工作区（配置）」根 | 带 `bms/` 前缀；「当前文件」类用 `${file}` |
| `D:\Develop\bizs\bms\.vscode\` | 单独打开 `bms` 时                                              | 不带前缀；用 `${relativeFile}`               |

Windows 侧关键点：同一份 `launch.json` 用 **`windows` 平台覆盖**表达 Windows 取值（VS Code 按当前 OS 自动取值，linux 取值即顶层默认值）——Node 类走 `pnpm.cmd`、Chrome 调试走 `C:\Program Files\Google\Chrome\Application\chrome.exe`、后端解释器走 `backend\.venv\Scripts\python.exe`。改完需「重新加载窗口」才会刷新下拉。

> **注意（现状）**：**工作区根** `D:\Develop\bizs\.vscode\` 的 `launch.json` / `tasks.json` **当前仍是 linux 口径**（`bash` 调 `.sh`、无 `windows` 覆盖）——Windows 侧请在 `bizs.code-workspace` 里选 **「BMS 基座/平台」根**（或单独打开 `bms`）用 `bms\.vscode\` 这套双平台配置；裸目录打开 `bizs` 时调试 / 任务暂按 linux 口径，待工作区根同步后再启用。

> 后端 `.venv` 在本机为**指向依赖仓的 Junction**（`D:\dev-deps\bms\backend-venv`），`Scripts\python.exe` 实际解析到外部依赖仓（依赖外置 / 还原见《[uv 部署使用说明](uv部署使用说明.md)》《[pnpm 部署使用说明](pnpm部署使用说明.md)》；维护入口 `bms\scripts\tools\deps\` 的 `外置依赖` / `还原依赖` / `重装依赖`）。

### 8.2 启动项清单 <a id="debug-list"></a>

| 启动项                                            | 用途                                                                                    | Windows 侧关键取值                                                                                        | 前置任务                                |
| ------------------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| 前端：宿主 dev（Node · Vite）                     | 调试 Vite dev server 本体（`vite.config` / 插件），起好后自动用外部浏览器打开            | `pnpm.cmd dev`（`windows` 覆盖）                                                                          | —                                       |
| 前端：宿主 + Chromium（浏览器断点）               | 宿主页面 JS / Vue 源码断点                                                              | Chrome（`C:\Program Files\Google\Chrome\Application\chrome.exe`）、`http://localhost:5173/`               | `dev:宿主（5173）`                      |
| 前端：宿主 + 模块 + Chromium（浏览器断点）        | 含运行时模块的完整宿主（前置任务确保 5002 发布存储服务在跑）                            | 同上                                                                                                      | `dev:宿主 + 模块产物（5002 + 5173）`    |
| 前端：核对页 + Chromium（选页）                   | 开发态核对页实测（下拉选页，默认 `login-check.html`）                                   | 同上                                                                                                      | `dev:宿主（5173）`                      |
| 前端：当前文件单测（Node · Vitest）               | 打开某个 `tests/*.spec.ts` 后 F5 调试该文件                                             | `pnpm.cmd exec vitest run ${relativeFile}`                                                                | —                                       |
| 模块：demo / sample 独立开发（5002 / 5003 · Node） | 模块自身 `pnpm dev`（与宿主联调无关）                                                   | `pnpm.cmd dev`                                                                                            | —                                       |
| 后端：单服务（debugpy · 选服务）                  | 后端单服务断点（下拉选服务；读 `backend/config.toml` 的 `[server] host/port`）           | 解释器 `backend\.venv\Scripts\python.exe`（`windows` 覆盖）                                               | `dev:清理后端端口（8000）`              |
| 后端：单服务（debugpy · bms_identity）            | 固定默认服务的等价项（免每次手选）                                                      | 同上                                                                                                      | `dev:清理后端端口（8000）`              |
| 后端：当前文件单测（debugpy · pytest）            | 打开 `backend/**/tests/test_*.py` 后 F5                                                 | 同上                                                                                                      | —                                       |
| **后端：本地全套（三服务 · 脚本）**         | 脚本起 tenant / platform / identity 三服务（**后台进程，不带调试器**）            | `python3 scripts\tools\dev\本地全套.py up`                                                                | —                                       |
| **后端：单服务（debugpy · 本机三服务）**    | **后端断点**（下拉选服务）：经 `backend\ops\dev_run.py` 注入别名 / 8000 / 开发密钥 / Redis 后进服务入口 | 解释器同上；先 `本地全套.py stop <服务>` 腾位，调试完 `up` 补回（见 [8.4](#local-stack)）           | —                                       |
| 全套：后端单服务 + 宿主 + Chromium                | 旧口径组合项（后端固定 `bms_identity`）；**本机三服务形态下别用**                  | —                                                                                                        | —                                       |
| **全套（本地三服务 + 宿主 + Chromium）**    | **一键全套（推荐）**：脚本起三服务 + 宿主 + 模块产物 + Chrome（**前端断点即用**） | —                                                                                                        | —                                       |

> 浏览器断点项的 `runtimeExecutable` 必须写**可执行文件绝对路径**：Windows 侧为 `C:\Program Files\Google\Chrome\Application\chrome.exe`（本机 155.0.8059.85，已实测支持 `--user-data-dir` 与远程调试端口）；Chrome 换路径 / 换版本后请同步该值。选择项下拉：核对页 19 个页面（默认 `login-check.html`）、后端服务 8 个（默认 `bms_identity`）。

### 8.3 任务清单 <a id="debug-tasks"></a>

| 任务                                                          | 说明                                                                                                                                                                                                                     |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `dev:清理宿主端口（5173）`                                  | 普通任务：跑 `清理宿主端口.py` 清理占用 5173 的**本项目**旧宿主 dev（Windows 走 `netstat -ano` + 进程 PEB 判定 `cwd` 归属），供 dev 类后台任务作 `dependsOn` 前置                          |
| `dev:确保模块产物服务（5002）`                              | 普通任务：幂等确保 5002 发布存储服务在跑（缺则后台拉起），供「宿主 + 模块」作 `dependsOn` 前置                                                                                                                          |
| `dev:宿主（5173）` / `dev:宿主 + 模块产物（5002 + 5173）` | 后台任务：命令只有 `pnpm dev`，准备动作全交 `dependsOn` 前置任务（`dependsOrder: sequence`）；以 Vite 的 `Local:` 行为就绪信号                                                                                     |
| `dev:清理后端端口（8000）`                                  | 普通任务：清理占用 8000 的本项目旧后端调试进程，供后端启动项作 `preLaunchTask`；**注意它按端口清理，会把本地全套的三服务一起清掉**——起三服务请用下面两条任务   |
| `dev:后端本地全套（三服务）`                                | 普通任务：调 `python3 scripts\tools\dev\本地全套.py up`——幂等起 tenant / platform / identity + 自愈 hosts 别名与开发密钥 + 等健康                                                                                         |
| `dev:后端本地全套·停（三服务）`                             | 普通任务：`本地全套.py down`——TERM → 5s → KILL，仍不死**报错交人工**；单个服务用 `本地全套.py stop <服务>`                                                                                                     |
| `服务:模块产物（5002 · CORS 静态）`                        | `serve-module-releases.mjs` 托管 `frontend/releases/**`（带 CORS，宿主加载运行时模块的前置）                                                                                                                       |
| `发布:模块产物（demo + sample · 构建 + 发布）`              | 构建并发布两个运行时模块到 `frontend/releases/`（归档不入库）                                                                                                                                                        |
| `dev:模块 demo / sample 独立开发`                           | 模块自身 dev（demo 5002 / sample 5003，与「服务:模块产物」的 5002 互斥）                                                                                                                                                 |
| 检查：前端基座三包 / 前端宿主 / 文档基座 / 后端               | 一键跑对应门禁（lint、typecheck、用例、体积预算、文档校验、ruff + pyright）                                                                                                                                              |

> 任务统一用 shell + 显式 `python3` / `pnpm` / `node`：dev 工具脚本为「**Python 单一实现 + 薄包装**」——逻辑在 `scripts\tools\dev\*.py`，同名 `.sh`（Linux）与 `.bat`（Windows）只是转调包装（`.bat` 内部先 `chcp 65001` 再 `python <同名>.py`），IDE 任务与终端一律 `python3 xxx.py`，双平台同口径。**Windows 侧后端门禁**：本机已装 `uv`（**0.12.7**，`…\Python314\Scripts\uv.exe` 已入用户 PATH，索引走 TUNA，见《[uv 部署使用说明](uv部署使用说明.md)》）⇒ `uv run …` 类命令可用；亦可直接用 `backend\.venv\Scripts\python.exe` 直跑。

### 8.4 本机裸跑后端「全套」（本地开发主形态） <a id="local-stack"></a>

**口径**：开发态**一律本机裸跑**——`backend/config.dev.toml` 本就是 SQLite 本地库 + 内存缓存 + 字典 / 参数走 SQL，**不需要 Docker，也不需要在开发服务器上部署**；容器 / 开发服务器**只在发布时**用于发布验证。三个服务各绑一个 loopback 别名并**共用 8000 端口**，与服务间基址模板 `http://{service}:8000` 同形（故服务间调用、网关内路径与容器形态一致；`org` 已随组织主数据归 mdm 产品服务，不再纳管）。

| 项       | 取值 / 做法                                                                                                                        |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 脚本     | `bms\scripts\tools\dev\本地全套.py`（子命令 `up` / `down` / `stop <服务…>` / `status` / `seed` / `env` / `logs` / `unlock [账号]`） |
| 别名     | `127.0.0.2 tenant`、`127.0.0.4 platform`、`127.0.0.5 identity`（`up` 自愈写入 hosts；**Windows 写 hosts 需管理员权限**，失败时脚本提示手工追加） |
| 开发密钥 | `bms\backend\.dev-keys.local`（`up` 缺则用 `joserfc` 生成：`usr-` 用户令牌 + `svc-` 服务令牌；不入库）                        |
| Redis    | 缺省指开发服务器上的隔离库（DB5；地址以脚本缺省与《[本地资源](../../../用户文档/本地资源.md)》为准，`--redis` 或 `BMS_LOCAL_REDIS` 覆盖） |
| 状态目录 | `%TEMP%\bms-local-stack`（pid 与日志；linux 侧为 `/tmp/bms-local-stack`）                                                          |
| 前端映射 | `bms\frontend\apps\desktop\.env.local` 的 `VITE_LOCAL_API`（**`up` 收尾自动写入**，`env` 子命令可单独补；未列出的服务仍走远端网关） |
| 账号     | `seed` 建号（缺省账号 `admin`，口令随机生成并仅打印一次）——**首次起栈后必须跑一次 `seed`**，否则本地库无账号、登录恒 401；账号 / 口令**只登记在《本地资源》** |
| 库重建   | `本地全套.py up --reset-db`（先把 `database\bms\bms_*.db` 备份移走，服务按当前表结构重建；**重建后须重新 `seed`**）      |

常用流程（PowerShell）：

```powershell
cd D:\Develop\bizs\bms
python3 scripts\tools\dev\本地全套.py up              # 起三服务（幂等：已在跑则跳过；等健康；收尾自动补 .env.local 的 VITE_LOCAL_API）
python3 scripts\tools\dev\本地全套.py seed            # 租户注册库 + 菜单元数据 + 建号 admin（幂等）
python3 scripts\tools\dev\本地全套.py status          # 进程与 /healthz、/readyz 一览
python3 scripts\tools\dev\本地全套.py stop identity   # 只停一个（供后端断点腾位）
python3 scripts\tools\dev\本地全套.py unlock          # 解锁账号（清失败计数 / 锁定时间 + Redis 计数键）
python3 scripts\tools\dev\本地全套.py down            # 停全部：TERM → 5s → KILL；仍不死则报错交人工
```

> 也可在资源管理器 / 任务计划里直接跑等价 `.bat` 入口（`scripts\tools\dev\本地全套.bat` 等）。**本机 Windows 侧尚未实跑过本地全套**（2026-10-16 核实：hosts 无别名、8000 未监听），首次运行前请以管理员身份开终端（供 hosts 写入），其余流程与 linux 侧一致。

**断点口径**（脚本起的服务是分离后台进程，**不带调试器**）：

| 目标               | 做法                                                                                                                                                                                                                                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 前端（Vue / TS）   | 用「全套（本地三服务 + 宿主 + Chromium）」里的 Chrome 调试会话，或单项「前端：宿主 + 模块 + Chromium（浏览器断点）」——**断点直接可用**                                                                                                                                                                                       |
| 后端（Python）     | ① `本地全套.py stop <服务>` 腾出该服务；② 启动「后端：单服务（debugpy · 本机三服务）」——`backend\ops\dev_run.py` 在**导入服务前**注入 `BMS_SERVER__HOST=<别名>` / `PORT=8000` / `BMS_REDIS__URL` 与开发密钥，再 `runpy` 进服务入口 ⇒ 断点 / 变量 / 调用栈与 `python -m bms_<服务>` 一致（`justMyCode: false` 可步入框架与基座）；③ 调试完 `本地全套.py up` 补回 |
| 旧「全套：后端单服务 + 宿主 + Chromium」 | **本机三服务形态下别用**：它只起 `bms_identity` 一个、不加载密钥与别名，且前置任务 `清理后端端口（8000）` 会把三服务**全部清掉**                                                                                                                                                                                       |

### 8.5 调试排障 <a id="debug-trouble"></a>

| 现象                                                            | 处理                                                                                                                                                                                                                                                                                    |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 调试下拉为空 / 任务跑成 linux 命令                              | 打开的是错误的根，或用的仍是 linux 口径的工作区根配置（见 [8.1](#debug-location)）；或改配置后未「重新加载窗口」；或该 json 有语法错误（打开文件看波浪线，注释为 JSONC 允许）                                                                                                                                               |
| 启动即报找不到任务                                              | `preLaunchTask` 名与 `tasks.json` 的 `label` 不一致（两处文件须同步，见 [8.1](#debug-location)）                                                                                                                                                                                     |
| 浏览器断点不生效                                                | `runtimeExecutable` 须是本机存在的可执行文件绝对路径（本机为 `C:\Program Files\Google\Chrome\Application\chrome.exe`）；确认 Chrome 已装且路径与版本一致                                                                                                                              |
| 后端启动项报错                                                  | 需扩展 `ms-python.debugpy`（**本机 Windows 侧尚未安装**，见 [7.2](#ext-install)）；解释器 `bms\backend\.venv\Scripts\python.exe` 须存在（`.venv` 为依赖仓 Junction）                                                                                                        |
| 后端 `.py` 满屏「无法解析导入 sqlalchemy」                      | 分析器没关联到项目解释器：`.vscode\settings.json` 的 `python.defaultInterpreterPath`（settings.json 无平台分支）当前是 linux 路径口径；Windows 侧在 IDE 内用「Python: Select Interpreter」选 `backend\.venv\Scripts\python.exe`（或写本机用户级设置），并确认已装 Python 扩展 |
| 宿主页面显示「模块加载失败」                                    | 5002 上未托管发布归档：先跑「发布:模块产物」再跑「服务:模块产物（5002 · CORS 静态）」（裸静态服务缺 CORS 头会致跨源 ESM 加载失败）                                                                                                                                                    |
| 点「全套」弹「正在等待 preLaunchTask」，但服务其实已经起来      | background 就绪正则没匹配上：vite 在终端里输出的是带 ANSI 颜色码的 `Local` + `ESC[22m` + `:`，字面 `Local:` 并不存在 → `endsPattern` 必须写成 `Local.*https?://`（两处 `tasks.json` 的 vite 任务已如此）                                                                         |
| 启动即报端口被占（5173 / 8000）                                 | 上一次遗留的 dev / 调试进程未退出：5173 由前置任务 `dev:清理宿主端口（5173）` 自愈、8000 由 `dev:清理后端端口（8000）` 自愈；**占用者为非本项目进程时任务会中止并提示**（不误杀）                                                                                                  |
| 点「全套」弹「任务尚未退出，并且未定义 problemMatcher」         | 该 background 任务的 `command` 里混了准备动作，耗时超出就绪等待窗口：点「仍要调试」可继续；根治是把准备动作拆成 `dependsOn` 前置任务（本机两处 `tasks.json` 已如此）                                                                                                              |
| 本地全套写 hosts 失败                                           | Windows 写 `C:\Windows\System32\drivers\etc\hosts` **需管理员权限**：以管理员身份重跑，或按脚本提示手工追加三个别名行                                                                                                                                                                  |
| 本地登录**恒 401**，但三服务 `/healthz`、`/readyz` 都 200  | 本地库里**没有可用账号**（多为 `--reset-db` 重建后未建号）：跑 `python3 scripts\tools\dev\本地全套.py seed`（租户 + 菜单 + 建号 `admin`），或 `seed` 加 `--username/--password`                                                                                                     |
| 登录报 **502**（`Request failed with status code 502`）          | 前端 `/api` 未就近代理，回落到了 `VITE_API_PROXY`（缺省 `http://localhost:8088`，本机通常无此网关）：确认 `frontend\apps\desktop\.env.local` 有 `VITE_LOCAL_API=tenant=127.0.0.2,platform=127.0.0.4,identity=127.0.0.5`——跑一次 `本地全套.py up`（收尾自动补）或 `本地全套.py env`；**`.env.local` 新增后须让 vite 重载配置**（重启「前端：宿主 dev」任务，或改动任意 config 触发 vite 重启） |
| 登录后**刷新 / 深链直开**动态菜单页落 404（如 `/sys/users`、`/sys/roles`） | 路由守卫的动态路由重解析判定曾用 `router.hasRoute(path)`（该 API 参数是路由 **name**，通用页面路由 `name: 'SystemUser'` ≠ `path: '/sys/users'` 时恒假）→ 刷新不重解析、落兜底 404。**2026-10-18 已修**（改按 `router.resolve(path)` 命中的路由记录标识前后对比）；若仍复现，确认宿主代码已更新且 vite 已热更（必要时重启 dev 任务） |
| 登录报 `20002`「账号或密码错误」 / `20003`「账号已锁定」        | 口令以《[本地资源](../../../用户文档/本地资源.md)》「BMS 应用账号」节的当前登记为准（历史对话 / 旧文档里的口令一律失效；注意浏览器自动填充旧口令）；连续 5 次失败锁 15 分钟，解锁跑 `本地全套.py unlock`，**验验证码请用不存在的账号试错口令**                                 |

## 9. 浏览器真机验证：Playwright MCP <a id="browser-mcp"></a>

开发态**真实浏览器核验**在 Windows 侧有两条链路，都能导航 / 点击 / 填表 / 截图 / 读控制台：**Playwright MCP**（`mcp__playwright__*`，本节登记）与 **`playwright-cli` 技能插件**（`enabledPlugins` 已启用；CLI 侧口径与选型见 linux 版同名文档）。

**登记**（用户级 `~\.codebuddy\mcp.json`，2026-10-16 原文）：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@0.0.83", "--browser", "chrome", "--isolated"],
      "env": { "npm_config_registry": "https://registry.npmmirror.com" }
    }
  }
}
```

| 参数                          | 作用                                                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| `@playwright/mcp@<版本>`      | 走 `npx` 拉取（`env` 指 npmmirror 国内镜像；本机 `~\.npmrc` 全局源也是 npmmirror）；其内置 playwright-core 决定内核支持 |
| `--browser chrome`            | 复用**系统 Google Chrome**（`C:\Program Files\Google\Chrome\Application\chrome.exe`），免下载 Chromium（本机无 `~\.cache\ms-playwright`） |
| `--isolated`                  | 隔离会话（不写用户 profile，每次全新上下文）                                                          |

> 生效：MCP 工具的可见列表是**会话启动快照**——登记或改配置后须**重启 IDE**（或刷新 MCP 面板）方可调用；面板内该 server 显示 running 即已拉起（浏览器**惰性启动**，首次调用工具才开窗口）。工作区级 MCP 另可放 `<工作区根>\.mcp.json`（本轮无需）。

**真机走查模板**（以本地全套 + 宿主 dev 为例）：

```powershell
cd D:\Develop\bizs\bms
python3 scripts\tools\dev\本地全套.py up                                            # 起本地三服务（见 8.4）
python3 scripts\tools\dev\本地全套.py seed --username admin --password '<口令>' --reset-password
cd frontend
pnpm --filter @bms/desktop dev                                                      # 起宿主 dev（:5173）
```

随后用 MCP 工具逐步走查：`browser_navigate` 打开 `/login` → `browser_fill_form` 填账号口令 → `browser_click` 提交 → `browser_snapshot` 读结构 / `browser_take_screenshot` 取证。常用工具：`browser_navigate` / `browser_click` / `browser_type` / `browser_fill_form` / `browser_snapshot` / `browser_find` / `browser_console_messages` / `browser_take_screenshot` / `browser_wait_for`。

口径与注意：

- **读页面结构用 `browser_snapshot` / `browser_find`**，二者把 a11y 树**内联返回**（含 `[ref=eNN]`），可直接据此 click / fill；**不要**指望 `.playwright-mcp\page-*.yml`——`browser_navigate` 触发的该文件恒 **0 字节**（与 `playwright-cli snapshot` 同源缺陷），`browser_click` 触发的才有内容；ref 前缀会随导航变化（如首次 `e..`、后续 `f1e..`）。
- **截图落盘**：`browser_take_screenshot` 的 `filename` 相对**工作区根**解析（本机 `D:\Develop\bizs\tmp\…`）；截图以**文件**落盘、工具只回路径，**不占模型图片额度**。
- **控制台**：`browser_console_messages --level error --all`；本地开发态允许的预期错误仅 `favicon.ico` 404、模块宿主（:5002）`remoteEntry.js` `ERR_CONNECTION_REFUSED`、未登录态 `auth/refresh` 401，其余均按缺陷看。
- **首次调用**：`npx` 需拉取 `@playwright/mcp`（本机首次约需下载，registry 已指 npmmirror），耐心等待；之后走本地缓存。

**与 `playwright-cli` 的选型（长会话口径，与 linux 侧同一结论）**：MCP 每步 1 次调用、CLI 每步 2~4 次子进程调用，且对话每轮整体重发历史上下文 ⇒ **长会话首选 MCP**（又快又省）；`playwright-cli` 仅在 1~2 步的极短会话或只看单次输出时可能更省。长会话内用 `browser_find`（只回命中片段）替代整页 `browser_snapshot` 可进一步省量。

## 10. 常用设置与排障 <a id="trouble"></a>

### 10.1 常用设置 <a id="settings"></a>

| 设置项                                                    | 说明                                                                                                     |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `codingcopilot.submitMessageShortcut`                   | 发送快捷键：本机 `Ctrl/Cmd + Enter`（发送）                                                              |
| `codingcopilot.enableAutoCompletions`                   | 自动触发代码补全（本机开）；关闭后可用快捷键手动触发                                                     |
| `codingcopilot.enableInlineChat` / `toolbarOnSelection` | 内联聊天与选中悬浮工具栏（本机 `true` / `false`）                                                        |
| `codingcopilot.enableCraftCodeBase`                     | Craft 模式启用代码库检索（本机开）                                                                       |
| `codingcopilot.enableNextEditSuggestions`               | 下一处编辑预测（本机关）                                                                                 |
| `codingcopilot.enabledWebSearch` / `autoAcceptWebSearch` | 联网搜索总开关 / 自动接受搜索结果（本机均开）                                                            |
| `codingcopilot.commitMessageStyle` / `commitMessageLanguage` | 提交信息风格 / 语言（本机 `Auto` / `zh_CN`）                                                      |
| `codingcopilot.HttpProxyMode` / `codingcopilot.HTTPProxy` | 网络代理：`system`（跟随系统）/ `manual`（手动，仅手动模式读 `HTTPProxy`）                           |
| `codingcopilot.disableBuiltInMarketplace`               | 无法访问内置插件市场时开启，**跳过市场安装与定期更新检查**，避免对话请求被反复的市场拉取超时阻塞          |
| `codingcopilot.autoUpdateThirdPartyMarketplaces`        | 每天检查一次第三方插件市场并后台静默更新（默认关）                                                       |
| `codingcopilot.enableModelOptimization`                 | 允许使用对话数据做模型优化（默认关，按需开启）                                                           |

### 10.2 排障入口 <a id="trouble-entry"></a>

| 现象                                                       | 处理                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 对话卡住 / 反复超时（市场拉取阻塞）                        | 开启 `codingcopilot.disableBuiltInMarketplace` 后重载窗口                                                                                                                                                                                                     |
| 界面白屏 / 花屏等渲染异常                                  | 在 `~\.codebuddycn\argv.json` 打开 `"disable-hardware-acceleration": true`，重启 IDE（本机当前未启用）                                                                                                                                                     |
| 命令被拦截或反复确认                                       | 检查 `codingcopilot.customBlacklistCommands`（命中正则会拦截）与安全类别设置（见[第 6 节](#permission)）                                                                                                                                                    |
| 改了 `disabledSecurityCategories` 仍在弹确认               | 权威存储在 `state.vscdb` → `CodeBuddy.settings.autoApprovalSettings`，需完全退出后改并**冷启动**；Windows 改法与取证见 [6.2](#permission-apply)、[6.3](#permission-verify)，失效链路见 linux 版「免确认失效的排查」节 |
| 删除的文件想找回                                           | `safeDelete` 默认开启时删除先进回收站；关闭后为永久删除                                                                                                                                                                                                       |
| 需要看运行日志                                             | 对话 / 扩展日志 `%LOCALAPPDATA%\CodeBuddyExtension\Logs\CodeBuddyIDE\<日期>\<工作区>__<hash>.log`；IDE 日志 `%APPDATA%\CodeBuddy CN\logs\<时间戳>\`                                                                                                     |
| 崩溃排查                                                   | `%APPDATA%\CodeBuddy CN\CrashReport\`（崩溃转储）                                                                                                                                                                                                            |
| 终端里 `python3` 报「Python was not found…Microsoft Store」 | 命中了 `WindowsApps` 里的**商店占位别名**：该终端继承的是旧环境变量（新装 Python 的 PATH 未生效）⇒ **重开终端**（必要时重启 IDE）；改用 `python` 或显式 `backend\.venv\Scripts\python.exe` 亦可                                                   |
| 终端里 `buddycn` 找不到                                     | CLI 包装脚本目录（`%LOCALAPPDATA%\Programs\CodeBuddy CN\bin`）已在用户 PATH，但**旧终端**未加载 ⇒ 重开终端；或用全路径 `& "$env:LOCALAPPDATA\Programs\CodeBuddy CN\bin\buddycn.cmd" --version`                                                                  |
| 终端中文乱码 / Python 打印非 GBK 字符报 `UnicodeEncodeError: 'gbk' codec can't encode…` | Windows 控制台默认 GBK 代码页：先 `chcp 65001`，并设 `$env:PYTHONIOENCODING='utf-8'`（项目 `.bat` 包装已内置 `chcp 65001`；本机 2026-10-16 实测该报错即此因）                                                                                        |
| 多开窗口互相干扰                                           | 排障时同一用户数据目录（`%APPDATA%\CodeBuddy CN`）下**只保留一个窗口**：多窗口共用扩展宿主与 MCP 会话，MCP 面板 / 任务可能相互干扰（CLI 默认复用已有窗口，`-n` 才新开）                                                                                        |
| Playwright MCP 调不到工具（无 `mcp__playwright__*`）     | 工具列表是**会话启动快照**：登记或改配置后需**重启 IDE**或刷新 MCP 面板；面板内该 server 为 running 即已拉起（见[第 9 节](#browser-mcp)）；日志线索在 `%LOCALAPPDATA%\CodeBuddyExtension\Logs\…`                                                |
| MCP / CLI `snapshot` 落盘 `.playwright-*` 文件恒 0 字节   | 二者同源缺陷：取结构改用 **`browser_snapshot` / `browser_find`**（a11y 树内联返回，含 `[ref=eNN]`），或 CLI 侧 `eval` 读 DOM（见[第 9 节](#browser-mcp)）                                                                                              |

## 11. 与 linux 版差异 <a id="diff-linux"></a>

同机双系统（mjpc），Ubuntu 侧与本侧共用同一套 bms 仓库与 `.vscode/` 配置；差异集中在平台取值与就绪度：

| 维度         | linux 侧（Ubuntu）                                                              | windows 侧（本文，Windows 11）                                                                     |
| ------------ | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 安装来源     | 官网 `.deb` 手工安装（无 apt 源），包 `codebuddy-cn` 4.12.0                     | 官网**用户级安装器**（无包管理器），安装器 4.12.2，安装目录 `%LOCALAPPDATA%\Programs\CodeBuddy CN` |
| 应用版本     | 1.106.1                                                                         | 1.106.1（构建 2026-10-13）                                                                         |
| CLI          | `/usr/share/buddycn/bin/buddycn`（**未入 PATH**）                            | **`buddycn` / `buddycn.cmd`**（包装脚本，**已入用户 PATH**）                                   |
| 用户数据目录 | `~/.config/CodeBuddy CN`、`~/.codebuddycn`、`~/.codebuddy`、`~/.local/share/CodeBuddyExtension` | `%APPDATA%\CodeBuddy CN`、`~\.codebuddycn`、`~\.codebuddy`、`%LOCALAPPDATA%\CodeBuddyExtension` |
| 权限现状     | `autoRunMode=runEverything`，**全 13 类安全类别已放开**                       | 同上：`RunEverything` + **全 13 类已放开**（2026-10-21 对齐，权威存储 `state.vscdb`）            |
| 扩展现状     | 官方 Python 三件 + ESLint / Prettier / Live Preview / markdown-mermaid 等       | 仅 `ms-python.vscode-python-envs`（后端断点、md mermaid 等待补装）                                 |
| 编辑器关联   | 已设（双击 html / md 即预览）                                                   | 未设（双击开源码，按 [7.3](#html-preview) 补）                                                  |
| 浏览器       | 系统 Chrome（`/usr/bin/google-chrome`）                                        | 系统 Chrome（`C:\Program Files\Google\Chrome\Application\chrome.exe`，155.0.8059.85）              |
| 扩展 / 脚本  | bash + `.sh`（`nohup` / `/tmp`）                                              | PowerShell 7 / Windows Terminal + `.bat` 薄包装（`chcp 65001`）；任务与终端统一 `python3 xxx.py`    |
| 任务与调试   | `launch.json` 顶层 Linux 默认值（`pnpm`、`bin/python`、Linux Chrome 路径）     | 同一份文件按 **`windows` 平台覆盖**取值（`pnpm.cmd`、`Scripts\python.exe`、Program Files 下 Chrome） |
| uv 工具链    | 已就绪（`uv run …` 门禁可用）                                                  | **0.12.7**（`Python314\Scripts\uv.exe`，已入用户 PATH；索引 TUNA）                                |
| 本地全套     | 四服务口径为历史值，现行为三服务（tenant / platform / identity）                | 三服务；hosts 写入需管理员权限，状态目录 `%TEMP%\bms-local-stack`                                  |
| 工作区级 `.codebuddy/` | 已生成（工作记忆三件套）                                                | 尚未生成（工作记忆 / 一条龙 / AI 交叉评审口径见 linux 版同名文档对应章节）                         |

## 12. 检查清单 <a id="checklist"></a>

- □ 版本已核实：安装器 4.12.2（`CodeBuddy CN.exe` ProductVersion）与应用 1.106.1（`buddycn --version` / `product.json`）分别取自两处
- □ 安装形态明确：用户级安装器（`%LOCALAPPDATA%\Programs\CodeBuddy CN`），无包管理器；卸载用 `unins000.exe`，用户数据独立存放
- □ 四个用户数据目录职责清晰（IDE 设置 / 扩展宿主 / AI 配置 / 日志），清理只动缓存目录
- □ 权限设置口径明确：IDE 设置 `%APPDATA%\CodeBuddy CN\User\settings.json`（`codingcopilot.*`），安全类别权威存储在 `state.vscdb`；本机「自动审批开、13 类安全类别全部放开」（2026-10-21，冷启动取证见 [6.3](#permission-verify)）
- □ 首配项齐备：语言 `zh-cn`、崩溃上报关闭、插件与技能市场、MCP 登记位、补全模型与提交信息风格
- □ 扩展管理口径明确：扩展目录 `~\.codebuddycn\extensions`、市场 open-vsx、安装用 `buddycn --install-extension`（与 `~\.vscode\extensions` 区分开）
- □ 文档预览口径明确：html 走内置 HTML 预览（`codebuddy.html.previewEditor`，双击需先设编辑器关联）、`file://` 受限改走 http 静态服务；md mermaid 需 `bierner.markdown-mermaid`
- □ 运行与调试链路口径明确：两处 `.vscode/` 落点同步维护、`windows` 平台覆盖（`pnpm.cmd` / Program Files 下 Chrome / `Scripts\python.exe`）；dev 类后台任务经 `dependsOn` 前置自愈 5173 与确保 5002；准备动作不写进 background 任务的 `command`；就绪正则容忍 ANSI（`Local.*https?://`）
- □ 本地全套口径明确：`本地全套.py`（三服务 + loopback 别名 + 开发密钥），hosts 需管理员权限、`seed` 必跑（否则恒 401）
- □ 浏览器真机验证口径明确：Playwright MCP 登记于 `~\.codebuddy\mcp.json`（系统 Chrome + `--isolated`）、生效需重启 IDE；结构读 `browser_snapshot` / `browser_find`（`.playwright-mcp\*.yml` 不可依赖）、截图落工作区 `tmp\`、控制台只认预期错误；长会话首选 MCP
- □ 排障入口齐备：日志三处（扩展 / IDE / 崩溃转储）、`python3` 商店别名、中文编码（GBK）、CLI 未入旧终端 PATH、多开窗口
- □ 本机事实均经核实（2026-10-15 安装实测；2026-10-16 复核版本 / 目录 / 扩展 / 权限存储 / uv 工具链 / MCP 登记 / `.vscode` 双平台取值；2026-10-21 权限与免确认设置改为全 13 类放开并冷启动取证），未写入账号 / 令牌等凭据

## 13. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc Windows 侧开发设施汇总（CodeBuddy 在其中的定位与取值）
- 《[CodeBuddy 部署使用说明](../linux/CodeBuddy部署使用说明.md)》：linux 侧同名文档（权限存储链路、工作区 `.codebuddy/` 与 AI 协作口径）
- 《[VSCode部署使用说明](VSCode部署使用说明.md)》：同机 VS Code 侧（工作区多根、调试与扩展口径对照）
- 《[google-chrome部署使用说明](google-chrome部署使用说明.md)》：浏览器断点与 Playwright 真机验证复用的系统 Chrome
- 《[playwright部署使用说明](playwright部署使用说明.md)》：真机验证兜底（`playwright-cli` 技能插件）的命令与选型
- 《[pnpm 部署使用说明](pnpm部署使用说明.md)》《[uv 部署使用说明](uv部署使用说明.md)》：Node / Python 工具链与依赖外置（IDE 任务、调试解释器与后端门禁的前提）
- 《[git部署使用说明](git部署使用说明.md)》：版本控制、Git Bash 与远端凭据
- 《[opencode部署使用说明](opencode部署使用说明.md)》：本机另一 AI 编码工具（与 CodeBuddy 互不干扰）
- 《[本地资源](../../../用户文档/本地资源.md)》：机器、账号与口令取值（已 gitignore，不入库）
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》《[CodeBuddy 部署使用说明](../linux/CodeBuddy部署使用说明.md)》（linux 侧）配套 · 记录 2026-10-15 安装与首次配置、2026-10-16 事实核实（版本 / 用户数据目录 / 扩展清单 / 权限存储 / uv 工具链 / `.vscode` 任务与启动项双平台取值 / Playwright MCP 登记）、2026-10-21 权限与免确认设置（全 13 类放开 + 冷启动取证）
