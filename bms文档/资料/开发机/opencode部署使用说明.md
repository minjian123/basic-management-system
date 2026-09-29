# opencode 部署使用说明

> mjpc 开发机 opencode（命令行 CLI + 桌面端 desktop）部署与验证实录 · 初版 2026-08-29，现行版本 v2（2026-09-29 完成 v1 → v2 迁移）

[文档首页](../../文档首页.md) › 资料 › 开发机 › opencode 部署使用说明　|　[同级参照：中文输入法部署使用说明 →](中文输入法部署使用说明.md)　[Steamcommunity_302部署使用说明 →](Steamcommunity_302部署使用说明.md)　[防火墙部署使用说明 →](防火墙部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS，GNOME，Wayland，NVIDIA RTX 4090）上 **opencode v2** 的部署、配置与使用：

- **opencode CLI**（命令行版）：官方二进制，装于 `~/.opencode/bin/opencode`，当前 **2.0.16**；
- **opencode desktop**（桌面图形端）：官方 `.deb`，apt 安装到 `/opt/OpenCode/`，当前 **2.0.16**；
- **配置**：全局 `~/.config/opencode/opencode.jsonc` 与各项目配置**已全部迁移为 v2 原生格式**（[第 6 节](#config)）。

v1 时期的 snap 部署方式、NVIDIA/Wayland 下 GPU 崩溃的排查结论与 `--disable-gpu` 规避方案属**历史备查**，保留在[第 2.3 节](#history-v1)与[第 8.2 节](#gpu-history)，遇同类现象可直接照做。

## 2. 现状与沿革 <a id="status"></a>

### 2.1 现状速览 <a id="status-now"></a>

| 实体 | 版本 | 安装位置 | 启动方式 |
| --- | --- | --- | --- |
| CLI | 2.0.16 | `~/.opencode/bin/opencode`（同目录 `opencode2` 为兼容别名 shim） | 终端执行 `opencode` |
| 桌面端 | 2.0.16 | `/opt/OpenCode/`（apt 包名 `opencode`） | 应用菜单 **OpenCode**；或命令行 `/usr/bin/ai.opencode.desktop` |

两者**升级通道独立、版本号可不一致**：CLI 用 `opencode upgrade` 自更新，桌面端由包内自更新器检查下载（`~/.cache/@opencodedesktop-updater`）。

> 2026-09-29 迁移当日桌面端自更新器已检到官方 **2.0.18** 并触发下载，即桌面端会自行跟进小版本；CLI 需手动 `opencode upgrade` 或不定期重下二进制。

### 2.2 v1 → v2 迁移过程（2026-09-29） <a id="migration"></a>

v2 是一次重写（服务端 API 重做、运行时换 Node、插件 API 不兼容），官方迁移文档明确要求**先移除包管理器安装的 v1，再安装 v2**；v1 与 v2 使用同一个 `opencode` 命令、同一套配置位置，不能并存。本次迁移的实际动作：

| 步骤 | 动作 |
| --- | --- |
| 1 | 删除 v1 CLI 二进制 `~/.opencode/bin/opencode`（1.18.32） |
| 2 | `sudo snap remove opencode`——一次移除 snap 版 CLI **与**其中的 `opencode+desktop` 桌面组件（snapd 2.76 无 `remove-component` 子命令，桌面组件无法单独卸） |
| 3 | 删除 v1 会话数据：`~/.local/share/opencode/` 下 `opencode.db`（约 2.2GB）、`storage/`、`snapshot/`、`tool-output/`、`log/`；**保留** `auth.json`（旧凭据文件，可查 key） |
| 4 | 删除 v1 桌面用户数据 `~/.config/ai.opencode.desktop/`（与 v2 桌面同 appId，避免旧窗口/工作区/崩溃状态带入） |
| 5 | 删除 v1 插件依赖残留 `~/.config/opencode/` 下的 `node_modules/`、`package.json`、`package-lock.json`；**保留** `opencode.jsonc` 与 `skills/` |
| 6 | 安装 v2 CLI 2.0.16（官方二进制）；安装 v2 桌面端 `.deb` 2.0.16（apt） |
| 7 | 8 份配置全部改写为 v2 原生格式（[第 6 节](#config)） |

`~/.bashrc` 中 `~/.opencode/bin` 的 PATH 段**保留**——v2 官方安装脚本同样使用该目录，无需改动。

### 2.3 v1 时期的部署沿革（历史备查） <a id="history-v1"></a>

- v1 桌面端曾长期使用 **snap 版**（1.18.x，classic + `desktop` 组件），历史上一度改用官方 `.deb` 以自行控制启动参数，后回退 snap；
- v1 CLI 与桌面端是**两个独立二进制**：snap 版同时提供 CLI 与桌面端，而 `.deb` 版只装桌面端（`/opt/OpenCode/`），故当时 CLI 单独用官方二进制装到 `~/.opencode/bin`；
- v1 全局配置的 provider 用 `npm: "@ai-sdk/openai-compatible"` 运行时，凭据存 `~/.local/share/opencode/auth.json` 并通过 `/connect` 录入；
- v1 插件 API 与 v2 **完全不兼容**，v1 插件实现（如工作区 `.opencode/plugins/*.js`）不会在 v2 中运行。

> 2026-09-18 的记忆插件 `opencode-mem` 故障处置（登记后桌面端无法会话、当日卸载）属 v1 时期事件，其排除思路（先移除 `plugin` 登记、清插件缓存、完全重启）对 v2 的 v2 版插件同样适用。

## 3. 技术环境 <a id="environment"></a>

| 项 | 取值 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS（resolute），x86_64 |
| 桌面 | GNOME（`XDG_SESSION_TYPE=wayland`） |
| 显卡 | NVIDIA GeForce RTX 4090（AD102），驱动 595.91.07 |
| opencode CLI | 2.0.16（官方 `opencode-linux-x64.tar.gz` 二进制） |
| opencode 桌面端 | 2.0.16（官方 `opencode-desktop-linux-amd64.deb`，apt 包 `opencode`） |
| 全局配置 | `~/.config/opencode/opencode.jsonc`（v2 原生格式） |
| 数据目录 | `~/.local/share/opencode/`（`opencode.db` 为凭据与会话的唯一存储） |
| 后台服务 | `opencode serve --service`（v2 共享后台服务，各客户端共用，随用随起） |

## 4. 命令行 CLI 部署 <a id="cli"></a>

### 4.1 安装与升级 <a id="cli-install"></a>

v2 官方分发渠道为 `~/.opencode/bin/opencode`，与 v1 路径一致（原地替换）。本机采用官方二进制直接安装：

```bash
# 1) 下载 Linux x64（glibc 标准版）二进制包；慢时可换用官方安装脚本
curl -fL --retry 5 --retry-delay 3 -o /tmp/opencode-linux-x64.tar.gz \
  "https://opencode.ai/files/bin/2.0.16/opencode-linux-x64.tar.gz"

# 2) 解压（包内为单个名为 opencode 的可执行文件）
mkdir -p /tmp/oc_extract && tar -xzf /tmp/opencode-linux-x64.tar.gz -C /tmp/oc_extract

# 3) 安装到官方路径
install -Dm755 /tmp/oc_extract/opencode ~/.opencode/bin/opencode

# 4) 生成 opencode2 兼容别名（官方安装脚本亦会创建，指向同一个二进制）
printf '#!/bin/sh\nexec "$(dirname "$0")/opencode" "$@"\n' > ~/.opencode/bin/opencode2
chmod 755 ~/.opencode/bin/opencode2
```

升级与卸载：

```bash
opencode upgrade                    # 升到最新版（或 opencode upgrade <版本号>）
opencode uninstall --dry-run        # 预览将要删除的文件与安装
opencode uninstall --keep-config --keep-data   # 保留配置与会话数据卸载
```

> 官方安装脚本 `curl -fsSL https://opencode.ai/v2/install | bash` 与上述步骤等价，并会自行维护 PATH 段与 `opencode2` 别名。脚本按当前网络状况选择下载路径，网络不佳时逐段下载可能较慢，可直接用上面第 1 步替换。

### 4.2 PATH 与验证 <a id="cli-verify"></a>

`~/.bashrc` 追加段（迁移前后均保留）：

```bash
# opencode CLI (opencode/bin)
if [ -d "$HOME/.opencode/bin" ]; then
  export PATH="$HOME/.opencode/bin:$PATH"
fi
```

```bash
which opencode            # /home/minjian/.opencode/bin/opencode
opencode --version        # opencode v2.0.16
opencode debug paths      # 打印 home/data/cache/config/state/db 等路径
script -qec "opencode models" /dev/null   # 列出可用模型（需交互终端，见 8.3）
```

> `opencode models` 在管道/非交互环境下**无输出**（命令要求可交互终端），排障时用真实终端或 `script -qec` 包一层。

## 5. 桌面端部署 <a id="desktop"></a>

### 5.1 安装 <a id="desktop-install"></a>

官方 Linux 桌面端提供 `.deb` / `.rpm` / AppImage；本机用 `.deb` 经 apt 安装（apt 自动补齐依赖，无需手动 `dpkg -i`）：

```bash
curl -fL --retry 5 --retry-delay 3 -o /tmp/opencode-desktop-linux-amd64.deb \
  "https://opencode.ai/files/bin/2.0.16/opencode-desktop-linux-amd64.deb"

sudo apt-get install -y /tmp/opencode-desktop-linux-amd64.deb
```

安装结果与验证：

```bash
dpkg -s opencode | grep -E '^(Package|Status|Version):'   # install ok installed / 2.0.16
ls -l /usr/bin/ai.opencode.desktop                        # → /etc/alternatives → /opt/OpenCode/ai.opencode.desktop
```

- 程序目录 `/opt/OpenCode/`，可执行文件 `ai.opencode.desktop`（Electron）；
- 桌面项 `/usr/share/applications/ai.opencode.desktop.desktop`（菜单可见）与 `opencode-desktop.desktop`（`NoDisplay=true`）；
- 应用菜单条目名为 **OpenCode**，启动不需要任何附加开关。

### 5.2 启动确认与自更新 <a id="desktop-verify"></a>

正常姿态（启动日志目录 `~/.config/ai.opencode.desktop/logs/<时间戳>/`）：

```bash
D=$(ls -td ~/.config/ai.opencode.desktop/logs/*/ | head -1)
grep -E "main window visible|background service ready" "$D/main.log"
```

本次验证实测（2026-09-29）：

| 证据 | 取值 |
| --- | --- |
| `main.log` | `main window visible`（窗口已绘制） |
| `main.log` | `v2 CLI background service ready { version: '2.0.16', url: 'http://127.0.0.1:49374' }` |
| `utility.log` | 无 `exit_code=139` / `GPU process exited`（GPU 进程正常） |
| 自更新器 | 检到官方 2.0.18 并开始下载（缓存目录 `~/.cache/@opencodedesktop-updater`） |

> 启动时仍会打印一条 `'--ozone-platform=wayland' is not compatible with Vulkan` 警告，属历史已知的无害告警（GPU 进程未崩溃即正常），无需处理；仅当出现[第 8.2 节](#gpu-history)所述的 GPU 崩溃时才需要 `--disable-gpu`。

## 6. 配置（v2 原生格式） <a id="config"></a>

### 6.1 配置落点 <a id="config-paths"></a>

| 层级 | 路径 | 作用 |
| --- | --- | --- |
| 全局 | `~/.config/opencode/opencode.jsonc` | provider / 权限 / 模型别名（本机三个远程 provider 在此） |
| 全局 | `~/.config/opencode/skills/` | 全局技能 |
| 项目 | `<项目>/opencode.json`、`<项目>/.opencode/opencode.json` | 项目 model、provider、MCP、命令等，覆盖全局 |
| 客户端 | `~/.config/opencode/cli.json` | 终端客户端设置（TUI 外观/快捷键），由客户端首次启动从 `tui.json(c)` 迁移 |

项目级配置一律在各自 git 仓库内跟踪，迁移时 8 份配置**全部改写为 v2 原生格式**（列表见 6.3）。

### 6.2 v1 → v2 字段对照（全局配置实例） <a id="config-mapping"></a>

| v1 写法 | v2 写法 | 说明 |
| --- | --- | --- |
| `"permission": "allow"` | `"permissions": [ {"action":"*","resource":"*","effect":"allow"}, {"action":"external_directory",…}, {"action":"read","resource":"*.env",…}, … ]` | v1 的全局字符串表示「全部允许」；v2 改为**有序规则数组**（后者覆盖前者），要保住 v1 的全允许语义需显式放开 `external_directory` 与 `*.env`（v2 默认这两项为 `ask`） |
| `"provider": { … }` | `"providers": { … }` | 单数改复数 |
| `"npm": "@ai-sdk/openai-compatible"` | `"package": "@opencode/ai/providers/openai-compatible"` | 采用 **v2 内置运行时包**，不再依赖 npm 包（配置目录无需 node_modules） |
| `"options": { "baseURL": … }` | `"settings": { "baseURL": … }` | provider / 模型级请求设置统一进 `settings`（另有 `headers`、`body`） |
| 模型条目 `"id": "deepseek/deepseek-v4.1-flash"` | `"modelID": "deepseek/deepseek-v4.1-flash"` | 模型别名键仍是 OpenCode 侧模型 ID，`modelID` 才是发给服务端的 ID |
| 模型条目 `"options": { "reasoningEffort": … }` | 模型条目 `"settings": { "reasoningEffort": … }` | 模型级选项改名 |
| `"tool_call": true` + `"modalities": { "input": [...], "output": [...] }` | `"capabilities": { "tools": true, "input": [...], "output": [...] }` | 能力声明收拢进 `capabilities` |
| 模型级 `"reasoning"` / `"attachment": true` | 无对应字段（v2 忽略） | v2 的能力由 `capabilities` 描述 |
| `"mcp": { "<名>": { … } }` | `"mcp": { "servers": { "<名>": { … } } }` | 服务器必须收进 `servers` |
| `"enabled": true` | `"disabled": false` | 语义取反 |
| `"experimental": { "mcp_timeout": 200000 }` | `"mcp": { "timeout": { "catalog": 200000, "execution": 200000 } }` | v1 的单一超时对应 v2 的目录读取与执行两类超时 |
| `"plugin": [ … ]` | `"plugins": [ … ]` | **仅改名不够**：v1 插件实现在 v2 不运行，须按 v2 插件 API 重写 |
| `"command": { … }` | `"commands": { … }` | 单数改复数；`template`、`description` 不变 |
| 无 | `"env": ["COMMANDCODE_API_KEY"]` | 新增：为自定义 provider 指定凭据环境变量，作为 `/connect` 之外的兜底凭据来源 |

### 6.3 本机配置清单 <a id="config-list"></a>

```text
~/.config/opencode/opencode.jsonc              # 全局：permissions + providers（zhipu / siliconflow / commandcode）
~/develop/bizs/.opencode/opencode.json         # bizs 工作区：lmstudio + llamacpp + MCP mjw-vision
~/develop/cws/.opencode/opencode.json          # cws 工作区：同上（两文件内容一致）
~/develop/bms_other/.opencode/opencode.json    # bms_other：lmstudio + MCP multimodal-local
~/develop/cfsx/opencode.json                   # cfsx：shell（Windows Git bash）+ instructions
~/story/jt/opencode.json                       # story/jt：instructions + commands
~/story/cfsx/opencode.json                     # story/cfsx：shell + instructions
~/story/yszl/.opencode/opencode.json           # story/yszl：lmstudio + llamacpp（多模型）
```

> 项目级配置中含 Windows 侧取值（如 `shell: "C:\\Program Files\\Git\\bin\\bash.exe"`、`D:/Develop/...` 的 MCP 命令），迁移后这些**只适用于对应平台**；v1 无法直接读取 v2 原生字段，若其他机器仍在用 v1，请先在 v1 侧确认再拉取这些改动。

### 6.4 插件 <a id="plugins"></a>

- v2 的插件 API 与 v1 **不兼容**：v1 插件实现（工作区 `.opencode/plugins/*.js`，如本机的 `bg.js`、`graphify.js`）**不会在 v2 中运行**，仅把配置项从 `plugin` 改名为 `plugins` 不够，须按 v2 插件 API 重写入口与钩子；
- 本机**全局未登记任何插件**；项目级仅 `~/develop/bms_other/.opencode/opencode.json` 登记了 `plugins/graphify.js`（v1 实现）——该功能在 v2 下需重写后才可用；
- 重新登记插件后须**完全重启**（桌面端含 sidecar 进程）并先验证会话正常，再投入日常使用。

## 7. 凭据与连接 <a id="auth"></a>

v2 的一个关键变化：**凭据保存在 SQLite 数据库内**（`~/.local/share/opencode/opencode.db`），官方说明仅在其「数据库迁移」时从 v1 的 `auth.json` 导入一次，此后新录入/更新的凭据**不再写回** `auth.json`。本次迁移删除了旧库，故迁移刚完成时 `opencode auth list` 为空，需逐 provider 重新连接；截至 2026-09-29 已完成重连的账号：

```bash
opencode auth list
# OpenCode Go  OpenCode Go   stored
# CommandCode  CommandCode   stored
```

重新连接的方式（按优先级）：

```bash
# 1) 交互式 CLI（推荐，凭据落入 SQLite）
opencode auth login                 # 打开 provider 选择器
opencode auth login commandcode --method key   # 指定 provider 与「API 密钥」方式

# 2) TUI / 桌面端内：/connect 选择 provider 输入密钥，/models 选择模型

# 3) 非交互：直接调服务端 API 的 key 连接端点
#    （`auth login` 的 API 密钥录入要求交互终端，此路可在脚本或工具调用中用）
opencode api post /api/integration/commandcode/connect/key \
  --data '{"key":"<你的密钥>","label":"CommandCode"}'

# 4) 兜底：用环境变量供给凭据（配置里已为三个自定义 provider 写好 env 字段）
opencode service set env COMMANDCODE_API_KEY <你的密钥>
opencode auth list                  # 出现 type 为 environment 的条目
```

> 排障时可用 `opencode api get /api/integration/<id>` 查看某 provider 支持的方法与已有连接（`methods` / `connections` 字段），先确认 provider ID 与可用的认证方式，再选上面任一路径重连。

`~/.local/share/opencode/auth.json` 为 v1 遗留凭据文件，v2 **不读不回写**，仅供人工对照取用；2026-09-29 已移除其中的 commandcode 条目（该 provider 已在 v2 重连成功），余下 opencode-go / opencode / zhipu / siliconflow 四个条目保留，确认各 provider 重连成功后可按需自行删除该文件。

## 8. 使用说明与故障排查 <a id="usage"></a>

### 8.1 常用命令 <a id="usage-cli"></a>

```bash
opencode                                  # 在当前目录打开全屏 TUI
opencode ~/develop/bizs                   # 指定目录打开
opencode mini                             # 极简交互界面
opencode run "帮我梳理这个仓库"            # 非交互执行一条消息（脚本/CI 可用）
opencode run --model commandcode/deepseek-v4.1-flash "只回复两个字:正常"
opencode serve                            # 启动 v2 API / Web 服务
opencode pair                             # 打印 Web 配对信息（用户名/密码/URL）
opencode models                           # 列出可用模型（需交互终端）
opencode mcp list                         # MCP 服务器与连接状态
opencode debug paths                      # 打印各路径（db/home/data/config/cache/state/…）
opencode -c                               # 继续上一次会话
opencode --standalone                     # 用私有服务运行（不共用后台服务）
```

- CLI 在项目目录运行时读该项目配置（如 `~/develop/bizs/.opencode/opencode.json`），本机默认模型为项目配置里的 `llamacpp/qwen3.8-27b-ud-q4-k-m`（连本机 `http://127.0.0.1:8080/v1` 的 llama-server）；
- v2 默认复用**一个共享后台服务**（`opencode serve --service`），所有本地客户端（CLI/桌面端/Web）连它；排障时可用 `--standalone` 起私有服务隔离变量。

### 8.2 桌面端无窗口 / GPU 崩溃（历史结论） <a id="gpu-history"></a>

v1 时期（2026-08）在本机 NVIDIA + Wayland 下遇到过「点图标无窗口」，根因是 **GPU 进程在原生 Wayland + Vulkan 下初始化即 SIGSEGV（`exit_code=139`）并无限重试**，把主进程拖垮：

```text
ERROR:content/browser/gpu/gpu_process_host.cc:998
GPU process exited unexpectedly: exit_code=139
ERROR:ui/ozone/platform/wayland/gpu/wayland_surface_factory.cc:252
'--ozone-platform=wayland' is not compatible with Vulkan.
```

结论与处置（当时对 snap 版与 .deb 版均复现）：

- 与打包方式无关，`ELECTRON_OZONE_PLATFORM_HINT=x11` 也无用（切 X11 后 GPU 进程照样崩溃）；
- 正解是**禁用 GPU 走软件渲染**。用 `.deb` 版时，可在用户级覆盖桌面项（不碰系统文件）：

```text
# ~/.local/share/applications/ai.opencode.desktop.desktop
[Desktop Entry]
Name=OpenCode
Exec=/opt/OpenCode/ai.opencode.desktop --disable-gpu %U
Terminal=false
Type=Application
Icon=ai.opencode.desktop
StartupWMClass=ai.opencode.desktop
MimeType=x-scheme-handler/opencode;
Categories=Development;
```

- v1 回退到 snap 后该崩溃不再复现；v2 桌面端（`.deb` 2.0.16）本次实测 GPU 进程正常、**无需** `--disable-gpu`。仅当 v2 再现 `exit_code=139` 时，才按上面的用户级覆盖临时加上该开关。

排查命令：

```bash
ps -eo cmd | grep -E "ai\.opencode\.desktop" | grep -v grep | head    # 主进程与启动参数
D=$(ls -td ~/.config/ai.opencode.desktop/logs/*/ | head -1)
cat "$D/main.log"; grep -iE 'exit_code=139|GPU process exited|Vulkan' "$D/utility.log"
ls -lt ~/.config/ai.opencode.desktop/Crashpad/pending/*.dmp 2>/dev/null | head   # 近期崩溃转储
```

### 8.3 `opencode models` 无输出 <a id="models-empty"></a>

该命令要求可交互终端；在管道、脚本或工具调用里执行会**静默返回空**。排障用：

```bash
script -qec "opencode models" /dev/null
```

### 8.4 命令找不到 / 装了两个版本 <a id="cli-missing"></a>

```bash
which -a opencode                     # 应只有 ~/.opencode/bin/opencode
echo "$PATH" | tr ':' '\n' | grep opencode
ls -l ~/.opencode/bin/opencode        # 二进制是否存在且有执行权限
opencode --version                    # 期望 v2.0.16
```

- v1 与 v2 **不能并存**（同一个 `opencode` 命令）：若 `which -a` 出现多个路径，先卸载 v1 安装（snap 版用 `sudo snap remove opencode`）；
- snap 版 `latest/stable` 通道仍发布 v1（1.18.x），需要回退 v1 时可用 `sudo snap install opencode` 装回 snap 版 CLI + 桌面端。

### 8.5 MCP 服务器与插件 <a id="mcp-trouble"></a>

```bash
opencode mcp list                     # ✓ 名称 connected 即正常
opencode mcp add <名> --url <URL>     # 加远端服务器（写入项目配置）
opencode mcp auth <名>                # 需要时完成 OAuth
```

| 现象 | 排查 |
| --- | --- |
| MCP 未连接 | 看 `opencode mcp list` 状态；本地服务器核对 `command` 与 `cwd`，远端核对 `url` 与认证 |
| MCP 工具超时 | v2 的 `mcp.timeout` 分 `startup`（默认 30 秒）/`catalog`（默认 30 秒）/`execution`（默认 12 小时）；本机项目配置把 `catalog` 与 `execution` 设为 200 秒 |
| 插件未生效 | v1 插件实现在 v2 不运行，须按 v2 插件 API 重写；改完完全重启客户端 |

## 9. 关联文档 <a id="related"></a>

- 《[中文输入法部署使用说明](中文输入法部署使用说明.md)》：mjpc 的 Fcitx5 + kimpanel 输入法部署，其「候选窗跟随」与本文的「窗口渲染」是两条不同的线，勿混用
- 《[Steamcommunity_302部署使用说明](Steamcommunity_302部署使用说明.md)》：mjpc 上的 Steam 社区加速反代部署与运维
- 《[防火墙部署使用说明](防火墙部署使用说明.md)》：mjpc 开发机 ufw 防火墙规则
- 《[llamacpp部署使用说明](../AI/llamacpp部署使用说明.md)》：本机 llama.cpp 本地推理（CLI 的 `llamacpp` provider 后端）
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发机设施总览（opencode 在其中的定位）
- 《[文档生成规范](../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定
- 《[本地资源](../../用户文档/本地资源.md)》：mjpc 相关机器信息取值（已 gitignore）

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 mjpc 上 opencode CLI、桌面端、配置与凭据的部署、使用与排障。
