# CodeBuddy 部署使用说明

> mjpc 开发机 CodeBuddy（腾讯云代码助手 IDE，codebuddy-cn 4.12.0 / 应用 1.106.1）部署、配置、扩展管理、文档预览、权限与排障实录 · 2026-09-12

[文档首页](../../文档首页.md) › 资料 › 开发机 › CodeBuddy 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[opencode部署使用说明 →](opencode部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS，GNOME，Wayland，NVIDIA RTX 4090）上 **CodeBuddy** 的部署与使用：安装来源与版本、四个用户数据目录的作用、首次配置项（登录/语言/插件/技能/MCP）、**权限与免确认设置**（自动运行命令、文件自动修改、安全检查类别、黑名单、安全删除）、**扩展管理（扩展目录 / open-vsx 市场 / 应用自带 CLI）与 HTML 文档预览**（内置 HTML 预览、Live Preview、Simple Browser；bms 文档资产与 md mermaid 的预览办法）、常用设置与排障入口。

本文档与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》「开发设施清单」节与「桌面快捷方式设置（通用）」节配套；CodeBuddy 与 [opencode](opencode部署使用说明.md)、[deepseek-harness](../AI/deepseek_harness部署使用说明.md) 同属本机 AI 编码工具，三者互不干扰、各自独立部署。

> **取值说明**：本机路径统一用 `~` 表示（开发机开发用户为 `minjian`）；账号、令牌等凭据不在本文记录，以本机登录态与《[本地资源](../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 环境概览 <a id="env"></a>

| 项 | 取值 |
| --- | --- |
| 系统 / 桌面 | Ubuntu 26.04.1 LTS（x86_64）；GNOME（`XDG_SESSION_TYPE=wayland`） |
| 应用名称 | CodeBuddy CN（`applicationName = buddycn`，`urlProtocol = codebuddycn`） |
| 应用版本 | **1.106.1**（stable；commit `b4c35ed0`，构建日期 2026-09-04） |
| deb 包 | `codebuddy-cn` **4.12.0**（amd64；Maintainer `CodeBuddy Team <codebuddy@tencent.com>`，Homepage `https://www.codebuddy.ai`） |
| 同源桌面包 | `workbuddy` 5.5.6（腾讯 WorkBuddy，与 CodeBuddy 同一官网分发） |
| 安装形态 | **手工 `.deb` 安装，无 apt 源**（`/etc/apt/sources.list*` 中无相关仓库）→ **不随 `apt upgrade` 升级**，需下载新包覆盖安装 |
| 应用目录 | `/usr/share/buddycn/`（二进制 `/usr/share/buddycn/bin/buddycn`） |
| 启动器 | `/usr/share/applications/buddycn.desktop` → `Exec=/usr/share/buddycn/bin/buddycn %F`（另有 `buddycn-url-handler.desktop` 处理 `codebuddycn://` 链接） |
| 服务端组件名 | `codebuddy-server-cn`（远程/SSH 场景使用，本机未部署） |
| CLI | PATH 中**无** `codebuddy` / `cbc`；但应用自带桌面 CLI **`/usr/share/buddycn/bin/buddycn`**（VS Code 同款，支持 `--install-extension` / `--list-extensions` 等，扩展管理即用它，见第 7 节）；如需独立 CLI 另按其官方文档部署 |
| Electron 版本 | 37.7.0（由进程启动参数核实） |

> 本机 **无 GPU/Wayland 崩溃**：CodeBuddy 日志中未见 GPU 进程段错误（与 [opencode](opencode部署使用说明.md) 在本机 NVIDIA + Wayland 下的 GPU 崩溃不是一类问题），因此**无需** `--disable-gpu`；若日后出现渲染异常，排障方式见[第 8 节](#trouble)。

## 3. 安装与升级 <a id="install"></a>

### 3.1 安装形态 <a id="install-form"></a>

CodeBuddy 通过官方 `.deb` 安装（dpkg 侧包名 `codebuddy-cn`），**未登记 apt 源**，因此：

- `apt upgrade` **不会**更新 CodeBuddy，升级需人工下载新 `.deb`（见 3.2）；
- 查询已装版本：`dpkg -l codebuddy-cn`（包版本）与 `/usr/share/buddycn/resources/app/product.json` 里的 `version`（应用版本，两者编号体系不同，如包 4.12.0 ↔ 应用 1.106.1）；
- 卸载：`sudo dpkg -r codebuddy-cn`（**不会**删除 `~/.config/CodeBuddy CN`、`~/.codebuddy`、`~/.codebuddycn` 等用户数据，重装后登录态与配置仍在）。

### 3.2 升级步骤 <a id="upgrade"></a>

```bash
# 1) 从官网下载新版 deb（www.codebuddy.ai）
# 2) 覆盖安装（同包名，直接升级）
sudo dpkg -i codebuddy-cn_<版本>_amd64.deb
# 3) 如提示依赖缺失（Ubuntu 26.04 的 t64 包名差异），补装依赖
sudo apt-get -f install
# 4) 重启 IDE（或 Ctrl+Shift+P → 「重新加载窗口」）
```

安装前后建议确认版本：

```bash
dpkg -l codebuddy-cn | tail -1
python3 -c "import json;print(json.load(open('/usr/share/buddycn/resources/app/product.json'))['version'])"
```

## 4. 用户数据目录 <a id="dirs"></a>

CodeBuddy 的用户数据分散在 **四个目录**（实测体积为 2026-09-12 本机快照，仅作量级参考）：

| 目录 | 体积 | 内容 | 说明 |
| --- | --- | --- | --- |
| `~/.config/CodeBuddy CN/` | 131 MB | `User/settings.json`（**IDE 设置，含本文的权限开关**）、`History/`、`workspaceStorage/`、`logs/<时间戳>/`、`CrashReport/` | 与 VS Code 一致的用户数据布局 |
| `~/.codebuddycn/` | 200 MB | `extensions/`（已装扩展 + `extensions.json`）、`argv.json`（持久启动参数） | 扩展宿主目录 |
| `~/.codebuddy/` | 141 MB | `settings.json`（**插件启用登记**）、`mcp.json`（MCP server 登记）、`plugins/`（插件市场）、`skills-marketplace/`（技能市场）、`inspiration/`、`logs/`、`diagnostics/` | CodeBuddy AI 侧配置（与 IDE 设置分开） |
| `~/.local/share/CodeBuddyExtension/` | 71 MB | `Logs/CodeBuddyIDE/<日期>/<工作区>__<hash>.log`、会话与工作区缓存 | **对话与扩展运行日志**，排障首选 |

清理建议：`History/`、`logs/`、`Logs/` 属可清缓存；`User/settings.json`、`~/.codebuddy/settings.json`、`argv.json` 属配置，勿随意删。

## 5. 首次配置 <a id="setup"></a>

| 项 | 位置 / 键 | 本机现状（2026-09-12 核实） |
| --- | --- | --- |
| 界面语言 | `~/.codebuddycn/argv.json` → `locale` | `zh-cn` |
| 崩溃上报 | `~/.codebuddycn/argv.json` → `enable-crash-reporter` | `false`（关闭上报） |
| 硬件加速 | `~/.codebuddycn/argv.json` → `disable-hardware-acceleration` | 注释态（未启用软件渲染） |
| 插件启用 | `~/.codebuddy/settings.json` → `enabledPlugins` | 已启用官方插件：`pptx`、`pdf`、`docx`、`xlsx`、`agent-browser`、`playwright-cli`、`skills-sec-audit`、`find-skills` |
| 插件/技能市场 | `~/.codebuddy/plugins/`、`~/.codebuddy/skills-marketplace/` | 已拉取官方市场；技能市场版本号见 `~/.codebuddy/.skills-marketplace-version` |
| MCP server | `~/.codebuddy/mcp.json` | `{"mcpServers": {}}`（暂未接入 MCP） |
| 补全模型 | 设置 `codingcopilot.selectedCompletionModel` | 空值 = 使用默认模型；可在补全状态栏菜单切换 |
| 提交信息风格 | `codingcopilot.commitMessageStyle` / `commitMessageLanguage` | `Auto` / `zh_CN` |
| 编辑器关联（双击行为） | `~/.config/CodeBuddy CN/User/settings.json` → `workbench.editorAssociations` | `*.html` / `*.htm` → 内置 HTML 预览 `codebuddy.html.previewEditor`；`*.md` / `*.markdown` → 内置 Markdown 预览 `vscode.markdown.preview.editor`（详见[第 7 节](#html-preview)） |

> 登录与账号：以 IDE 内登录态为准（本机已登录），凭据不入文档；退出登录后插件市场与技能市场会重新校验。

## 6. 权限与免确认设置 <a id="permission"></a>

CodeBuddy 的权限开关都在 **IDE 用户设置** `~/.config/CodeBuddy CN/User/settings.json`（键前缀 `codingcopilot.`），与 `~/.codebuddy/settings.json`（插件登记）不是同一个文件。

### 6.1 本机当前取值 <a id="permission-current"></a>

| 设置项 | 本机值 | 含义 |
| --- | --- | --- |
| `codingcopilot.autoRunMode` | `runEverything` | **代理运行工具的总体模式**：`askEveryTime`（每次都询问）/ `runEverything`（运行所有内容，含命令执行、MCP 与文件写入）。本机设为「运行所有内容」= 全部通过 |
| `codingcopilot.autoRun` | `true` | 大模型自动运行命令，无需手动确认（开关级） |
| `codingcopilot.autoModifyFile` | `true` | 大模型自动修改文件，无需手动确认（开关级） |
| `codingcopilot.autoAcceptWebSearch` | `true`（默认） | 自动接受网络搜索结果 |
| `codingcopilot.customBlacklistCommands` | `[]` | 自定义危险命令黑名单：每项为对整条命令匹配的正则，命中的命令会被拦截或需确认（在内置安全规则之上生效） |
| `codingcopilot.disabledSecurityCategories` | `["injection","scriptExec","powershell"]` | 禁用的内置安全检查类别：被禁用类别下的检查全部跳过。可选值：`diskOps`、`windowsSystem`、`network`、`systemServices`、`userManagement`、`fileDelete`、`permissions`、`processControl`、`gitOps`、`injection`、`scriptExec`、`powershell`、`custom` |
| `codingcopilot.safeDeleteEnabled` | 默认 `true` | 删除操作（`rm`/`unlink`/`rmdir`/`del`/`delete_file` 等）先移入回收站；批量删除达阈值仍需确认。**建议保留默认** |
| `codingcopilot.safeDeleteBulkThreshold` | 默认 `500` | 单次删除文件数达该值触发批量删除确认；值越大提示越少 |

> 安全边界：`autoRunMode = runEverything` 等于允许 AI 不经确认执行本机命令与写文件。若临时收紧，改回 `askEveryTime` 并重载窗口即可；删除类操作另有回收站与批量阈值兜底（上表后两行）。

### 6.2 修改与生效 <a id="permission-apply"></a>

```bash
# 查看当前权限相关设置
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/.config/CodeBuddy CN/User/settings.json')
d = json.load(open(p, encoding='utf-8'))
for k, v in d.items():
    if k.startswith('codingcopilot.') and any(t in k for t in ['autoRun', 'autoModify', 'autoAccept', 'Security', 'Blacklist', 'safeDelete']):
        print(k, '=', json.dumps(v, ensure_ascii=False))
PY
```

- **改法**：编辑 `~/.config/CodeBuddy CN/User/settings.json`，或 IDE 内 `Ctrl+,` 打开设置后搜索 `autoRun` / `autoRunMode`。
- **生效**：设置文件改动需 `Ctrl+Shift+P` → 「重新加载窗口」（或重启 IDE）；对话侧若还有模式级同名开关，需在对话设置里再确认一次。
- **还原**：本机改配置前均留有带时间戳的备份，形如 `~/.config/CodeBuddy CN/User/settings.json.bak-YYYYmmdd-HHMMSS`，直接覆盖回去再重载窗口即可。

本机 2026-09-12 生效片段（其余键略）：

```json
{
  "codingcopilot.customBlacklistCommands": [],
  "codingcopilot.disabledSecurityCategories": ["injection", "scriptExec", "powershell"],
  "codingcopilot.autoRun": true,
  "codingcopilot.autoModifyFile": true,
  "codingcopilot.autoRunMode": "runEverything"
}
```

## 7. 扩展管理与 HTML 文档预览 <a id="extensions"></a>

### 7.1 扩展目录与市场 <a id="ext-dirs"></a>

| 项 | 取值 |
| --- | --- |
| 扩展宿主目录 | `~/.codebuddycn/extensions/`（**不是 `~/.vscode/extensions`**——本机该目录存在但属其他编辑器，装到那儿 CodeBuddy 不加载） |
| 扩展登记文件 | `~/.codebuddycn/extensions/extensions.json` |
| 扩展市场 | **open-vsx.org**（`product.json` → `extensionsGallery.serviceUrl = https://open-vsx.org/vscode/gallery`），非微软市场 → 只收录在 open-vsx 发布过的扩展 |
| 内置扩展 | `/usr/share/buddycn/resources/app/extensions/`（101 个，含 `simple-browser`、`html`、`html-language-features`、`media-preview`、`markdown-language-features` 等，随应用发布不占用户目录） |
| AI 侧插件 | 与 IDE 扩展分开：`~/.codebuddy/settings.json` → `enabledPlugins`（见第 5 节） |

### 7.2 安装与卸载扩展（应用自带 CLI） <a id="ext-install"></a>

CodeBuddy 的桌面 CLI 在应用目录内（**未加入 PATH**），用法与 VS Code 一致：

```bash
CLI=/usr/share/buddycn/bin/buddycn
"$CLI" --list-extensions                              # 列出已装扩展
"$CLI" --install-extension <发布者.名称> --force       # 从 open-vsx 安装
"$CLI" --uninstall-extension <发布者.名称>
```

实测注意事项：

- 扩展 ID 必须写成 **`发布者.名称`**；写错会直接报 `Extension 'xxx' not found.`（例：Live Preview 的正确 ID 是 `ms-vscode.live-server`，写成 `ms-vscode.live-preview` 会报 not found）；
- 安装过程**没有进度回显**，网络慢时长时间无输出属正常；判断结果以 `~/.codebuddycn/extensions/` 是否出现 `发布者.名称-版本-<平台>` 目录为准（如 `ms-vscode.live-server-0.4.16-universal`）；
- 安装完成后需 `Ctrl+Shift+P` → 「重新加载窗口」才会激活；
- 中断/卡死可能残留 `sh /usr/share/buddycn/bin/buddycn --install-extension …` 进程（`pgrep -af install-extension` 查看），`kill <pid>` 后重试；
- 安装前可先确认市场可达：`curl -I https://open-vsx.org/api/<发布者>/<名称>`（本机 2026-09-12 实测直连正常，秒级响应）。

本机已装扩展（2026-09-12 快照，除标注外均为先前安装）：

- `ms-python.python` / `ms-python.debugpy` / `ms-python.vscode-python-envs` / `wubzbz.debugpy`、`detachhead.basedpyright`（Python 与类型检查）
- `cweijan.vscode-office`（Office 文件查看）、`donjayamanne.githistory`（Git 历史）、`sst-dev.opencode`、`fengze233.dsh-vscode-panel`
- **`ms-vscode.live-server` 0.4.16（Live Preview，本次为 HTML 预览新装）**

### 7.3 HTML 预览的三条路 <a id="html-preview"></a>

| 方式 | 触发 | 适用与限制 |
| --- | --- | --- |
| **内置 HTML 预览编辑器**（默认可用，零配置） | 资源管理器**双击 html 文件**；命令面板 `codebuddyPreview.toggleMode`（预览 ↔ 源码切换）、`codebuddyPreview.openHtmlSource`（打开源码）、`codebuddyPreview.openPreview`（打开预览） | CodeBuddy 内建扩展 `vscode.markdown-language-features`（v1.0.0，随应用发布）在 `customEditors` 里注册了 `codebuddy.html.previewEditor`（displayName **HTML Preview**，selector `*.html`/`*.htm`），本机已用 `workbench.editorAssociations` 关联；同扩展还提供 `vscode.markdown.preview.editor`（Markdown Preview，`codebuddyPreview.openMarkdownSource` 打开源码） |
| **Live Preview 扩展**（本次已装） | 右键 html → **Show Preview**（命令 `livePreview.start.internalPreview.atFile`） | 按文件所在目录起 http 服务，相对链接跳转与实时刷新更好；结束用 `Live Preview: Stop Server` |
| **Simple Browser**（内置命令） | `Ctrl/Cmd+Shift+P` → `Simple Browser: Show` → 填 URL | 内置浏览器面板，**只支持 http/https，`file://` 打不开**，需先有静态服务（见 7.4） |

本机用户设置 `~/.config/CodeBuddy CN/User/settings.json` 的现有关联（决定了双击行为）：

```json
"workbench.editorAssociations": {
  "*.html": "codebuddy.html.previewEditor",
  "*.htm": "codebuddy.html.previewEditor",
  "*.md": "vscode.markdown.preview.editor",
  "*.markdown": "vscode.markdown.preview.editor"
}
```

### 7.4 本仓库（bms 文档）预览 <a id="bms-docs"></a>

- `bms文档/**/*.html` 布局线框图 / 原型 / 组件原型资产（167 个）引用同目录的 `文档样式.css`、`mermaid.min.js`：用**内置预览**或 **Live Preview** 打开单个文件即可。
- 若预览出现「样式/脚本没加载、mermaid 不渲染」，改用 http 方式（起静态服务后用 Simple Browser 或外部浏览器打开），避免 `file://` 限制。
- md 正文里的 mermaid 需另装 **`bierner.markdown-mermaid`**（open-vsx 有收录，装法见 7.2）：`*.md` 已关联内置 Markdown 预览，装完扩展重载窗口后预览即渲染。
- 起静态文档服务（等价 Live Preview 的底座，可手动控制端口与生命周期）：

```bash
cd ~/develop/bizs/bms
python3 -m http.server 8765 --directory bms文档     # 访问 http://localhost:8765/
pkill -f "http.server 8765"                         # 用完关闭
```

### 7.5 扩展与预览排障 <a id="ext-trouble"></a>

| 现象 | 处理 |
| --- | --- |
| 装扩展报 `Extension '…' not found.` | ID 或市场问题：ID 必须 `发布者.名称`；用 `curl -I https://open-vsx.org/api/<发布者>/<名称>` 确认 open-vsx 是否收录、网络是否可达 |
| 装了扩展但不生效 | 未重载窗口；或装错目录（应为 `~/.codebuddycn/extensions/`，不是 `~/.vscode/extensions`） |
| 安装命令长时间无回显 | 属正常（无进度输出）；查 `~/.codebuddycn/extensions/` 是否出现新目录；长时间卡死则 `kill` 残留进程后重试 |
| 双击 html 打开了源码 | `workbench.editorAssociations` 被改动；恢复 `*.html` / `*.htm` → `codebuddy.html.previewEditor` |
| 预览页无样式、mermaid 不渲染 | 走 http：Live Preview 或 7.4 的静态服务，别用 `file://` |
| md 里 mermaid 是代码块 | 未装 `bierner.markdown-mermaid`（或装后未重载窗口） |

## 8. 常用设置与排障 <a id="trouble"></a>

### 8.1 常用设置 <a id="settings"></a>

| 设置项 | 说明 |
| --- | --- |
| `codingcopilot.submitMessageShortcut` | 发送快捷键：`Enter`（发送=Enter，换行=Ctrl/Cmd+Enter）或 `CtrlOrCmdAndEnter` |
| `codingcopilot.enableAutoCompletions` | 自动触发代码补全（回车、停顿触发）；关闭后可用快捷键手动触发 |
| `codingcopilot.enableCraftCodeBase` | Craft 模式启用代码库检索 |
| `codingcopilot.enableInlineChat` / `toolbarOnSelection` | 内联聊天与选中悬浮工具栏 |
| `codingcopilot.enableNextEditSuggestions` | 下一处编辑预测 |
| `codingcopilot.enabledWebSearch` | 联网搜索总开关 |
| `codingcopilot.HttpProxyMode` / `codingcopilot.HTTPProxy` | 网络代理：`system`（跟随系统）/ `manual`（手动，仅手动模式读 `HTTPProxy`） |
| `codingcopilot.disableBuiltInMarketplace` | 无法访问内置插件市场（`download.codebuddy.cn`）时开启，**跳过市场安装与定期更新检查**，避免对话请求被反复的市场拉取超时阻塞；等效于设置环境变量 `CODEBUDDY_SKIP_BUILTIN_...` |
| `codingcopilot.autoUpdateThirdPartyMarketplaces` | 每天检查一次第三方（Git 类型）插件市场并后台静默更新（默认关） |
| `codingcopilot.enableModelOptimization` | 允许使用对话数据做模型优化（默认关，按需开启） |

### 8.2 排障入口 <a id="trouble-entry"></a>

| 现象 | 处理 |
| --- | --- |
| 对话卡住/反复超时（市场拉取阻塞） | 开启 `codingcopilot.disableBuiltInMarketplace`（或设等效环境变量）后重载窗口 |
| 界面白屏/花屏等渲染异常 | 在 `~/.codebuddycn/argv.json` 打开 `"disable-hardware-acceleration": true`，重启 IDE（本机当前未启用） |
| 命令被拦截或反复确认 | 检查 `codingcopilot.customBlacklistCommands`（命中正则会拦截）与 `codingcopilot.autoRunMode` 取值 |
| 删除的文件想找回 | `safeDeleteEnabled` 默认开启时删除先进回收站；关闭后为永久删除 |
| 需要看运行日志 | 对话/扩展日志 `~/.local/share/CodeBuddyExtension/Logs/CodeBuddyIDE/<日期>/<工作区>__<hash>.log`；IDE 日志 `~/.config/CodeBuddy CN/logs/<时间戳>/` |
| 崩溃排查 | `~/.config/CodeBuddy CN/CrashReport/`（崩溃转储）与 `~/.codebuddy/diagnostics/` |
| 网络代理问题 | 核对 `HttpProxyMode`（系统/手动）与 `HTTPProxy`；与系统代理设置保持一致 |

## 9. 检查清单 <a id="checklist"></a>

- □ 版本已核实：包 `codebuddy-cn` 与应用版本分别取自 `dpkg -l` 与 `product.json`
- □ 明确无 apt 源 → 升级靠手工 `.deb` 覆盖安装，卸载不删用户数据
- □ 四个用户数据目录职责清晰（IDE 设置 / 扩展宿主 / AI 配置 / 日志），清理只动缓存目录
- □ 权限设置全部落在 `~/.config/CodeBuddy CN/User/settings.json`（`codingcopilot.*`），改动前有带时间戳备份
- □ 免确认取值明确：`autoRunMode=runEverything` + `autoRun/autoModifyFile=true`，回收站与批量删除阈值兜底保留
- □ 首配项齐备：语言 `zh-cn`、崩溃上报关闭、插件与技能市场、MCP 登记位、补全模型与提交信息风格
- □ 扩展管理口径明确：扩展目录 `~/.codebuddycn/extensions`、市场 open-vsx、安装用应用自带 CLI（全路径 `--install-extension`），与 `~/.vscode/extensions` 区分开
- □ 文档预览口径明确：html 双击走内置 HTML 预览（`codebuddy.html.previewEditor`）、需要相对引用/实时刷新用 Live Preview、`file://` 不可用改走 http 静态服务；md mermaid 需 `bierner.markdown-mermaid`
- □ 排障入口齐备：日志三处、崩溃转储、市场超时与渲染异常的处置办法
- □ 本机事实均经核实（2026-09-12），未写入账号/令牌等凭据

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》《[opencode部署使用说明](opencode部署使用说明.md)》《[命名规范](../../规范/命名规范.md)》配套 · 记录 2026-09-12 mjpc 本机核实结果
