# graphify 部署与使用说明

> 适用版本：graphify 0.9.32（PyPI 包名 `graphifyy`，CLI 命令为 `graphify`）
> 适用范围：BMS 项目（Windows 开发机，bash/PowerShell 均适用）

## 1. 概述

graphify 是一个把整个代码库（代码、文档、PDF、图片、视频）映射成**可查询知识图谱**的工具，用来替代在原始文件里 grep 式的搜索。

- **代码免费且完全本地化**：代码用 tree-sitter 做 AST 解析，确定性输出，不调用 LLM，数据不出本机。
- **每条边都有出处**：连接都带 `EXTRACTED`（源码中明确存在）或 `INFERRED`（graphify 推导）标签。
- **不是向量索引**：没有 embedding、没有向量库，是真正的图，可做查询（query）、路径（path）、概念解释（explain）。
- 文档/PDF/图片/视频的语义抽取可选配 `GEMINI_API_KEY` 走 Gemini；不配 key 时由 AI 助手（宿主模型）代为抽取，代码库场景不需要任何 key。

官方信息：

- GitHub：https://github.com/Graphify-Labs/graphify
- 官网：https://graphify.com
- PyPI：https://pypi.org/project/graphifyy/

## 2. 部署（安装）

### 2.1 前置条件

| 依赖 | 最低版本 | 检查命令 |
|---|---|---|
| Python | 3.10+ | `python --version` |
| uv（推荐）或 pipx | 任意 | `uv --version` / `pipx --version` |

Windows 下安装 uv：

```powershell
winget install astral-sh.uv
```

### 2.2 安装 CLI

> **注意**：PyPI 上的官方包名是 `graphifyy`（两个 y），其他 `graphify*` 包均与本工具无关；安装后命令行命令仍是 `graphify`。

```bash
# 推荐：uv 隔离安装（本机已采用此方式）
uv tool install graphifyy

# 备选
pipx install graphifyy
pip install graphifyy   # 可能需要手动配置 PATH
```

如安装后提示 `graphify: command not found`，运行 `uv tool update-shell`（或 `pipx ensurepath`）后重开终端。

升级：

```bash
uv tool install --upgrade graphifyy
```

### 2.3 验证安装

```bash
graphify --version
# 期望输出：0.9.32（或更新版本）
```

> 本机现状：`uv 0.11.7` + `graphify 0.9.32` 已安装于 `~/.local/bin`，版本与项目内 `.opencode/skills/graphify/.graphify_version` 一致。

### 2.4 与 AI 助手集成

graphify 通过 skill + 钩子让 AI 助手"先查图、再读码"。OpenCode 平台的注册命令：

```bash
graphify install --platform opencode
```

**本项目已完成集成**（`.opencode/` 目录，属 graphify 安装脚本生成，勿手动修改）：

- `.opencode/opencode.json`：注册插件 `.opencode/plugins/graphify.js`——图存在时，会在每次 bash 调用前提示优先用 `graphify query`。
- `.opencode/skills/graphify/`：graphify 的 skill（SKILL.md + references/），供助手按步骤构建、更新、查询图谱。
- `.opencode/skills/graphify/.graphify_version`：当前 skill 版本 `0.9.32`。

若以后升级 graphify，请同步刷新上述文件（重新执行 `graphify install --platform opencode` 或按官方说明更新）。

## 3. 构建知识图谱

### 3.1 首次全量构建

在项目根目录执行：

```bash
graphify .        # PowerShell 中不要写 /graphify .（斜杠会被当作路径分隔符）
```

常用参数：

| 参数 | 作用 |
|---|---|
| `<path>` | 指定扫描目录（默认当前目录） |
| `--mode deep` | 深度抽取，产出更多 INFERRED 边 |
| `--directed` | 构建有向图（保留 source→target 方向） |
| `--no-cluster` | 跳过社区发现（大语料可提速） |
| `--no-viz` | 不生成可视化 HTML |
| `--svg` / `--graphml` | 额外导出 graph.svg / graph.graphml |
| `--wiki` | 生成 agent 可爬取的 wiki（index.md + 每社区一篇） |
| `--watch` | 监视目录，代码变动自动重建 |
| `--force` | 强制重写（图变小被拒时用，如确实删除了文件） |

