# CodeBuddy 部署使用说明

> mjpc 开发机 CodeBuddy（腾讯云代码助手 IDE，codebuddy-cn 4.12.0 / 应用 1.106.1）部署、配置、扩展管理、文档预览、权限与排障实录 · 2026-09-12 部署 / 2026-09-13 免确认排障 / 2026-10-03 运行与调试链路排障 / 2026-10-04 事实同步 / 2026-10-04 本机裸跑「全套」与后端断点口径 / 2026-10-10 Playwright MCP 登记与浏览器真机验证口径

[文档首页](../../文档首页.md) › 资料 › 开发机 › CodeBuddy 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[google-chrome部署使用说明 →](google-chrome部署使用说明.md)　[playwright部署使用说明 →](playwright部署使用说明.md)　[opencode部署使用说明 →](opencode部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS，GNOME，Wayland，NVIDIA RTX 4090）上 **CodeBuddy** 的部署与使用：安装来源与版本、四个用户数据目录的作用、首次配置项（登录/语言/插件/技能/MCP）、**权限与免确认设置**（自动运行命令、文件自动修改、安全检查类别、黑名单、安全删除；含**免确认失效的排查：安全类别的真正存储与生效链路**，见[6.3](#permission-security)）、**扩展管理（扩展目录 / open-vsx 市场 / 应用自带 CLI）与 HTML 文档预览**（内置 HTML 预览、Live Preview、Simple Browser；bms 文档资产与 md mermaid 的预览办法）、**运行与调试启动项**（`.vscode/launch.json` / `tasks.json` 的两处落点与「VS Code 不读子目录 `.vscode`」口径、启动项与任务清单、**端口自愈 / 就绪正则 / Python 解释器与 pyright 口径 / Chrome 绝对路径**排障，见[第 8 节](#debug)）、**本机裸跑后端「全套」**（脚本起停 / 账号种子 / **后端断点口径**，见[8.5](#local-stack)）、**工作区级 `.codebuddy/`（工作记忆三件套）与 AI 协作口径**（见[第 10 节](#workspace-ai)）、**浏览器真机验证（Playwright MCP 登记、走查用法与 playwright-cli 选型口径**，见 [10.6](#workspace-ai-browser)）、常用设置与排障入口。

本文档与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》「开发设施清单」节与「桌面快捷方式设置（通用）」节配套；CodeBuddy 与 [opencode](opencode部署使用说明.md)、[deepseek-harness](../AI/deepseek_harness部署使用说明.md) 同属本机 AI 编码工具，三者互不干扰、各自独立部署。

> **取值说明**：本机路径统一用 `~` 表示（开发机开发用户为 `minjian`）；账号、令牌等凭据不在本文记录，以本机登录态与《[本地资源](../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 环境概览 <a id="env"></a>

| 项            | 取值                                                                                                                                                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 系统 / 桌面   | Ubuntu 26.04.1 LTS（x86_64）；GNOME（`XDG_SESSION_TYPE=wayland`）                                                                                                                                                                               |
| 应用名称      | CodeBuddy CN（`applicationName = buddycn`，`urlProtocol = codebuddycn`）                                                                                                                                                                      |
| 应用版本      | **1.106.1**（stable；commit `b4c35ed0`，构建日期 2026-09-04）                                                                                                                                                                             |
| deb 包        | `codebuddy-cn` **4.12.0**（amd64；Maintainer `CodeBuddy Team <codebuddy@tencent.com>`，Homepage `https://www.codebuddy.ai`）                                                                                                          |
| 同源桌面包    | `workbuddy` 5.5.6（腾讯 WorkBuddy，与 CodeBuddy 同一官网分发）                                                                                                                                                                                  |
| 安装形态      | **手工 `.deb` 安装，无 apt 源**（`/etc/apt/sources.list*` 中无相关仓库）→ **不随 `apt upgrade` 升级**，需下载新包覆盖安装                                                                                                      |
| 应用目录      | `/usr/share/buddycn/`（二进制 `/usr/share/buddycn/bin/buddycn`）                                                                                                                                                                              |
| 启动器        | `/usr/share/applications/buddycn.desktop` → `Exec=/usr/share/buddycn/bin/buddycn %F`（另有 `buddycn-url-handler.desktop` 处理 `codebuddycn://` 链接）                                                                                    |
| 服务端组件名  | `codebuddy-server-cn`（远程/SSH 场景使用，本机未部署）                                                                                                                                                                                          |
| CLI           | PATH 中**无** `codebuddy` / `cbc`；但应用自带桌面 CLI **`/usr/share/buddycn/bin/buddycn`**（VS Code 同款，支持 `--install-extension` / `--list-extensions` 等，扩展管理即用它，见第 7 节）；如需独立 CLI 另按其官方文档部署 |
| Electron 版本 | 37.7.0（由进程启动参数核实）                                                                                                                                                                                                                      |

> 本机 **无 GPU/Wayland 崩溃**：CodeBuddy 日志中未见 GPU 进程段错误（与 [opencode](opencode部署使用说明.md) 在本机 NVIDIA + Wayland 下的 GPU 崩溃不是一类问题），因此**无需** `--disable-gpu`；若日后出现渲染异常，排障方式见[第 9 节](#trouble)。

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

CodeBuddy 的用户数据分散在 **四个目录**（实测体积为 2026-09-12 本机快照，仅作量级参考）。此外工作区根还会有一个 `.codebuddy/`（工作记忆），见[第 10 节](#workspace-ai)：

| 目录                                   | 体积   | 内容                                                                                                                                                                                                               | 说明                                   |
| -------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| `~/.config/CodeBuddy CN/`            | 131 MB | `User/settings.json`（**IDE 设置，含本文的权限开关**）、`History/`、`workspaceStorage/`、`logs/<时间戳>/`、`CrashReport/`                                                                          | 与 VS Code 一致的用户数据布局          |
| `~/.codebuddycn/`                    | 200 MB | `extensions/`（已装扩展 + `extensions.json`）、`argv.json`（持久启动参数）                                                                                                                                   | 扩展宿主目录                           |
| `~/.codebuddy/`                      | 141 MB | `settings.json`（**插件启用登记**）、`mcp.json`（MCP server 登记）、`skills/`（AI 技能）、`plugins/`（插件市场）、`skills-marketplace/`（技能市场）、`inspiration/`、`logs/`、`diagnostics/` | CodeBuddy AI 侧配置（与 IDE 设置分开） |
| `~/.local/share/CodeBuddyExtension/` | 71 MB  | `Logs/CodeBuddyIDE/<日期>/<工作区>__<hash>.log`、会话与工作区缓存                                                                                                                                                | **对话与扩展运行日志**，排障首选 |

清理建议：`History/`、`logs/`、`Logs/` 属可清缓存；`User/settings.json`、`~/.codebuddy/settings.json`、`argv.json` 属配置，勿随意删。

## 5. 首次配置 <a id="setup"></a>

| 项                     | 位置 / 键                                                                         | 本机现状（2026-09-12 核实）                                                                                                                                                                  |
| ---------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 界面语言               | `~/.codebuddycn/argv.json` → `locale`                                        | `zh-cn`                                                                                                                                                                                    |
| 崩溃上报               | `~/.codebuddycn/argv.json` → `enable-crash-reporter`                         | `false`（关闭上报）                                                                                                                                                                        |
| 硬件加速               | `~/.codebuddycn/argv.json` → `disable-hardware-acceleration`                 | 注释态（未启用软件渲染）                                                                                                                                                                     |
| 插件启用               | `~/.codebuddy/settings.json` → `enabledPlugins`                              | 已启用官方插件：`pptx`、`pdf`、`docx`、`xlsx`、`agent-browser`、`playwright-cli`、`skills-sec-audit`、`find-skills`                                                          |
| 插件/技能市场          | `~/.codebuddy/plugins/`、`~/.codebuddy/skills-marketplace/`                   | 已拉取官方市场；技能市场版本号见`~/.codebuddy/.skills-marketplace-version`                                                                                                                 |
| MCP server             | `~/.codebuddy/mcp.json`                                                         | 按需登记 MCP server（登记与用法见《[deepseek_harness部署使用说明](../AI/deepseek_harness部署使用说明.md)》MCP 相关节与工具自身文档）；本机已登记 **Playwright MCP**（`mcp__playwright__*`，系统 Chrome + 隔离会话），供开发态浏览器真机走查，用法与选型见 [10.6](#workspace-ai-browser) |
| 补全模型               | 设置`codingcopilot.selectedCompletionModel`                                     | 空值 = 使用默认模型；可在补全状态栏菜单切换                                                                                                                                                  |
| 提交信息风格           | `codingcopilot.commitMessageStyle` / `commitMessageLanguage`                  | `Auto` / `zh_CN`                                                                                                                                                                         |
| 编辑器关联（双击行为） | `~/.config/CodeBuddy CN/User/settings.json` → `workbench.editorAssociations` | `*.html` / `*.htm` → 内置 HTML 预览 `codebuddy.html.previewEditor`；`*.md` / `*.markdown` → 内置 Markdown 预览 `vscode.markdown.preview.editor`（详见[第 7 节](#html-preview)） |

> 登录与账号：以 IDE 内登录态为准（本机已登录），凭据不入文档；退出登录后插件市场与技能市场会重新校验。

## 6. 权限与免确认设置 <a id="permission"></a>

CodeBuddy 的权限开关都在 **IDE 用户设置** `~/.config/CodeBuddy CN/User/settings.json`（键前缀 `codingcopilot.`），与 `~/.codebuddy/settings.json`（插件登记）不是同一个文件。

### 6.1 本机当前取值 <a id="permission-current"></a>

| 设置项                                       | 本机值                                                           | 含义                                                                                                                                                                                                                                                                                                                                                              |
| -------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `codingcopilot.autoRunMode`                | `runEverything`                                                | **代理运行工具的总体模式**：`askEveryTime`（每次都询问）/ `runEverything`（运行所有内容，含命令执行、MCP 与文件写入）。本机设为「运行所有内容」= 全部通过                                                                                                                                                                                               |
| `codingcopilot.autoRun`                    | `true`                                                         | 大模型自动运行命令，无需手动确认（开关级）                                                                                                                                                                                                                                                                                                                        |
| `codingcopilot.autoModifyFile`             | `true`                                                         | 大模型自动修改文件，无需手动确认（开关级）                                                                                                                                                                                                                                                                                                                        |
| `codingcopilot.autoAcceptWebSearch`        | `true`（默认）                                                 | 自动接受网络搜索结果                                                                                                                                                                                                                                                                                                                                              |
| `codingcopilot.customBlacklistCommands`    | `[]`                                                           | 自定义危险命令黑名单：每项为对整条命令匹配的正则，命中的命令会被拦截或需确认（在内置安全规则之上生效）                                                                                                                                                                                                                                                            |
| `codingcopilot.disabledSecurityCategories` | 全部 13 类（本机 2026-09-13 取值，见[6.3](#permission-security)） | 禁用的内置安全检查类别：被禁用类别下的检查全部跳过。可选值：`diskOps`、`windowsSystem`、`network`、`systemServices`、`userManagement`、`fileDelete`、`permissions`、`processControl`、`gitOps`、`injection`、`scriptExec`、`powershell`、`custom`。**该设置的真正存储不是本文件**，手改会被回写，改法见[6.3](#permission-security) |
| `codingcopilot.safeDeleteEnabled`          | 默认`true`                                                     | 删除操作（`rm`/`unlink`/`rmdir`/`del`/`delete_file` 等）先移入回收站；批量删除达阈值仍需确认。**建议保留默认**                                                                                                                                                                                                                                    |
| `codingcopilot.safeDeleteBulkThreshold`    | 默认`500`                                                      | 单次删除文件数达该值触发批量删除确认；值越大提示越少                                                                                                                                                                                                                                                                                                              |

> 安全边界：`autoRunMode = runEverything` 等于允许 AI 不经确认执行本机命令与写文件。若临时收紧，改回 `askEveryTime` 并重载窗口即可；删除类操作另有回收站与批量阈值兜底（上表后两行）。
>
> 本机 2026-09-13 已放开全部 13 类安全类别：`injection`、`scriptExec`、`powershell`、`fileDelete`、`gitOps`、`permissions`、`processControl`、`network`、`diskOps`、`windowsSystem`、`systemServices`、`userManagement`、`custom`；放开 `fileDelete` 后 `rm` 等删除命令不再弹确认（仍走回收站兜底）。收紧办法与失效排查见[6.3](#permission-security)。

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
- **生效**：设置文件改动需 `Ctrl+Shift+P` → 「重新加载窗口」（或重启 IDE）；对话侧若还有模式级同名开关，需在对话设置里再确认一次。**例外**：`disabledSecurityCategories` 重载窗口不生效（会被权威存储回写），按[6.3](#permission-security)处理。
- **还原**：改配置前有带时间戳备份——`settings.json` 形如 `~/.config/CodeBuddy CN/User/settings.json.bak-YYYYmmdd-HHMMSS`，安全类别的权威存储形如 `~/.config/CodeBuddy CN/User/globalStorage/state.vscdb.bak-YYYYmmddHHMMSS`，直接覆盖回去再重启 IDE（安全类别需冷启动）即可。

本机 2026-09-13 生效片段（其余键略）：

```json
{
  "codingcopilot.customBlacklistCommands": [],
  "codingcopilot.disabledSecurityCategories": ["injection", "scriptExec", "powershell", "fileDelete", "gitOps", "permissions", "processControl", "network", "diskOps", "windowsSystem", "systemServices", "userManagement", "custom"],
  "codingcopilot.autoRun": true,
  "codingcopilot.autoModifyFile": true,
  "codingcopilot.autoRunMode": "runEverything"
}
```

### 6.3 免确认失效的排查：安全类别的真正存储与生效链路 <a id="permission-security"></a>

**现象**：`codingcopilot.disabledSecurityCategories` 明明已放开，命令仍弹安全确认（IDE 日志里该命令的 `Permission decision: source=safety_rule_ask`）。

**原因**：这个设置的权威值**不在** `settings.json`。实测链路是三段：

1. 权威值存在 `~/.config/CodeBuddy CN/User/globalStorage/state.vscdb` → `ItemTable["CodeBuddy.settings"]` → `autoApprovalSettings.disabledSecurityCategories`（明文 JSON）；
2. IDE **每次启动**用它的值回写 `User/settings.json`，并同步给扩展（`SyncSettingsFromIDECommand` → LocalStorage `chatModeSettings.craft`，该键为加密 secret，不可直接改）；
3. 每条命令执行时，终端安全校验再读一次（日志 `[SecurityCheck] Loaded N disabled security categories: …`）。

由此得出三个坑（本机逐条实测）：

| 做法                             | 结果           | 原因                                                   |
| -------------------------------- | -------------- | ------------------------------------------------------ |
| 手改`settings.json` 后重载窗口 | 无效，值被还原 | 启动/重载时用权威存储回写`settings.json`             |
| 只「重新加载窗口」               | 无效           | 重载不重读权威存储（进程没重启，用的还是内存里的旧值） |
| 写`~/.codebuddy/settings.json` | 无效           | 那是插件/技能/MCP 登记，不参与安全检查                 |

内置类别与对应命令（扩展内置表，判断该放开哪一类时查这里）：

| 类别                                         | 命令                                                                                             |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `fileDelete`                               | `rm` / `rmdir` / `del` / `erase` / `find` / `locate`                                 |
| `permissions`                              | `chmod` / `chown` / `chgrp` / `attrib` / `icacls`                                      |
| `processControl`                           | `kill` / `killall` / `pkill` / `taskkill`                                                |
| `gitOps`                                   | `git`                                                                                          |
| `injection`                                | `open` / `start` / `xdg-open` 及下载执行类正则                                             |
| `diskOps`                                  | `dd` / `mkfs` / `fdisk` / `parted` / `cfdisk` / `sfdisk` / `format` / `diskpart` |
| `network`                                  | `nc` / `ncat` / `netcat` / `socat` / `iptables` / `ufw` / `firewall-cmd`           |
| `systemServices`                           | `systemctl` / `service` / `chkconfig` / `crontab` / `at`                               |
| `userManagement`                           | `passwd` / `usermod` / `useradd` / `userdel`                                             |
| `windowsSystem`                            | `wmic` / `takeown` / `cipher`                                                              |
| `scriptExec` / `powershell` / `custom` | 脚本执行类正则 / PowerShell 专属 / 自定义黑名单（即`customBlacklistCommands`）                 |

**改法 A（推荐，一次到位）：完全退出 → 改权威存储 → 冷启动**

```bash
# 1) 完全退出 CodeBuddy（确认进程已退出：应无输出）
pgrep -f buddycn

# 2) 改写权威存储（先自动备份 state.vscdb）
python3 - <<'PY'
import json, os, shutil, sqlite3, time

DB = os.path.expanduser('~/.config/CodeBuddy CN/User/globalStorage/state.vscdb')
KEY = 'CodeBuddy.settings'
TARGET = ['injection', 'scriptExec', 'powershell', 'fileDelete', 'gitOps',
          'permissions', 'processControl', 'network', 'diskOps', 'windowsSystem',
          'systemServices', 'userManagement', 'custom']

shutil.copy2(DB, DB + '.bak-' + time.strftime('%Y%m%d%H%M%S'))
conn = sqlite3.connect(DB)
data = json.loads(conn.execute('SELECT value FROM ItemTable WHERE key=?', (KEY,)).fetchone()[0])
print('改前:', data['autoApprovalSettings'].get('disabledSecurityCategories'))
data['autoApprovalSettings']['disabledSecurityCategories'] = TARGET
conn.execute('UPDATE ItemTable SET value=? WHERE key=?', (json.dumps(data, ensure_ascii=False), KEY))
conn.commit()
conn.close()
print('改后:', TARGET)
PY

# 3) 启动 CodeBuddy（是重启应用，不是「重新加载窗口」）
```

收紧时把 `TARGET` 换回 `['injection', 'scriptExec', 'powershell']`，或只保留需要的类别。

**改法 B（设置界面）**：`Ctrl+,` → 搜 `disabledSecurityCategories`（中文项名「要禁用的内置安全检查类别」）→ 逐项加入需要的类别。界面改动写的是 IDE 内存与权威存储，不会被回写；若命令仍弹确认，重载窗口一次即可。

**验证（四步取证）**

```bash
# ① 确认真冷启动：进程启动时间刚变、logs 下出现新的时间戳目录
ps -eo pid,lstart,args | grep buddycn | head -1
ls -dt ~/.config/"CodeBuddy CN"/logs/*/ | head -1

# ② 同步与加载日志：类别数与目标一致
D=$(ls -dt ~/.config/"CodeBuddy CN"/logs/*/ | head -1)
grep -rhoa "Synced disabledSecurityCategories to chat mode settings: \[.*\]" "$D"
grep -rhoa "\[SecurityCheck\] Loaded [0-9]* disabled security categories: .*" "$D" | sort -u

# ③ 跑一条此前必弹的命令
touch /tmp/cb_check.txt && rm -f /tmp/cb_check.txt && echo "rm 已执行"

# ④ 看决策来源：还有 safety_rule_ask 说明仍被拦，只剩 auto_run_allow / default_allow 即已放开
grep -rhoa "Permission decision: source=[a-z_]*, allowed=[a-z]*, needConfirm=[a-z]*" "$D" | sort | uniq -c
```

> 判断技巧：第 ④ 步的统计里可能混着旧会话残留的命中，确认方法是在同一条命令里先跑目标命令、再立即统计，看新增的命中指向哪条命令（本机即以此确认 `rm` 已免确认）。

**生效边界**：放开 `fileDelete` 后 `rm` 不再弹确认，删除仍走 `safeDeleteEnabled` 回收站兜底；放开其余类别同理。放开期间建议：临时文件放 `/tmp`、重要目录靠 git 兜底。

## 7. 扩展管理与 HTML 文档预览 <a id="extensions"></a>

### 7.1 扩展目录与市场 <a id="ext-dirs"></a>

| 项           | 取值                                                                                                                                                                                                  |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 扩展宿主目录 | `~/.codebuddycn/extensions/`（**不是 `~/.vscode/extensions`**——本机该目录存在但属其他编辑器，装到那儿 CodeBuddy 不加载）                                                                  |
| 扩展登记文件 | `~/.codebuddycn/extensions/extensions.json`                                                                                                                                                         |
| 扩展市场     | **open-vsx.org**（`product.json` → `extensionsGallery.serviceUrl = https://open-vsx.org/vscode/gallery`），非微软市场 → 只收录在 open-vsx 发布过的扩展                                    |
| 内置扩展     | `/usr/share/buddycn/resources/app/extensions/`（101 个，含 `simple-browser`、`html`、`html-language-features`、`media-preview`、`markdown-language-features` 等，随应用发布不占用户目录） |
| AI 侧插件    | 与 IDE 扩展分开：`~/.codebuddy/settings.json` → `enabledPlugins`（见第 5 节）                                                                                                                    |

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

本机已装扩展（2026-09-12 快照，除标注外均为先前安装；2026-10-03 补装见末条）：

- `ms-python.python` / `ms-python.debugpy` / `ms-python.vscode-python-envs`、`detachhead.basedpyright`（Python 与类型检查）
- `cweijan.vscode-office`（Office 文件查看）、`donjayamanne.githistory`（Git 历史）、`sst-dev.opencode`、`fengze233.dsh-vscode-panel`
- `ms-vscode.live-server` 0.4.16（Live Preview，HTML 预览用）
- **2026-10-03 补装（对应工作区 `extensions.json` 推荐项）**：`dbaeumer.vscode-eslint` 3.0.34、`esbenp.prettier-vscode` 12.4.0、`bierner.markdown-mermaid` 1.32.1；`ms-python.debugpy` 与 `vue.volar` 本已安装
- **2026-10-03 卸载（同命令 ID 冲突，见 [8.4](#debug-trouble)）**：`wubzbz.debugpy`、`devshub-ai.devshub-python` —— 两者是官方扩展的「套壳发行版」，与 `ms-python.debugpy` / `ms-python.python` **注册同一批命令 ID**，导致官方扩展激活抛 `command 'python.configureTests' already exists`，`type: debugpy` 启动项卡在「正在加载 python 扩展」。卸载后只保留官方三件。

### 7.3 HTML 预览的三条路 <a id="html-preview"></a>

| 方式                                               | 触发                                                                                                                                                                                            | 适用与限制                                                                                                                                                                                                                                                                                                                                                                              |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **内置 HTML 预览编辑器**（默认可用，零配置） | 资源管理器**双击 html 文件**；命令面板 `codebuddyPreview.toggleMode`（预览 ↔ 源码切换）、`codebuddyPreview.openHtmlSource`（打开源码）、`codebuddyPreview.openPreview`（打开预览） | CodeBuddy 内建扩展`vscode.markdown-language-features`（v1.0.0，随应用发布）在 `customEditors` 里注册了 `codebuddy.html.previewEditor`（displayName **HTML Preview**，selector `*.html`/`*.htm`），本机已用 `workbench.editorAssociations` 关联；同扩展还提供 `vscode.markdown.preview.editor`（Markdown Preview，`codebuddyPreview.openMarkdownSource` 打开源码） |
| **Live Preview 扩展**（本次已装）            | 右键 html →**Show Preview**（命令 `livePreview.start.internalPreview.atFile`）                                                                                                         | 按文件所在目录起 http 服务，相对链接跳转与实时刷新更好；结束用`Live Preview: Stop Server`                                                                                                                                                                                                                                                                                             |
| **Simple Browser**（内置命令）               | `Ctrl/Cmd+Shift+P` → `Simple Browser: Show` → 填 URL                                                                                                                                      | 内置浏览器面板，**只支持 http/https，`file://` 打不开**，需先有静态服务（见 7.4）                                                                                                                                                                                                                                                                                               |

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

- `bms文档/**/*.html` 布局线框图 / 原型 / 组件原型资产（**200 个**，2026-10-04 复核；均在 `bms文档/设计/` 下——`原型设计/` 各域 + `布局设计/`）引用同目录的 `文档样式.css`、`mermaid.min.js`：用**内置预览**或 **Live Preview** 打开单个文件即可。
- 若预览出现「样式/脚本没加载、mermaid 不渲染」，改用 http 方式（起静态服务后用 Simple Browser 或外部浏览器打开），避免 `file://` 限制。
- md 正文里的 mermaid 需另装 **`bierner.markdown-mermaid`**（open-vsx 有收录，装法见 7.2）：`*.md` 已关联内置 Markdown 预览，装完扩展重载窗口后预览即渲染。
- 起静态文档服务（等价 Live Preview 的底座，可手动控制端口与生命周期）：

```bash
cd ~/develop/bizs/bms
python3 -m http.server 8765 --directory bms文档     # 访问 http://localhost:8765/
pkill -f "http.server 8765"                         # 用完关闭
```

### 7.5 扩展与预览排障 <a id="ext-trouble"></a>

| 现象                                  | 处理                                                                                                                                |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 装扩展报`Extension '…' not found.` | ID 或市场问题：ID 必须`发布者.名称`；用 `curl -I https://open-vsx.org/api/<发布者>/<名称>` 确认 open-vsx 是否收录、网络是否可达 |
| 装了扩展但不生效                      | 未重载窗口；或装错目录（应为`~/.codebuddycn/extensions/`，不是 `~/.vscode/extensions`）                                         |
| 安装命令长时间无回显                  | 属正常（无进度输出）；查`~/.codebuddycn/extensions/` 是否出现新目录；长时间卡死则 `kill` 残留进程后重试                         |
| 双击 html 打开了源码                  | `workbench.editorAssociations` 被改动；恢复 `*.html` / `*.htm` → `codebuddy.html.previewEditor`                            |
| 预览页无样式、mermaid 不渲染          | 走 http：Live Preview 或 7.4 的静态服务，别用`file://`                                                                            |
| md 里 mermaid 是代码块                | 未装`bierner.markdown-mermaid`（或装后未重载窗口）                                                                                |

## 8. 运行与调试启动项 <a id="debug"></a>

IDE 的「运行和调试」下拉由 `.vscode/launch.json`（启动项）与 `.vscode/tasks.json`（任务 / 前置任务）驱动；bizs / bms 两处配置均已入库（根仓库白名单 `!/.vscode/`）。

### 8.1 位置口径（先看这条） <a id="debug-location"></a>

**VS Code 只读取「被打开的那个根」下的 `.vscode/`，不读取子目录的配置。** 本机曾出现「运行和调试面板为空」，原因就是把 `bizs` 当根打开、而启动项只放在 `bms/.vscode/`。故同一套启动项有两份，**改动须同步两处**（与工作区根 `settings.json` 的「双保险：裸目录打开 / 工作区文件打开均生效」同口径）：

| 落点                                              | 生效场景                                                                            | 路径写法                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------- |
| `~/develop/bizs/.vscode/`（**工作区根**） | 裸目录打开`bizs`；或打开工作区文件 `bizs.code-workspace` 的「工作区（配置）」根 | 带`bms/` 前缀；「当前文件」类用 `${file}` |
| `~/develop/bizs/bms/.vscode/`                   | 单独打开`bms` 时                                                                  | 不带前缀；用`${relativeFile}`               |

改完需 `Ctrl+Shift+P` → 「重新加载窗口」才会刷新下拉。

### 8.2 启动项清单 <a id="debug-list"></a>

| 启动项                                           | 用途                                                                                                                                                                                                                                       | 前置任务                               |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| 前端：宿主 dev（Node · Vite）                   | 调试 Vite dev server 本体（`vite.config` / 插件），起好后自动用外部浏览器打开                                                                                                                                                            | —                                     |
| 前端：宿主 + Chrome（浏览器断点）                | 宿主页面 JS / Vue 源码断点                                                                                                                                                                                                                 | `dev:宿主（5173）`                   |
| 前端：宿主 + 模块 + Chrome                       | 含运行时模块的完整宿主（前置任务确保 5002 发布存储服务在跑）                                                                                                                                                                               | `dev:宿主 + 模块产物（5002 + 5173）` |
| 前端：核对页 + Chrome（选页）                    | 开发态核对页实测（下拉选页，默认`login-check.html`）                                                                                                                                                                                     | `dev:宿主（5173）`                   |
| 前端：当前文件单测（Node · Vitest）             | 打开某个`tests/*.spec.ts` 后 F5 调试该文件                                                                                                                                                                                               | —                                     |
| 模块：demo / sample 独立开发（5002 / 5003）      | 模块自身`pnpm dev`（与宿主联调无关）                                                                                                                                                                                                     | —                                     |
| 后端：单服务（debugpy · 选服务）                | 后端单服务断点（下拉选服务；读`backend/config.toml` 的 `[server] host/port`）                                                                                                                                                          | `dev:清理后端端口（8000）`           |
| 后端：单服务（debugpy ·**bms_identity**） | 固定默认服务的等价项（免每次手选）——旧「全套」用它；换服务用上一行或改`module`；**不加载开发密钥与 loopback 别名**，本机四服务形态下请在下面两项里选                                                                             | `dev:清理后端端口（8000）`           |
| 后端：当前文件单测（debugpy · pytest）          | 打开`backend/**/tests/test_*.py` 后 F5                                                                                                                                                                                                   | —                                     |
| **后端：本地全套（四服务 · 脚本）**       | **本机裸跑四服务**（`bms/scripts/tools/dev/本地全套.sh up`；同一 8000 + loopback 别名 + 开发密钥）——「全套（本地四服务）」的后端成员（脚本起的服务是**后台进程，不带调试器**）                                             | —                                     |
| **后端：单服务（debugpy · 本机四服务）**  | **后端断点**用（下拉选服务）：经 `bms/backend/ops/dev_run.py` 注入别名 / 8000 / Redis / 开发密钥后进服务入口 ⇒ 断点、变量、调用栈齐备；**先 `本地全套.sh stop <服务>` 腾位**，调试完 `up` 补回（见 [8.5](#local-stack)） | —                                     |
| 全套：后端单服务 + 宿主 + Chrome                 | 组合项（后端 + 宿主 + 浏览器一起拉起）；后端用固定项`bms_identity`（**不再弹选择框**），前端用「宿主 + 模块」项（**自动确保 5002 在跑**）——**本地四服务形态下别用**（见 [8.5](#local-stack)）                         | —                                     |
| **全套（本地四服务 + 宿主 + Chrome）**     | **一键全套（推荐）**：脚本起四服务 + 宿主 + 模块产物 + Chrome（**前端断点即用**）                                                                                                                                              | —                                     |

浏览器断点项的 `runtimeExecutable` 必须写**绝对路径** `"/usr/bin/google-chrome"`（js-debug 只接受 `stable`/`beta` 等别名或可执行文件绝对路径，写命令名 `google-chrome` 会报「找不到浏览器」）；需改用 snap Chromium 时换成 `"/snap/bin/chromium"`，见《[google-chrome部署使用说明](google-chrome部署使用说明.md)》。

### 8.3 任务清单 <a id="debug-tasks"></a>

| 任务                                                          | 说明                                                                                                                                                                                                                      |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dev:清理宿主端口（5173）`                                  | 普通任务：跑`清理宿主端口.sh` 清理占用 5173 的**本项目**旧宿主 dev（含等待端口释放），供 dev 类后台任务作 `dependsOn` 前置                                                                                      |
| `dev:确保模块产物服务（5002）`                              | 普通任务：幂等确保 5002 发布存储服务在跑（缺则后台拉起），供「宿主 + 模块」作`dependsOn` 前置                                                                                                                           |
| `dev:宿主（5173）` / `dev:宿主 + 模块产物（5002 + 5173）` | 后台任务：命令只有`pnpm dev`，准备动作全交 `dependsOn` 前置任务（`dependsOrder: sequence`）；以 Vite 的 `Local:` 行为就绪信号（供 `preLaunchTask` 判断）                                                        |
| `dev:清理后端端口（8000）`                                  | 普通任务：清理占用 8000 的本项目旧后端调试进程，供上表两个后端启动项作`preLaunchTask`（重开「全套」不必先手工停掉上一次调试会话）；**注意它按端口清理，会把本地全套的四服务一起清掉**——起四服务请用下面两条任务 |
| `dev:后端本地全套（四服务）`                                | 普通任务：调`bms/scripts/tools/dev/本地全套.sh up`——幂等起 tenant/org/platform/identity（已在监听则跳过）+ 自愈 `/etc/hosts` 别名与 `bms/backend/.dev-keys.local` + 等健康                                        |
| `dev:后端本地全套·停（四服务）`                            | 普通任务：`本地全套.sh down`——`TERM` → 5s → `KILL`，仍不死**报错交人工**（不无限等待）；单个服务用 `本地全套.sh stop <服务>`                                                                            |
| `服务:模块产物（5002 · CORS 静态）`                        | `serve-module-releases.mjs` 托管 `bms/frontend/releases/**`（带 CORS，宿主加载运行时模块的前置）                                                                                                                      |
| `发布:模块产物（demo + sample · 构建 + 发布）`             | 构建并发布两个运行时模块到`frontend/releases/`（归档不入库）                                                                                                                                                            |
| `dev:模块 demo / sample 独立开发`                           | 模块自身 dev（demo 5002 / sample 5003，与「服务:模块产物」的 5002 互斥）                                                                                                                                                  |
| 检查：前端基座三包 / 前端宿主 / 文档基座 / 后端               | 一键跑对应门禁（lint、typecheck、用例、体积预算、文档校验、ruff+pyright）                                                                                                                                                 |

> 端口自愈由脚本 `bms/scripts/tools/dev/清理宿主端口.sh` 实现（入参为端口 + 本项目目录），判定依据是占用进程的 `cwd` 是否等于给定目录——只清理本项目旧进程，占用者为非本项目进程时**中止启动**并提示，不误杀。
>
> **准备动作一律放 `dependsOn` 前置任务，不要写进 `isBackground` 任务的 `command`**：后者的耗时（等端口释放、拉起 5002、`sleep`）会算进 background 的就绪等待窗口，触发「任务尚未退出，并且未定义 problemMatcher」提示；遇到该提示点「仍要调试」可继续跑，但正确做法是拆前置任务（本机两处 `tasks.json` 已如此）。

### 8.4 排障 <a id="debug-trouble"></a>

| 现象                                                                | 处理                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 调试下拉为空                                                        | 打开的是错误的根（见[8.1](#debug-location)）；或改配置后未「重新加载窗口」；或该 json 有语法错误（打开文件看波浪线，注释为 JSONC 允许）                                                                                                                                                                                                                                                                                        |
| 启动即报找不到任务                                                  | `preLaunchTask` 名与 `tasks.json` 的 `label` 不一致（两处文件须同步，见 [8.1](#debug-location)）                                                                                                                                                                                                                                                                                                                         |
| 浏览器断点不生效                                                    | `runtimeExecutable` 须是本机存在的可执行文件（`google-chrome` 或备用 `chromium`）；确认 Chrome 已装（[google-chrome部署使用说明](google-chrome部署使用说明.md)）                                                                                                                                                                                                                                                         |
| 后端启动项报错                                                      | 需扩展`ms-python.debugpy`（已装）；解释器 `bms/backend/.venv/bin/python` 须存在（`.venv` 外置口径见 [uv部署使用说明](uv部署使用说明.md)）                                                                                                                                                                                                                                                                                |
| 宿主页面显示「模块加载失败」                                        | 5002 上未托管发布归档：先跑「发布:模块产物」再跑「服务:模块产物（5002 · CORS 静态）」（裸静态服务缺 CORS 头会致跨源 ESM 加载失败）                                                                                                                                                                                                                                                                                           |
| 点「全套」弹「正在等待 preLaunchTask」，但服务其实已经起来          | background 就绪正则没匹配上：vite 在终端里输出的是带 ANSI 颜色码的`Local` + `ESC[22m` + `:`，字面 `Local:` 并不存在 → `endsPattern` 必须写成 `Local.*https?://`（两处 `tasks.json` 的 4 个 vite 任务已如此）                                                                                                                                                                                                   |
| 启动即报端口被占（5173 / 8000）                                     | 上一次遗留的 dev / 调试进程未退出：5173 由前置任务`dev:清理宿主端口（5173）` 自愈、8000 由 `dev:清理后端端口（8000）` 自愈；**占用者为非本项目进程时任务会中止并提示**（不误杀，需自行处理占用方）                                                                                                                                                                                                                  |
| 点「全套」弹「任务尚未退出，并且未定义 problemMatcher」             | 该 background 任务的`command` 里混了准备动作，耗时（清理等端口释放 + 拉起 5002 + `sleep`）超出就绪等待窗口：点「仍要调试」可继续；根治是把准备动作拆成 `dependsOn` 前置任务（本机两处 `tasks.json` 已如此）                                                                                                                                                                                                           |
| 页面「整体素」但登录页卡片正常                                      | 宿主外壳样式缺失——`ui-ep` 的 layout 族组件（`MainLayout` / `SideMenu` / `SideMenuItem` / `TabNavBar` / `ContentTabs` / `LayoutCard` / `PageContainer`）尚无样式实现；**非环境问题**（EP 样式、设计令牌与品牌色均正常）。已登记在阶段七计划的后续待办台账，需按《布局设计》主框架 / 导航补样式                                                                                                         |
| 后端启动项卡在「正在加载 python 扩展」                              | 装了与官方扩展**同命令 ID** 的套壳扩展（`devshub-ai.devshub-python` / `wubzbz.debugpy`）→ 官方 `ms-python.python` 激活抛 `command 'python.configureTests' already exists`；在扩展面板卸载套壳项后重载窗口（见 [7.2](#ext-dirs)）                                                                                                                                                                                |
| Python 环境工具（PET）反复超时、6 个 python 工具未注册              | `~/.codebuddycn/extensions/ms-python.python-*/python-env-tools/bin/pet` **缺执行位**（日志 `spawn … EACCES`）：`chmod +x` 该文件即可（本机 2026-10-03 已修，`pet --version` → `pet 0.1.0`）                                                                                                                                                                                                                 |
| 后端`.py` 满屏「无法解析导入 sqlalchemy」                         | 分析器没关联到项目解释器：裸目录打开时`bms/.vscode/settings.json` **不生效**，须在工作区根 `settings.json` 配 `python.defaultInterpreterPath`（`bms/backend/.venv/bin/python`）与 `python.analysis.extraPaths`（`bms/backend`）                                                                                                                                                                             |
| `alembic/versions/**` 满屏类型报错（如 `Column` 泛型缺参数）    | 该目录**本就不在门禁范围**（`bms/backend/pyproject.toml` 的 `[tool.pyright] include` 只含 `libs`/`services`），是 IDE 侧 `basedpyright` 默认 `recommended` 档在报：已在项目 `[tool.pyright]` 加 `ignore = ["alembic"]`，并让 `basedpyright.analysis.configFilePath` 指向该 `pyproject.toml`（IDE 与门禁同口径；`uv run pyright --outputjson` 实测 `filesAnalyzed=916` / 0 错，2026-10-04 复核） |
| 本地登录**恒 401**，但四服务 `/healthz`、`/readyz` 都 200 | 本地库里**没有可用账号**（多为 `本地全套.sh up --reset-db` 重建库后未建号——现象易误判为「登录链路不通」）：跑 `bash scripts/tools/dev/本地全套.sh seed`（租户 + 菜单 + 建号 `admin`），或 `ops.seed_user` 指定 `--username/--password`（见 [8.5](#local-stack)）                                                                                                                                             |
| 点了「全套」后登录反而不通、先前跑着的后端被杀                      | 用的是旧「全套：后端单服务 + 宿主 + Chrome」：其前置任务`清理后端端口（8000）` 按端口清理，会把本地全套的**四服务全部清掉**，且只起 `bms_identity` 一个（无密钥 / 无别名）→ 本地开发改用「全套（本地四服务 + 宿主 + Chrome）」（见 [8.5](#local-stack)）                                                                                                                                                            |

| 登录报 `20002`「**账号或密码错误**」                                          | 服务端与账号状态正常时多为**口令不对**：口令**以《[本地资源](../../用户文档/本地资源.md)》「BMS 应用账号」节的当前登记为准**（**历史对话 / 旧文档里出现过的口令一律视为已失效**——口令轮换后旧值即不可用；凭据只登记在该节，见《AI开发规范》）；另注意浏览器**自动填充**了旧口令（点密码框清空后重输）。连续失败 5 次会触发锁号（见下一行） |
| 登录报 `20003`「**账号已锁定，请联系管理员或稍后重试**」                      | 触发登录防爆破：**连续 5 次失败锁 15 分钟**（`[security].login.max_failures` / `lock_seconds`；失败计数在 Redis、锁定时间记 `sys_user.locked_until`）。多为**拿真账号反复试错口令**所致（**验验证码请改用不存在的账号试错口令**）：当场解锁跑 `bash scripts/tools/dev/本地全套.sh unlock`（清 `failed_count` / `locked_until` + 删 Redis 计数键），或等锁定到期 |

| ESLint 扩展报 `Parsing error: No tsconfigRootDir was set, and multiple candidate TSConfigRootDirs are present`（打开 `frontend/{modules,packages,apps}/*` 下文件时） | monorepo 里**每个包各一份 `eslint.config.js`**（宿主 / 组件库 / 运行时模块），而扩展**未指定工作目录** ⇒ 默认启发式把 `apps/desktop` 的配置套到别的包的文件上，解析器看到**多个候选 tsconfig 根**即报错（**与文件内容无关**：`startLineNumber=1` 空范围 = 解析期；`pnpm --filter <包> lint` 本身是通过的）。**修法（已落地）**：① 两处 `.vscode/settings.json` 加 `eslint.useFlatConfig` / `eslint.workingDirectories: [{ "mode": "auto" }]`（按文件就近取配置）/ `eslint.validate`；② 各包 `eslint.config.js` 加 `parserOptions.tsconfigRootDir: import.meta.dirname` 锚定自身（双保险）。**改完需「Developer: Reload Window」重载才生效** |

### 8.5 本机裸跑后端「全套」（本地开发主形态） <a id="local-stack"></a>

**口径**：开发态**一律本机裸跑**——`bms/backend/config.dev.toml` 本就是 SQLite 本地库 + 内存缓存 + 字典/参数走 SQL，**不需要 Docker，也不需要在 mjbk（开发服务器）上部署**；容器 / 开发服务器**只在发布时**用于发布验证。四个服务各绑一个 loopback 别名并**共用 8000 端口**，与服务间基址模板 `http://{service}:8000` 同形（故服务间调用、网关内路径与容器形态一致）。

| 项       | 取值 / 做法                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 脚本     | `bms/scripts/tools/dev/本地全套.sh`（子命令 `up` / `down` / `stop <服务…>` / `status` / `seed` / `env` / `logs` / `unlock [账号]`）   |
| 别名     | `127.0.0.2 tenant`、`127.0.0.3 org`、`127.0.0.4 platform`、`127.0.0.5 identity`（`up` 自愈写入 `/etc/hosts`，sudo 免密） |
| 开发密钥 | `bms/backend/.dev-keys.local`（`up` 缺则用 `joserfc` 生成：`usr-` 用户令牌 + `svc-` 服务令牌两组；不入库）                 |
| Redis    | 缺省`redis://192.168.0.107:6379/5`（本机无 Redis，指向开发机 DB5 隔离；`BMS_LOCAL_REDIS` 或 `--redis` 覆盖）                   |
| 前端映射 | `bms/frontend/apps/desktop/.env.local` 的 `VITE_LOCAL_API`（`本地全套.sh env` 写入；未列出的服务仍走远端网关）                 |
| 账号     | `ops/seed_user.py` 建号（缺省账号 `admin`，口令随机生成并仅打印一次）——**首次起栈后必须跑一次 `seed`**，否则本地库无账号、登录恒 401；账号 / 口令**只登记在《[本地资源](../../用户文档/本地资源.md)》（gitignore，凭据不入库）**     |
| 库重建   | `本地全套.sh up --reset-db`（先把 `bms/backend/bms_*.db` 备份移走，服务按当前表结构重建；**重建后须重新 `seed`**）       |

常用流程：

```bash
cd ~/develop/bizs/bms
bash scripts/tools/dev/本地全套.sh up              # 起四服务（幂等：已在跑则跳过；等健康）
bash scripts/tools/dev/本地全套.sh seed            # 租户注册库 + 菜单元数据 + 建号 admin（幂等）
bash scripts/tools/dev/本地全套.sh status          # 进程与 /healthz、/readyz 一览
bash scripts/tools/dev/本地全套.sh stop identity   # 只停一个（供后端断点腾位）
bash scripts/tools/dev/本地全套.sh unlock          # 解锁账号（清失败计数 / 锁定时间 + Redis 计数键）
bash scripts/tools/dev/本地全套.sh down            # 停全部：TERM → 5s → KILL；仍不死则报错交人工
```

**断点口径**（脚本起的服务是 `nohup` 后台进程，**不带调试器**）：

| 目标                                   | 做法                                                                                                                                                                                                                                                                                                                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 前端（Vue / TS）                       | 用「全套（本地四服务 + 宿主 + Chrome）」里的 Chrome 调试会话，或单项「前端：宿主 + 模块 + Chrome（浏览器断点）」——**断点直接可用**                                                                                                                                                                                                                                                        |
| 后端（Python）                         | ①`本地全套.sh stop <服务>` 腾出该服务；② 启动「后端：单服务（debugpy · 本机四服务）」——`bms/backend/ops/dev_run.py` 在**导入服务前**注入 `BMS_SERVER__HOST=<别名>` / `PORT=8000` / `BMS_REDIS__URL` 与开发密钥，再 `runpy` 进服务入口 ⇒ 断点 / 变量 / 调用栈与 `python -m bms_<服务>` 一致（`justMyCode: false` 可步入框架与基座）；③ 调试完 `本地全套.sh up` 补回 |
| 旧「全套：后端单服务 + 宿主 + Chrome」 | **本地四服务形态下别用**：它只起 `bms_identity` 一个、不加载密钥与别名，且前置任务 `清理后端端口（8000）` 会把四服务**全部清掉**（该口径已就地标注在两处 `launch.json`）                                                                                                                                                                                                        |

> 运维细节：脚本的 pid 记录的是**真服务进程**（不是 bash 包装进程），停服务时连带 `TERM`/`KILL` 其子进程；起服务阶段若进程退出会**立刻报错并打印日志尾部**，不会把健康等待超时耗满；诊断入口 `本地全套.sh logs [服务]`（日志在 `/tmp/bms-local-stack/`）。

## 9. 常用设置与排障 <a id="trouble"></a>

### 9.1 常用设置 <a id="settings"></a>

| 设置项                                                        | 说明                                                                                                                                                                                   |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `codingcopilot.submitMessageShortcut`                       | 发送快捷键：`Enter`（发送=Enter，换行=Ctrl/Cmd+Enter）或 `CtrlOrCmdAndEnter`                                                                                                       |
| `codingcopilot.enableAutoCompletions`                       | 自动触发代码补全（回车、停顿触发）；关闭后可用快捷键手动触发                                                                                                                           |
| `codingcopilot.enableCraftCodeBase`                         | Craft 模式启用代码库检索                                                                                                                                                               |
| `codingcopilot.enableInlineChat` / `toolbarOnSelection`   | 内联聊天与选中悬浮工具栏                                                                                                                                                               |
| `codingcopilot.enableNextEditSuggestions`                   | 下一处编辑预测                                                                                                                                                                         |
| `codingcopilot.enabledWebSearch`                            | 联网搜索总开关                                                                                                                                                                         |
| `codingcopilot.HttpProxyMode` / `codingcopilot.HTTPProxy` | 网络代理：`system`（跟随系统）/ `manual`（手动，仅手动模式读 `HTTPProxy`）                                                                                                       |
| `codingcopilot.disableBuiltInMarketplace`                   | 无法访问内置插件市场（`download.codebuddy.cn`）时开启，**跳过市场安装与定期更新检查**，避免对话请求被反复的市场拉取超时阻塞；等效于设置环境变量 `CODEBUDDY_SKIP_BUILTIN_...` |
| `codingcopilot.autoUpdateThirdPartyMarketplaces`            | 每天检查一次第三方（Git 类型）插件市场并后台静默更新（默认关）                                                                                                                         |
| `codingcopilot.enableModelOptimization`                     | 允许使用对话数据做模型优化（默认关，按需开启）                                                                                                                                         |

### 9.2 排障入口 <a id="trouble-entry"></a>

| 现象                                          | 处理                                                                                                                                                                               |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 对话卡住/反复超时（市场拉取阻塞）             | 开启`codingcopilot.disableBuiltInMarketplace`（或设等效环境变量）后重载窗口                                                                                                      |
| 界面白屏/花屏等渲染异常                       | 在`~/.codebuddycn/argv.json` 打开 `"disable-hardware-acceleration": true`，重启 IDE（本机当前未启用）                                                                          |
| 命令被拦截或反复确认                          | 检查`codingcopilot.customBlacklistCommands`（命中正则会拦截）与 `codingcopilot.autoRunMode` 取值                                                                               |
| 改了`disabledSecurityCategories` 仍在弹确认 | 见[6.3](#permission-security)：权威存储在 `state.vscdb` → `CodeBuddy.settings.autoApprovalSettings`，需完全退出后改并**冷启动**；重载窗口与手改 `settings.json` 均无效 |
| 删除的文件想找回                              | `safeDeleteEnabled` 默认开启时删除先进回收站；关闭后为永久删除                                                                                                                   |
| 需要看运行日志                                | 对话/扩展日志`~/.local/share/CodeBuddyExtension/Logs/CodeBuddyIDE/<日期>/<工作区>__<hash>.log`；IDE 日志 `~/.config/CodeBuddy CN/logs/<时间戳>/`                               |
| 崩溃排查                                      | `~/.config/CodeBuddy CN/CrashReport/`（崩溃转储）与 `~/.codebuddy/diagnostics/`                                                                                                |
| 网络代理问题                                  | 核对`HttpProxyMode`（系统/手动）与 `HTTPProxy`；与系统代理设置保持一致                                                                                                         |
| Playwright MCP 调不到工具（无`mcp__playwright__*`） | 工具列表是**会话启动快照**：登记或改配置后需**重启 IDE**或刷新 MCP 面板；面板内该 server 为 running 即已拉起（见[10.6](#workspace-ai-browser)） |
| MCP / CLI `snapshot` 落盘 `.playwright-*/*.yml` 恒 0 字节 | 二者同源缺陷：取结构改用 **`browser_snapshot` / `browser_find`**（a11y 树内联返回，含`[ref=eNN]`），或 CLI 侧 `eval` 读 DOM（见[10.6](#workspace-ai-browser)） |

## 10. 工作区级 `.codebuddy/` 与 AI 协作口径 <a id="workspace-ai"></a>

第 4 节记的是**用户级**四个数据目录；CodeBuddy 还会在**工作区根**读写 `.codebuddy/`（本机工作区根为 `~/develop/bizs/`，其下 `bms/` 为 bms 仓库），用于**跨会话工作记忆**与协作产物。

### 10.1 目录现状与入库口径 <a id="workspace-ai-dirs"></a>

| 路径（相对工作区根）       | 现状（2026-10-04 核实）                                                                                         | 作用                                            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `.codebuddy/memory/`     | **存在**：20 个文件 = 日报 `YYYY-MM-DD.md`（2026-09-13 起）+ 长期记忆 `MEMORY.md` + `技术坑清单.md` | 跨会话工作记忆（见[10.2](#workspace-ai-memory)） |
| `.codebuddy/teams/`      | 本机**未创建**（启用团队协作时由工具生成 `<团队名>/`，含各成员历史）                                    | 多代理协作                                      |
| `.codebuddy/` 其余生成物 | 按需生成                                                                                                        | 技能 / 自动化等                                 |

入库口径：工作区根仓库的 `.gitignore` 是 `/*` + 白名单（`!/.gitignore`、`!/.opencode/`、`!/.vscode/`、`!/AGENTS.md`、`!/README.md`、`!/LICENSE`、`!/scripts/`、`!/*.code-workspace`），**`.codebuddy/` 不在白名单 → 工作记忆不入库**（与 `用户文档/本地资源.md`、`deploy/.env` 同属本机私有数据；公开文档红线见《[AI开发规范](../../规范/AI开发规范.md)》「资料与资源」节）。`bms/` 下**无** `.codebuddy/`。

### 10.2 工作记忆三件套的读写口径 <a id="workspace-ai-memory"></a>

| 文件                         | 写入口径                                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 日报`memory/YYYY-MM-DD.md` | 当日**追加**（replace 而非整文件覆盖）：任务级过程、本轮拍板与探查结论；不写中间检索结果等临时信息                        |
| `memory/MEMORY.md`         | **原地更新**并保持精简：只留协作口径 / 架构铁律 / 仓库与命令 / 文档硬约束 / 进度 / 踩坑索引；**能指向文档的不复述** |
| `memory/技术坑清单.md`     | 踩坑细节**只增不改口径**：新坑先落日报、再并入本文件（`MEMORY.md` 只留索引）                                            |

补充纪律：

- **会话开场**：先读 `MEMORY.md` + 当日 / 前一日日报（可能涉及既有决策与偏好时）；**会话结束**：完成实质工作后立即追加日报，口径类事实进 `MEMORY.md`。
- **记忆不是交付物**：不得以「已写入记忆」替代设计 / 代码 / 记录 / 计划等交付物；用户要的结论仍须落到对应文档或回复正文。
- **冲突处理**：日报追加更正条；`MEMORY.md` 原地改并注明原因与日期；30 天以上日报按主题蒸馏进 `MEMORY.md` 后删除。

### 10.3 单任务交付「一条龙」（引自《[AI开发规范](../../规范/AI开发规范.md)》「单任务交付『一条龙』」节） <a id="workspace-ai-chain"></a>

链条：上下文 → 决策确认 → 详细设计 → 实施 → 测试 → 验证 → 登记回写 → 记录 → 提交 → 处理偏差与遗留 → 收尾。要点：

- **先设计后编码**；详细设计中的待拍板事项**逐项确认**（推荐项在前、附差异说明），设计定稿即提交并自动续行后续各步；
- **随时可停**：凡遇不清楚或需用户拍板之处即停下确认，不以推荐值 / 默认值擅自越过；
- **编号对齐**：Kiwi 用例**先在平台登记取得编号**，再回填代码标注与任务记录（既有编号不复用、不改派）；
- **提交与推送**：链内各次提交（设计 / 代码 / 文档 / 偏差遗留闭环）自动执行；**仅推送远程需两级独立确认**——说「提交」只做 commit、说「推送」才 push；
- **闭环才算完成**：偏差与遗留未登记去向、下游消费方未标注，不算任务完成。

> 会话提示词可对该口径加**临时约束**（本机出现过「本轮不提交 git，除非明确要求」这类会话级纪律）——**以会话提示词为准**。

### 10.4 核心模块的 AI 交叉评审（引自《[代码评审规范](../../规范/代码评审规范.md)》《[Git协作规范](../../规范/Git协作规范.md)》「分支模型」节） <a id="workspace-ai-review"></a>

- 单人开发期以 **AI 交叉评审**替代人工指派：核心模块（认证、RBAC、工作流、审计、收付款）改动**提交前**由 AI 按《代码评审规范》「通用评审清单」「后端重点」「前端重点」「数据库变更重点」节逐项核对，**评审结论随提交说明或任务记录留痕**；
- 多人协作期恢复人工评审与 MR 流程（当前不启用分支与 MR 流转）。
- 外部服务类操作（Kiwi 登记、服务部署重建、备份恢复、数据库、远程开关机等）**先读 `bms文档/资料/开发服务器/` 下对应说明再动手**（《AI开发规范》「资料与资源」节）。

### 10.5 常用门禁命令（本机口径） <a id="workspace-ai-gates"></a>

```bash
# 文档基座（bms 仓根）
python3 scripts/tools/base-check/check-base.py
python3 scripts/tools/base-check/check-links.py
python3 scripts/tools/base-check/check-docs-scope.py
python3 scripts/tools/check-docs/check-status.py --stage <阶段> --strict
python3 scripts/tools/preflight/check-preflight.py --fast        # 推送前快速预检（不跑全量）

# 后端（bms/backend 下，uv run；只跑受变更影响的定向用例）
uv run pytest -q ; uv run ruff check . ; uv run ruff format --check . ; uv run pyright

# 前端（bms 工作区根下；apps/desktop 与 modules/* 需 --filter 单独跑）
pnpm --filter @bms/desktop run test ; pnpm --filter @bms/desktop run lint
pnpm --filter @bms/desktop exec vue-tsc -b ; pnpm run api-types:gen:check
```

> [8.3](#debug-tasks) 的「检查：前端基座三包 / 前端宿主 / 文档基座 / 后端」四个任务即上述门禁的一键入口；口径细则归《[测试规范](../../规范/测试规范.md)》与各工程说明，本节只作速查。

### 10.6 浏览器真机验证：Playwright MCP（与 playwright-cli 对比） <a id="workspace-ai-browser"></a>

开发态**真实浏览器核验**本机有两条链路，都能导航 / 点击 / 填表 / 截图 / 读控制台：**Playwright MCP**（`mcp__playwright__*`，本节登记）与 **`playwright-cli` skill**（CLI 侧口径见《[playwright部署使用说明](playwright部署使用说明.md)》，系统 Chrome 见《[google-chrome部署使用说明](google-chrome部署使用说明.md)》）。

**登记**（用户级 `~/.codebuddy/mcp.json`）：

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

| 参数 | 作用 |
| --- | --- |
| `@playwright/mcp@<版本>` | 走 `npx` 拉取（`env` 指 npmmirror 国内镜像）；其内置 playwright-core 决定内核支持 |
| `--browser chrome` | 复用**系统 Google Chrome**，免下载 Chromium（本机 `~/.cache/ms-playwright` 仅有 firefox） |
| `--isolated` | 隔离会话（不写用户 profile，每次全新上下文） |

> 生效：MCP 工具的可见列表是**会话启动快照**——登记或改配置后须**重启 IDE**（或刷新 MCP 面板）方可调用；面板内该 server 显示 running 即已拉起（浏览器**惰性启动**，首次调用工具才开窗口）。实测 `tools/list` 25 个工具，`browser_navigate` 可拉起有头系统 Chrome 并导航。

**真机走查模板**（以本地全套 + 宿主 dev 为例）：

```bash
cd ~/develop/bizs/bms
bash scripts/tools/dev/本地全套.sh up                                              # 起本地四服务（见 8.5）
bash scripts/tools/dev/本地全套.sh seed --username admin --password '<口令>' --reset-password   # 建 / 重置账号（口令只落《本地资源》）
cd frontend && pnpm --config.verify-deps-before-run=false --filter @bms/desktop dev             # 起宿主 dev（:5173，无 TTY 须加该参数）
```

随后用 MCP 工具逐步走查：`browser_navigate` 打开 `/login` → `browser_fill_form` 填账号口令 → `browser_click` 提交 → `browser_snapshot` 读结构 / `browser_take_screenshot` 取证。常用工具：`browser_navigate` / `browser_click` / `browser_type` / `browser_fill_form` / `browser_snapshot` / `browser_find` / `browser_console_messages` / `browser_take_screenshot` / `browser_wait_for`。

口径与注意：

- **读页面结构用 `browser_snapshot` / `browser_find`**，二者把 a11y 树**内联返回**（含 `[ref=eNN]`），可直接据此 click / fill；**不要**指望 `.playwright-mcp/page-*.yml`——`browser_navigate` 触发的该文件恒 **0 字节**（与 `playwright-cli snapshot` 同源缺陷），`browser_click` 触发的才有内容；ref 前缀会随导航变化（如首次 `e..`、后续 `f1e..`）。
- **截图落盘**：`browser_take_screenshot` 的 `filename` 相对**工作区根**解析；截图以**文件**落盘、工具只回路径，**不占模型图片额度**。
- **控制台**：`browser_console_messages --level error --all`；本地开发态允许的预期错误仅 `favicon.ico` 404、模块宿主（:5002）`remoteEntry.js` `ERR_CONNECTION_REFUSED`、未登录态 `auth/refresh` 401，其余均按缺陷看。
- 走查产物与截图放工作区 `tmp/` 下（**不入库**）。

**与 `playwright-cli` 的选型（长会话口径）**：

| 维度 | 谁快 / 谁省 | 原因 |
| --- | --- | --- |
| 速度（来回次数） | **MCP 快** | MCP 每步 1 次调用（`browser_snapshot` 直接给可点 `ref`）；CLI 每步要 2~4 次子进程调用（open → eval 读 DOM → run-code 点 → screenshot），且每次都新起进程 |
| 单次载荷 | **CLI 省** | CLI `eval` 读 `innerText` 实测约 0.3 KB；MCP a11y 树 1~4 KB（约 3~10 倍，含 role / ref / 属性 / 嵌套） |
| 固定开销 | 基本相当 | MCP 工具 schema 一次拉取约 3.2 K；CLI 加载 `SKILL.md` 约 2.5 K，均一次性 |
| **长会话总消耗** | **MCP 省** | 对话每轮整体重发历史上下文 ⇒ 总消耗主导项是「累计上下文 × 来回次数」；MCP 来回更少，CLI 每步的多次来回被反复重发 |

结论：**长会话首选 MCP**（又快又省）；`playwright-cli` 仅在 1~2 步的极短会话或只看单次输出时可能更省。若在意消耗，长会话内用 `browser_find`（只回命中片段）替代整页 `browser_snapshot`。

## 11. 检查清单 <a id="checklist"></a>

- □ 版本已核实：包 `codebuddy-cn` 与应用版本分别取自 `dpkg -l` 与 `product.json`
- □ 明确无 apt 源 → 升级靠手工 `.deb` 覆盖安装，卸载不删用户数据
- □ 四个用户数据目录职责清晰（IDE 设置 / 扩展宿主 / AI 配置 / 日志），清理只动缓存目录
- □ 权限设置全部落在 `~/.config/CodeBuddy CN/User/settings.json`（`codingcopilot.*`），改动前有带时间戳备份
- □ 免确认取值明确：`autoRunMode=runEverything` + `autoRun/autoModifyFile=true`，回收站与批量删除阈值兜底保留
- □ 首配项齐备：语言 `zh-cn`、崩溃上报关闭、插件与技能市场、MCP 登记位、补全模型与提交信息风格
- □ 扩展管理口径明确：扩展目录 `~/.codebuddycn/extensions`、市场 open-vsx、安装用应用自带 CLI（全路径 `--install-extension`），与 `~/.vscode/extensions` 区分开
- □ 文档预览口径明确：html 双击走内置 HTML 预览（`codebuddy.html.previewEditor`）、需要相对引用/实时刷新用 Live Preview、`file://` 不可用改走 http 静态服务；md mermaid 需 `bierner.markdown-mermaid`
- □ 运行与调试链路口径明确：dev 类后台任务经 `dependsOn` 前置自愈 5173 与确保 5002、后端 8000 经 `preLaunchTask` 自愈（脚本按 `cwd` 判定归属，非本项目占用则中止）；**准备动作不写进 background 任务的 command**；就绪正则容忍 ANSI（`Local.*https?://`）；Chrome 断点用绝对路径；「全套」用固定后端项 + 含模块的前端项
- □ Python 侧口径明确：官方 Python 扩展三件（无同命令 ID 的套壳项）、`pet` 有执行位、解释器在**工作区根** `settings.json` 声明、alembic 已由 `[tool.pyright] ignore` 排除
- □ 排障入口齐备：日志三处、崩溃转储、市场超时与渲染异常的处置办法
- □ 工作区级 `.codebuddy/` 口径清晰：工作记忆三件套职责分明（日报追加 / `MEMORY.md` 原地精简 / 技术坑清单只增）、**不入库**；记忆不得替代交付物；「一条龙」与 AI 交叉评审口径以《AI开发规范》《代码评审规范》为准（见[第 10 节](#workspace-ai)）
- □ 浏览器真机验证口径明确：Playwright MCP 登记于 `~/.codebuddy/mcp.json`（系统 Chrome + `--isolated`）、生效需重启 IDE；结构读 `browser_snapshot` / `browser_find`（`.playwright-mcp/*.yml` 不可依赖）、控制台只认预期错误；长会话首选 MCP（见[10.6](#workspace-ai-browser)）
- □ 本机事实均经核实（2026-09-12 首次核实；数量类事实 2026-10-04 复核；2026-10-10 补浏览器真机验证），未写入账号/令牌等凭据

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》《[opencode部署使用说明](opencode部署使用说明.md)》《[命名规范](../../规范/命名规范.md)》配套 · 记录 2026-09-12 部署核实、2026-09-13 免确认排障、2026-10-03 运行与调试启动项与扩展补齐、2026-10-03「全套」启动链路排障（端口自愈与前置任务拆分 / ANSI 就绪正则 / Python 扩展与解释器 / pyright 口径 / PET 权限 / Chrome 绝对路径 / 含模块的前端项）、2026-10-04 数量类事实同步（原型与布局 HTML 200 个 / `pyright --outputjson` `filesAnalyzed=916`）与新增[第 10 节](#workspace-ai)（工作区级 `.codebuddy/`：工作记忆三件套 + 「一条龙」/ AI 交叉评审 / 门禁速查）、2026-10-10 新增 [10.6](#workspace-ai-browser)（Playwright MCP 登记、浏览器真机走查用法与 playwright-cli 选型对比）（mjpc 本机）
