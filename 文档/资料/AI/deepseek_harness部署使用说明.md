# DeepSeek Harness（dsh）部署与使用说明

> mjpc 开发机（Ubuntu 26.04 / Node 24 + pnpm 11.7.0）· 基于 deepseek-harness `dsh-v0.1.5-alpha.1`（commit `5dda764ed3`，2026-09-08 自 0.1.2-alpha.1 升级）

[文档首页](../../文档首页.md) › 资料 › deepseek_harness 部署与使用说明

## 1. 概述 <a id="intro"></a>

DeepSeek Harness（命令 `dsh`）是 [DeepSeek AI](https://deepseek.com) 开发的**开源 agent harness（智能体框架）**，
构建于「一切皆插件」架构，由 [Cordis](https://github.com/cordiverse/cordis) 驱动（设计见论文
[_A Programming Paradigm for Spatiotemporal Composability_](https://arxiv.org/abs/2608.25512)）。

它提供多种运行形态（profile）：`web`（浏览器 UI，最常用）、`tui`（终端）、`headless`（跑一次任务即退出），
由「有序的插件补丁层 + 用户覆盖」合成一个可启动的 profile。当前处于**开发者预览**阶段，快速迭代、
**未来会有破坏兼容性变更**——生产使用先读仓库 [安全说明](https://github.com/deepseek-ai/deepseek-harness/blob/main/SAFETY.md)。

| 项 | 值 |
| --- | --- |
| 包名 | `@deepseek-ai/dsh-root`（monorepo 根） |
| 版本 | 0.1.5-alpha.1（tag `dsh-v0.1.5-alpha.1`） |
| 许可证 | MIT |
| 官方文档 | [deepseek-harness.github.io/deepseek-harness](https://deepseek-harness.github.io/deepseek-harness/) |
| 仓库 | [github.com/deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) |
| 本机源码 | `/home/minjian/develop/deepseek-harness` |

本项目采用**源码运行**（`pnpm dsh web`），并配了桌面快捷方式一键更新与启停脚本（见第 6 节）。

## 2. 环境要求 <a id="prereq"></a>

| 项 | 要求 | 本机 |
| --- | --- | --- |
| Node.js | `^22.19.0 \|\| >=24.0.0` | v24.20.0（nvm 管理，默认 24） |
| pnpm | 11.7.0（`packageManager` 锁定） | 11.7.0 |
| 包管理器镜像 | 建议 npmmirror（淘宝） | `NVM_NODEJS_ORG_MIRROR` 已指向 npmmirror |

> Node 与 pnpm 由 nvm 提供（`~/.bashrc` 已加载 nvm，默认 Node 24）；pnpm 建议配 `registry=https://registry.npmmirror.com` 加速。
> 依赖已安装（仓库含 `pnpm-lock.yaml`），首次或更新依赖时才需 `pnpm install`。

## 3. 获取与构建 <a id="build"></a>

### 3.1 方式一：源码运行（本项目采用） <a id="build-source"></a>

```bash
# 克隆（国内网络可加 ghfast.top 前缀加速）
git clone https://github.com/deepseek-ai/deepseek-harness.git /home/minjian/develop/deepseek-harness
# 加速写法：git clone https://ghfast.top/https://github.com/deepseek-ai/deepseek-harness.git

cd /home/minjian/develop/deepseek-harness
pnpm install          # 安装依赖（建议 npmmirror 源）
pnpm run build        # 准备仓库产物（生产 Web runner 必需）
pnpm dsh web          # 启动 Web UI（默认 http://127.0.0.1:3080）
```

> `pnpm run build` 只准备产物，不重复构建；`pnpm dsh web` 直接复用已构建产物。改动源码后需重新 `pnpm run build`。

### 3.2 方式二：npm 直接运行（免克隆） <a id="build-npm"></a>

```bash
npx @deepseek-ai/dsh web
```

适合只想快速体验、不改源码的场景；跑的是发布包。

## 4. 运行 dsh <a id="run"></a>

### 4.1 CLI 命令 <a id="run-cli"></a>

`pnpm dsh` 等价于 `node --import tsx/esm apps/cli/src/bin.ts`（仓库内脚本入口）：

| 命令 / 选项 | 说明 |
| --- | --- |
| `dsh web` | 启动 Web UI（= `--profile web`），默认 `http://127.0.0.1:3080` |
| `dsh --profile <name>` | 启动 `$DSH_HOME/profiles` 下指定 profile（web / tui / headless…） |
| `dsh --profile headless "<任务>"` | 跑一次任务、打印结果后退出 |
| `dsh plugin --profile <name> add <pkg>` | 向 profile 安装插件（转发给 pnpm） |
| `dsh --patch <path>` | 追加一层补丁叠加（可重复） |
| `dsh --dump-config` | 打印合成后的 profile 配置树 |
| `-V` / `--version` | 版本号 |

### 4.2 Web UI 参数 <a id="run-web"></a>

`dsh web` 的专属 flag：

| flag | 说明 |
| --- | --- |
| `--port <port>` | 监听端口；传 `0` 让系统自选空闲端口（默认 3080） |
| `--host <host>` | 绑定地址（CLI **不支持 `0.0.0.0`**，会按用法错误退出） |
| `--no-open` | 仅起服务器、不自动打开浏览器 |
| `--trusted-host <authority...>` | `/api` 浏览器信任围栏额外接受的具名 authority |

行为：

- **本机启动**自动用默认浏览器打开页面；**SSH 远程启动**（`SSH_CONNECTION`/`SSH_TTY` 非空）只打印宿主机 URL、不打开浏览器。
- 生产 Web runner 依赖 `pnpm run build` 的产物（见 3.1）。

```mermaid
flowchart LR
  subgraph mjpc ["mjpc 开发机"]
    SC ["桌面快捷方式<br/>dsh-web-start.sh"]
    PN ["pnpm dsh web<br/>(tsx 启动 CLI)"]
    RUN ["生产 Web Runner<br/>(需 pnpm run build 产物)"]
    UI ["Web UI :3080<br/>默认浏览器"]
    Cfg ["DSH_HOME ~/.dsh<br/>settings.yaml + .credentials.yaml"]
    LLM ["模型 Provider<br/>DeepSeek / 自托管"]
  end
  SC --> PN --> RUN --> UI
  RUN -.->|"读取配置 / 凭据"| Cfg
  RUN -->|"OpenAI 兼容请求"| LLM
```

## 5. 配置与模型 <a id="config"></a>

### 5.1 DSH_HOME 目录 <a id="config-home"></a>

未显式设置 `DSH_HOME` 时默认 `~/.dsh`：

```text
~/.dsh/                          # DSH_HOME
├── profiles/                    # 各 profile，--profile 从这里启动
│   └── web/                     #   web profile（含 node_modules 与补丁层）
├── settings.yaml                # 全局设置：provider 引用、模型 input 模态等
├── .credentials.yaml            # API key（write-only，设置页只存引用、不回显明文）
└── storages/                    # 会话 / 存储数据
```

> 模型改动**下一次请求即生效，无需重启服务器**（见 5.2）。

### 5.2 配置模型 Provider <a id="config-model"></a>

在 Web UI 的 **Settings → Models** 中配置（改动静态生效）：

- **DeepSeek**：卡片内填 API Key 保存，密钥写入 `$DSH_HOME/.credentials.yaml`。
- **Add provider**：选目录内置 provider（Anthropic / OpenAI 等），填 Key；目录自动提供端点、协议、模型清单。
- **Add a custom provider**：接自托管 / 企业网关——填 Provider ID（**永久**，请求与会话都引用它，改名=新增再删旧）、base URL、协议、凭据、至少一个模型。可点「Fetch available models」拉取候选。
- **视觉模型**：自定义 provider 手填的模型默认视为纯文本，附图会被拒。需在 `~/.dsh/settings.yaml` 给该模型加 `input: [text, image]`，或整路用 `defaultInput: [text, image]` 兜底：

  ```yaml
  llm-pi-ai:
    providers:
      my-gateway:
        apiKeyEnv: GATEWAY_API_KEY   # 从环境变量取 Key
        api: openai-completions
        baseURL: https://gateway.example/v1
        defaultInput: [text, image]
        models:
          - id: vision-preview
  ```

### 5.3 接入本地 llama.cpp 服务（本机） <a id="config-llamacpp"></a>

本地模型走自定义 provider `llamacpp`，接本机的 `llama-server`（`127.0.0.1:8080`，服务部署见《[llamacpp部署使用说明](llamacpp部署使用说明.md)》），模型为 Qwen3.8-27B（Q4_K_M）：

> **坑**：pi-ai 的 OpenAI 兼容实现对**无鉴权的本地服务也要求 API key 或 `Authorization` 头**（dsh 已知限制），不配凭据则发消息报 `No API key for provider: llamacpp`。解法：配一个**占位 key** 即可——llama.cpp 不校验它，任意非空值可用。

本机实际配置：

```yaml
# ~/.dsh/settings.yaml
llm-pi-ai:
  providers:
    llamacpp:
      displayName: 本地（llama.cpp）
      api: openai-completions
      baseURL: http://127.0.0.1:8080/v1
      apiKeyEnv: LLAMACPP_API_KEY   # 占位 key 的凭据引用
      models:
        - id: /home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf   # llama-server 上报的 id 即模型路径
          name: Qwen3.8-27B-UD-Q4_K_M
          contextWindow: 210000   # 与服务端 -c 215040（约 210K）一致
          maxTokens: 32000
```

```yaml
# ~/.dsh/.credentials.yaml 的 refs 段
refs:
  LLAMACPP_API_KEY: no-key-needed   # 占位值，llama.cpp 不校验
```

使用注意：

- `settings.yaml` 与 `.credentials.yaml` 的**字段级**改动**下一次请求即生效**，无需重启；但 `llm-pi-ai.providers` 是**整段校验（全有或全无）**——段内任一路由配置不被 pi-ai 服务时整段被拒（本地模型随其它 provider 一起消失），且**校验失败后不会自动恢复，需重启 dsh web**（见第 7.2 节 FAQ）。
- `agent-default-model` 默认是 `deepseek-official`（DeepSeek API）；要用本地模型，在 Web UI 的模型选择器里**手动选择**本地模型。

## 6. 桌面快捷方式（本机定制） <a id="desktop"></a>

为免每次敲命令，桌面配了「更新 dsh与插件」一键更新项，启停走脚本（图标 `~/.local/share/icons/dsh-web.svg`）：

| 项 | 位置 / 行为 |
| --- | --- |
| 桌面项 `更新 dsh与插件` | `~/.local/share/applications/更新 dsh与插件.desktop`，`Terminal=true` 直跑 `bms/scripts/tools/dsh/dsh-update.sh`（2026-09-09 新增） |
| `~/.local/bin/dsh-web-start.sh` | 启动 dsh web：加载 nvm(Node24+pnpm) → cd 仓库 → exec `pnpm dsh web`（前台，终端内跑便于看日志；未建独立桌面启动项，需要时在终端手跑或自建项） |
| `~/.local/bin/dsh-web-stop.sh` | 停止 dsh web：按端口 3080 定位 PID → kill → 等端口释放(≤5s) → 兜底 kill -9 → notify-send |

```text
~/.local/bin/
└── dsh-web-start.sh    # 启动 dsh web（前台）
└── dsh-web-stop.sh     # 停止 dsh web（按端口，含兜底强杀与通知）
（更新脚本位于 bms 仓库 scripts/tools/dsh/dsh-update.sh，桌面项 Exec 直接指向仓库路径）
```

`dsh-update.sh` **幂等更新流程**：先比对版本——dsh 主体比对本地 HEAD 与 origin/master，插件（dsh-free-vision、dsh-undo-savepoint）比对已装版本与 npm 最新；知识图谱（2026-09-10 纳入）——dsh-graphify 比对已装版本与 ghfast 远端 tag、graphifyy 比对已装版本与 PyPI 清华源最新，落后时分别执行「源码 git pull + pnpm install/build + remove → add file: 重装」与「uv tool upgrade（受原版本 pin 约束时自动转 --force 直装）→ graphify-mcp 探活补 extras」；**全部一致且 web 在跑 → 提示退出（不动 web）；web 未跑 → 直接启动**；任一落后才停 web → 只更新落后项（`git pull --ff-only` / `pnpm install` / `pnpm run build`、插件 `up --latest`）→ 重启（仅 graphifyy 运行时落后时不重启——MCP 子进程按需启动即用新版本）。网络查询失败（离线/慢）时跳过对应项、**不误停 web**；更新命令均带超时（pull 5min / install 10min / build 15min / up 5min / 图谱各步 2-5min），任何失败路径由 EXIT 兜底把 web 拉起，不会出现"停了起不来"。支持 `--force`（跳过版本检查强制全量更新，含图谱）、`--no-restart`（只更新不重启）、`--skip-kg`（跳过知识图谱检查与更新）。更新前的 profile 配置/插件树已被 dsh-undo-savepoint 自动快照，出错可 undo 回滚（见 8.2）。

## 7. 维护与排障 <a id="maintain"></a>

### 7.1 常用维护 <a id="maintain-daily"></a>

```bash
cd /home/minjian/develop/deepseek-harness
pnpm run typecheck    # 类型检查
pnpm run lint         # oxlint
pnpm test             # vitest
bash /home/minjian/develop/bms/scripts/tools/dsh/dsh-update.sh   # 一键更新（桌面「更新 dsh与插件」同款）：源码 git pull + 依赖 + 构建 + 插件最新 + 重启 web
```

### 7.2 常见问题 <a id="faq"></a>

| 问题 | 处理 |
| --- | --- |
| 端口 3080 被占用？ | `dsh web --port 0`（系统自选，看打印的 URL）或换 `--port <n>`；停止用 `dsh-web-stop.sh`。 |
| 传 `--host 0.0.0.0` 报用法错误？ | CLI 有意禁止 `0.0.0.0`（安全围栏），只能绑定具体地址；对外暴露走反向代理。 |
| SSH 启动没自动开浏览器？ | 预期行为：检测到 `SSH_CONNECTION`/`SSH_TTY` 就只打印宿主机 URL，靠 SSH 端口转发访问。 |
| `dsh web` 报错找不到产物？ | 先 `pnpm run build` 准备产物（生产 runner 依赖构建产物）。 |
| 换模型后没生效？ | 改配置后**下一次请求**即生效，无需重启；若仍不行查 `~/.dsh/settings.yaml` 与 `.credentials.yaml` 引用是否一致。 |
| Web UI 模型下拉只剩 DeepSeek 官方、自定义 provider（本地 llamacpp / 硅基流动等）全消失？ | `llm-pi-ai.providers` **整段校验（全有或全无）**：段内任一路由不被服务即整段拒绝。典型触发：路由缺 `api`（模型不在 pi-ai 目录）、残留旧字段（`provider`、`maxRetries`/`maxRetryDelayMs`）、空 `baseURL`/`displayName`、空 `defaultInput`。修复后**重启 dsh web** 才重新装配（校验失败后 settings watcher 不自动恢复）。可本地快速验证：`python3 -c "import yaml,json;json.dump(yaml.safe_load(open('$HOME/.dsh/settings.yaml'))['llm-pi-ai']['providers'],open('/tmp/p.json','w'))"` 后在 `deepseek-harness/packages/llm/llm-pi-ai` 跑 `node --import tsx -e "import {resolveProfiles} from './src/config.ts'; import fs from 'node:fs'; resolveProfiles(JSON.parse(fs.readFileSync('/tmp/p.json','utf8'))); console.log('OK')"`。 |
| 报 `provider "xxx" model "…" needs an api; the installed catalog does not describe it`？ | 该 provider/模型不在 pi-ai 安装目录且路由未声明协议。给该 provider 段补 `api: openai-completions` + `baseURL`（2026-09-08 实测：`opencode` 免费翻译段缺这两字段，导致整个 `llm-pi-ai` 段失效、本地模型一并消失；补上并重启 dsh web 后恢复）。 |
| 发消息报 `No API key for provider: llamacpp`（或某自定义 provider）？ | pi-ai 的 OpenAI 兼容实现对无鉴权本地服务也要求凭据；给路由加 `apiKeyEnv` 指向占位 key（见 5.3）。 |
| 视觉模型附图被拒？ | 自定义 provider 手填模型默认纯文本，需按 5.2 加 `input: [text, image]` 或 `defaultInput`。 |
| 依赖安装慢 / 超时？ | pnpm 配 npmmirror 源；nvm 下 Node 用 `NVM_NODEJS_ORG_MIRROR=https://npmmirror.com/mirrors/node`。 |
| `dsh web` 报 `Cannot find package '@deepseek-ai/dsh-host-apiproxy'`？ | 插件 `@linxin666/dsh-remote-web-ui` 与当前 dsh 不兼容（缺该 host 包，启动即崩）；`pnpm dsh plugin --profile web remove @linxin666/dsh-remote-web-ui` 卸载（见 8.4）。 |
| 想彻底停止后台 dsh web？ | `bash ~/.local/bin/dsh-web-stop.sh`，或 `ss -lptnH | awk '$4 ~ /:3080$/'` 找 PID 后 `kill`。 |

## 8. 插件扩展 <a id="plugins"></a>

「一切皆插件」，可通过 `dsh plugin --profile <name> add|remove <pkg>` 给 profile 装/卸插件（转发给 pnpm，并自动 reconcile `dsh.profile.bundles` 图层）。本机**当前装有**两个挂进 `web` profile 的 bundle 扩展：`dsh-free-vision`（见 8.1）、`dsh-undo-savepoint`（见 8.2）。曾装过已移除：`dshmarket` / `dsh-context`（0.1.5 重构后未保留，见 8.3）、`dsh-remote-web-ui`（见 8.4）、`dsh-tui`（见 8.5）。

### 8.1 免费视觉 dsh-free-vision（web profile bundle，当前装有） <a id="plugins-free-vision"></a>

在 web 会话内提供**识图工具 `image_understand`**：把 mjw 机器上 LM Studio 的
`qwen3-vl-8b-instruct-abliterated-v2`（多模态识图模型，服务与鉴权见《[LM Studio 模型服务使用说明](LM Studio模型服务使用说明.md)》）
接为本地识图能力，图片不上云。

| 项 | 值 |
| --- | --- |
| 安装 | `pnpm dsh plugin --profile web add dsh-free-vision`（2026-09-08 装） |
| 版本 | 1.0.8（`profile/package.json` 记 `^1.0.8`） |
| 配置 | `~/.dsh/free-vision.json`：服务地址、API token、模型名、工具参数（token 不落被跟踪文件） |
| 落位 | `~/.dsh/profiles/web`，登记于 `dsh.profile.bundles` 图层 |
| 生效时机 | bundle 图层在 profile **启动时**合成，装/卸需**重启 dsh web** 生效（区别于 5.1 模型/设置的「下一次请求即生效」） |

### 8.2 撤销/保存点 dsh-undo-savepoint（web profile bundle，当前装有） <a id="plugins-undo-savepoint"></a>

**配置变更自动快照 + 一键回滚**：装插件、改皮肤、调设置等变更前自动打快照，错了随时撤销（undo/redo）；
dsh **启动崩溃 / 插件树损坏**时也能救回——SAFE MODE（只留本插件启动）+ 离线 CLI/GUI，回滚无需重装。
仓库：<https://github.com/lire1131/dsh-undo-savepoint>（MIT，零依赖）。

| 项 | 值 |
| --- | --- |
| 安装 | `pnpm dsh plugin --profile web add dsh-undo-savepoint`（2026-09-09 装） |
| 版本 | 0.3.5（npm 包 `dsh-undo-savepoint`） |
| 使用 | Web UI 快照面板；会话内 `undo_list` / `undo_diff` / `undo_restore` / `undo_snapshot` 等工具；崩溃告警会点名最近良好快照 |
| 落位 | bundle 图层；快照存 `~/.dsh/undo-snapshots/{manual,auto}` |
| 与更新脚本 | `dsh-update.sh` 更新前后状态可经它回滚；插件版本纳入脚本 `up --latest`（见 6 节） |

> **误报提醒**：主动停止 dsh web（`dsh-web-stop.sh` 或更新脚本的停启流程）会被插件记为「上次运行未正常结束」，
> `undo_list` 顶部出现崩溃告警属预期，当前实例运行正常即可忽略，**不要**为此 undo 回滚。

#### 8.2.1 外部救援工具（DSH 起不来时也能用） <a id="plugins-undo-offline"></a>

插件自带**局外救援工具**——不依赖 DSH 运行，DSH 崩溃、启动不了时也能操作快照做回滚。工具随插件装在
`~/.dsh/profiles/web/node_modules/dsh-undo-savepoint/tools/`（与 Node 插件**共用同一快照仓库与格式**）：

| 文件 | 作用 | 平台 |
| --- | --- | --- |
| `dsh-undo-savepoint-gui.bat` / `.ps1` | 图形界面「DSH 撤销管理器」：崩溃横幅 + 一键回退、导出/导入、快照 diff、清理、设置面板、系统托盘；语言随系统 UI（`DSH_UNDO_LANG=zh\|en` 可强制） | **仅 Windows**（WinForms） |
| `dsh-undo.ps1` | 命令行救援：`list` / `snapshot` / `undo` / `redo` / `restore -Id <id>` / `diff` / `remove` / `prune` / `export` / `import` / `safe-mode` / `recent` | PowerShell 5.1 与 7（pwsh 7 跨平台，Linux 可跑） |
| `dsh-plugin.ps1` | 安全装插件：自动前后快照，失败自动回退 | 同上 |
| `make-desktop-shortcut.bat` / `.ps1` | Windows 上双击一键创建桌面「DSH撤销管理器」快捷方式 | 仅 Windows |

典型救援场景（插件 README）：DSH 启动报 `duplicate loader entry id` 之类插件树错误 → 打开「DSH 撤销管理器」→
选中出问题前的快照 → 回退 → 重启 DSH，不用重装、不丢会话。Windows PowerShell 用法示例：

```powershell
# GUI（推荐）:双击 dsh-undo-savepoint-gui.bat（或 make-desktop-shortcut.bat 生成的桌面图标）
# CLI:
powershell -NoProfile -ExecutionPolicy Bypass -File "...\tools\dsh-undo.ps1" list
powershell -NoProfile -ExecutionPolicy Bypass -File "...\tools\dsh-undo.ps1" restore -Id <快照id> -Force
```

**快照目录定位与跨机救援**：工具与插件按 `DSH_HOME`（未设则 `~/.dsh`）定位 `undo-snapshots/{manual,auto}`；
环境变量 `DSH_UNDO_ROOT` 可覆盖根目录——需要从另一台机器救援时，把快照目录挂到该变量指向的路径即可。

**本部署（mjpc / Ubuntu）提示**：GUI 为 WinForms，仅 Windows 可用；CLI 是纯 PowerShell，Linux 上需先安装
PowerShell 7（`pwsh`）才能跑。**已决定暂不装 pwsh**（2026-09-09）：日常回滚用 Web UI 快照面板或会话内 undo 工具即可；
真遇 DSH 起不来的离线场景，届时再评估补装 pwsh（CLI 用法同上，文件路径
`~/.dsh/profiles/web/node_modules/dsh-undo-savepoint/tools/dsh-undo.ps1`）或 Windows 侧 GUI 救援。

### 8.3 曾装已移除：dshmarket 与 dsh-context <a id="plugins-removed"></a>

0.1.2 时代装过两个 web bundle 扩展，随 **2026-09-08 升级 0.1.5 的 profile 重构未再保留**
（bundles 现为 dsh-base / dsh-web-app / dsh-free-vision / dsh-undo-savepoint）：

- `dshmarket`：可视化插件市场（浏览/搜索/一键安装社区插件），当时 ^1.37.0，npm 最新 1.45.1；
- `dsh-context`：客户端上下文注入 bundle，当时 ^0.38.1，npm 最新 0.47.0。

如需装回（0.1.5 兼容性未验证；装后启动崩溃可 remove 还原或用 dsh-undo-savepoint 回滚）：

```bash
cd /home/minjian/develop/deepseek-harness
pnpm dsh plugin --profile web add dshmarket
pnpm dsh plugin --profile web add dsh-context
```

### 8.4 远程 Web UI dsh-remote-web-ui（web profile bundle，**已卸载**） <a id="plugins-remote-web-ui"></a>

> **结论：`dsh web` 启动即崩溃（plugin tree failed to load），已用官方 `dsh plugin remove` 卸载。**

`@linxin666/dsh-remote-web-ui`（第三方 bundle，`dsh.client.platform = web`）用于远程访问 Web UI。

**为何报错（根因）**：它的 `lib/index.js` 依赖 `@deepseek-ai/dsh-host-apiproxy`，而 dsh（0.1.2 与 0.1.5 均）**不提供该包**，导致 web profile 加载插件树时报 `ERR_MODULE_NOT_FOUND`：

```text
Error: dsh: plugin tree failed to load: failed to apply loader entry include
(cordis:include): failed to import loader entry remote-web-ui
(@linxin666/dsh-remote-web-ui): Cannot find package '@deepseek-ai/dsh-host-apiproxy'
imported from ~/.dsh/profiles/web/node_modules/@linxin666/dsh-remote-web-ui/lib/index.js
```

**处置**：

```bash
cd /home/minjian/develop/deepseek-harness
pnpm dsh plugin --profile web remove @linxin666/dsh-remote-web-ui   # 转发 pnpm remove 并自动剔除 bundle 图层
```

卸载后 `dsh web` 恢复正常启动。装上它须等该包适配当前 dsh（移除对 `@deepseek-ai/dsh-host-apiproxy` 的依赖或等官方补包）再试；安装命令备查：`pnpm dsh plugin --profile web add @linxin666/dsh-remote-web-ui`。

### 8.5 终端客户端 dsh-tui（全局 CLI，**已卸载**） <a id="plugins-tui"></a>

> **结论：与 dsh 不兼容（0.1.2 时代实测，0.1.5 未复测），已全局卸载，暂不使用。**

DSH 的**终端客户端**（TUI over the DSH client contract `ctx.remote`），可连上正在运行的 harness 操作会话。
它**不是** `dsh.bundle` 插件，而是一个**独立 CLI**（bin `dsh-tui`），因此按**全局安装**、不挂 profile。

**为何用不了（根因，基于当时 v0.1.2-alpha.1）**：`dsh web` 把 `/api/*` 全部 RPC 压到 `client-connection` 的 `rpc-host`，
每个请求需过 `browserAuth.isAuthenticated()`——**只认绑定 authority 的签名 cookie**（`packages/client/connection/src/browser-auth.ts`，
不支持 header/query 替代）；且 `client-connection` 配置仅有 `trustedHosts` + `cookieMaxAgeDays`，**没有关闭鉴权的开关**。
dsh-tui 的 `DshClient`（`lib/client.js`）只 POST `/api/<method>` 且**不带任何 cookie/token**，故 `session.create` 报 `HTTP 401`。
即：dsh-tui 按「/api 可匿名」设计（README 只让你跑 `dsh web`），与当前 dsh 的 cookie 门禁互不兼容；`dsh-tui@0.2.19`（npm 最新）仅读 `DSH_URL`，无鉴权选项。

**处置**：已执行 `pnpm remove -g dsh-tui` 全局卸载。若未来 dsh-tui 增加鉴权（或 dsh 为程序化客户端提供 token），再按需装回。

**安装命令（备查）**：

```bash
pnpm setup        # 一次性：把 $PNPM_HOME/bin 写进 ~/.bashrc，新开终端生效
pnpm add -g dsh-tui
dsh-tui --version # 0.2.19
```

## 9. mjw（Windows）安装 <a id="mjw-install"></a>

> 2026-09-10 已在 mjw（Windows 11）完成 DSH 安装（commit `b2e3b2a0`，与本文档 mjpc 环境一致），
> **部署实录已独立成文**：《[deepseek_harnessWindows部署使用说明](../资料/开发服务器/windows/deepseek_harnessWindows部署使用说明.md)》
> ——含 pnpm 证书坑修复、install/build、桌面启停入口、web 仅绑 127.0.0.1（官方禁止 `--host 0.0.0.0`）、计划任务长命令执行法及 Windows 排障。mjw 侧通用能力（插件 bundle、undo 快照等）仍以本文档第 8 节为准。

---

> 本文档基于 deepseek-harness `dsh-v0.1.5-alpha.1`（commit `5dda764ed3`，Node 24 / pnpm 11.7.0 源码运行）编写，2026-09-09 随 0.1.5 升级与插件变更同步。
> 项目：[github.com/deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) · 文档：[deepseek-harness.github.io](https://deepseek-harness.github.io/deepseek-harness/)