### 3.2 输出产物（graphify-out/）

```text
graphify-out/
├── graph.html       # 交互式图谱，浏览器打开可点击、筛选、搜索
├── GRAPH_REPORT.md  # 审计报告：关键概念、意外连接、建议问题
├── graph.json       # 完整图谱数据，随时可查询（无需重读源码）
├── graph.svg        # （仅 --svg 时生成）
├── wiki/            # （仅 --wiki 时生成）
└── .graphify_*      # 运行状态文件（解释器路径、清单等，勿手动改）
```

### 3.3 增量更新

代码/文档变更后，只重新抽取变更文件（省时省 token）：

```bash
graphify update .           # 等价于 /graphify --update，增量重建
graphify update --force .   # 如提示拒绝缩小图，确认删除文件属实则强制重建
```

> 本项目约定（见 AGENTS.md）：修改代码后应运行 `graphify update .` 保持图谱最新。增量更新后 `graphify-out/` 内文件变脏属正常现象。

## 4. 日常使用

> 以下命令在 `graphify-out/graph.json` 存在时即可使用，无需重建图谱。
> 查询可用中文（本项目已启用中文查询分词）。

### 4.1 提问查询（query）

```bash
graphify query "登录认证是怎么实现的"
graphify query "数据校验" --dfs        # DFS 追踪具体链路
graphify query "用户模块" --budget 1500 # 限制回答长度（token）
```

默认 BFS 遍历，取邻近上下文；`--dfs` 适合追踪一条调用/依赖链。

### 4.2 最短路径（path）

```bash
graphify path "UserModel" "AuthService"
# 输出形如：UserModel --uses--> ... <--references-- AuthService
```

### 4.3 概念解释（explain）

```bash
graphify explain "JWT"
# 输出：节点来源、社区、度数、连接列表（带 EXTRACTED/INFERRED 标签）
```

### 4.4 其他子命令

```bash
graphify add <url>              # 抓取 URL 加入语料并更新图
graphify cluster-only .         # 只对现有图重跑社区发现
graphify hook install           # 装 post-commit 钩子：每次提交自动重建（仅代码）
graphify claude install         # 把 graphify 写进 CLAUDE.md（Claude Code 专用）
```

## 5. 本项目的使用约定（来自 AGENTS.md）

1. **先查图**：代码库相关问题，当 `graphify-out/graph.json` 存在时，先运行 `graphify query "<问题>"`（可直接用中文）。关系用 `graphify path "<A>" "<B>"`，概念用 `graphify explain "<概念>"`。返回的是范围受限的子图，通常比 GRAPH_REPORT.md 或原始 grep 输出小得多。
2. **钩子或增量更新后 `graphify-out/` 变脏属正常**，不应因此跳过 graphify。
3. 若 `graphify-out/wiki/index.md` 存在，用它做广域导航，避免直接浏览源码。
4. 仅在做宏观架构审查、或 query/path/explain 信息不足时，才读 `graphify-out/GRAPH_REPORT.md`。
5. 修改代码后运行 `graphify update .` 保持图谱最新。

## 6. 常见问题排查

| 现象 | 处理 |
|---|---|
| `graphify: command not found` | 运行 `uv tool update-shell` 或 `pipx ensurepath`，重开终端 |
| `ModuleNotFoundError: No module named 'graphify'` | 用 `uv tool install`/`pipx` 隔离安装，避免 pip 与运行环境不一致 |
| 增量更新报"refused to shrink graph.json" | 确认确实删除了文件后，用 `graphify update --force .` 全量重建 |
| `ERROR: Graph is empty` | 语料全被跳过或抽取失败，检查扫描路径与文件类型 |
| 图过大（>5000 节点）生成 HTML 卡顿 | 加 `--no-viz` 跳过可视化，或按子目录缩小扫描范围 |
| 想用 Gemini 做文档语义抽取 | 设置 `GEMINI_API_KEY`/`GOOGLE_API_KEY`，安装 `graphifyy[gemini]`；不设置时由 AI 助手代抽，代码库场景无需 key |
