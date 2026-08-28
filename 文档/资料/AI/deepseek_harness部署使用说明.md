# DeepSeek Harness（dsh）部署与使用说明

> mjpc 开发机（Ubuntu 26.04 / Node 24 + pnpm 11.7.0）· 基于 deepseek-harness `dsh-v0.1.2-alpha.1`（commit `cd5ef81481`）

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
| 版本 | 0.1.2-alpha.1（tag `dsh-v0.1.2-alpha.1`） |
| 许可证 | MIT |
| 官方文档 | [deepseek-harness.github.io/deepseek-harness](https://deepseek-harness.github.io/deepseek-harness/) |
| 仓库 | [github.com/deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) |
| 本机源码 | `/home/minjian/develop/deepseek-harness` |

本项目采用**源码运行**（`pnpm dsh web`），并配了桌面快捷方式一键启停（见第 6 节）。

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

## 6. 桌面快捷方式（本机定制） <a id="desktop"></a>

为免每次敲命令，配了桌面一键启停（图标 `~/.local/share/icons/dsh-web.svg`）：

| 桌面项 | 行为 |
| --- | --- |
| `启动 dsh web` | `ptyxis` 终端跑 `~/.local/bin/dsh-web-start.sh` |
| `停止 dsh web` | 跑 `~/.local/bin/dsh-web-stop.sh` |

```text
~/.local/bin/
└── dsh-web-start.sh    # 加载 nvm(Node24+pnpm) → cd 仓库 → exec pnpm dsh web
└── dsh-web-stop.sh     # 按端口 3080 定位 PID → kill → 等端口释放(≤5s) → 兜底 kill -9 → notify-send
```

- 启动脚本依赖 `~/.bashrc` 已加载 nvm（默认 Node 24 + pnpm），`NVM_NODEJS_ORG_MIRROR` 指向 npmmirror。
- 停止脚本按**端口**（非进程名）定位，能覆盖 `--port` 换端口的情况需改脚本里的 `PORT`；终止后 `notify-send` 弹通知。
- 桌面项 `Exec` 用 `ptyxis -x "bash <脚本>"`（GNOME 的 ptyxis 终端）在终端窗口前台跑，便于看日志。

## 7. 维护与排障 <a id="maintain"></a>

### 7.1 常用维护 <a id="maintain-daily"></a>

```bash
cd /home/minjian/develop/deepseek-harness
pnpm run typecheck    # 类型检查
pnpm run lint         # oxlint
pnpm test             # vitest
git pull && pnpm install && pnpm run build   # 升级并重建
```

### 7.2 常见问题 <a id="faq"></a>

| 问题 | 处理 |
| --- | --- |
| 端口 3080 被占用？ | `dsh web --port 0`（系统自选，看打印的 URL）或换 `--port <n>`；停止用 `dsh-web-stop.sh`。 |
| 传 `--host 0.0.0.0` 报用法错误？ | CLI 有意禁止 `0.0.0.0`（安全围栏），只能绑定具体地址；对外暴露走反向代理。 |
| SSH 启动没自动开浏览器？ | 预期行为：检测到 `SSH_CONNECTION`/`SSH_TTY` 就只打印宿主机 URL，靠 SSH 端口转发访问。 |
| `dsh web` 报错找不到产物？ | 先 `pnpm run build` 准备产物（生产 runner 依赖构建产物）。 |
| 换模型后没生效？ | 改配置后**下一次请求**即生效，无需重启；若仍不行查 `~/.dsh/settings.yaml` 与 `.credentials.yaml` 引用是否一致。 |
| 视觉模型附图被拒？ | 自定义 provider 手填模型默认纯文本，需按 5.2 加 `input: [text, image]` 或 `defaultInput`。 |
| 依赖安装慢 / 超时？ | pnpm 配 npmmirror 源；nvm 下 Node 用 `NVM_NODEJS_ORG_MIRROR=https://npmmirror.com/mirrors/node`。 |
| 想彻底停止后台 dsh web？ | 桌面「停止 dsh web」，或 `ss -lptnH | awk '$4 ~ /:3080$/'` 找 PID 后 `kill`。 |

---

> 本文档基于 deepseek-harness `dsh-v0.1.2-alpha.1`（commit `cd5ef81481`，Node 24 / pnpm 11.7.0 源码运行）编写。
> 项目：[github.com/deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) · 文档：[deepseek-harness.github.io](https://deepseek-harness.github.io/deepseek-harness/) · 生成日期：2026-08-28
