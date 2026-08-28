# graphify 部署与使用说明

> Linux 环境 · 基于 graphify 0.9.51（2026-08-28 由 Windows + PowerShell 7 迁移而来）

[文档首页](../../文档首页.md) › 资料 › graphify 部署与使用说明

## 1. 什么是 graphify <a id="intro"></a>

graphify 是一个开源命令行工具（Python 包名 `graphifyy`），能把任意目录下的
代码、文档、论文、图片、视频自动转换为持久化的知识图谱，并附带社区检测、审计追踪，
产出三种结果：交互式 HTML 可视化、GraphRAG 就绪的 JSON、以及人话版的 GRAPH_REPORT.md。

核心特性：

- **纯 AST 结构化抽取**：代码文件用 tree-sitter AST 分析，确定性、免费、无需 API Key。
- **语义抽取**：文档/论文/图片可选用 Gemini API；未配置时由 AI 助手自身完成（见第 4.2 节）。
- **诚实审计**：每条关系标注 EXTRACTED（事实）／INFERRED（推断）／AMBIGUOUS（模糊）。
- **持久化**：图谱跨会话保留在 `graphify-out/`，之后直接用 `query` 查询，不必重建。
- **增量更新**：`--update` / `graphify update` 只重新抽取新增或变更的文件。
- **中文支持**：中文查询分词（jieba，见 3.2 节）、callflow 架构图中文界面（见 7.2 节）。

## 2. 环境要求 <a id="prereq"></a>

本机（Linux）已验证的环境（2026-08-28 由 Windows + PowerShell 7 迁移而来）：

| 组件 | 要求 | 本机版本 |
| --- | --- | --- |
| Python | ≥ 3.10 | 3.14.4 |
| uv | 推荐（工具安装/隔离环境） | 0.12.7 |
| git | 克隆 GitHub 仓库时使用 | 2.53.0 |
| graphify | uv 安装（含 extras） | 0.9.51 |

> graphify 本身**不需要任何 API Key**。只有对文档/论文/图片做语义抽取时才需要 LLM（Gemini Key 或 AI 助手会话），纯代码目录完全免费离线运行。

## 3. 安装与部署 <a id="install"></a>

### 3.1 安装 graphify（含 extras 注意） <a id="install-uv"></a>

**先装 uv**（graphify 依赖它做隔离安装；uv 未预装时）：

```bash
# Linux（系统 Python 受 PEP 668 保护，用 --user --break-system-packages 装到 ~/.local/bin）
python3 -m pip install --user --break-system-packages uv -i https://pypi.tuna.tsinghua.edu.cn/simple
export PATH="$HOME/.local/bin:$PATH"   # 确保 uv 进入 PATH

# Windows（PowerShell，官方脚本）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**再装 graphify（含 extras，走清华源）**：

```bash
# uv 安装（推荐，本机采用此方式；--force 用于加装/升级 extras 时覆盖）
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv tool install "graphifyy[chinese,openai]" --force

# 验证安装
graphify --version
```

uv 方式安装后，graphify 被隔离在 `~/.local/share/uv/tools/graphifyy/`（Windows 为 `C:\Users\<用户名>\AppData\Roaming\uv\tools\graphifyy\`），全局可调用 `graphify` 命令。

> **extras 互顶坑**：graphify 按功能拆分可选依赖（`[chinese]` jieba 分词、`[openai]` OpenAI 兼容客户端、`[gemini]`、`[pdf]` 等）。`uv tool install "graphifyy[chinese]"` 会把之前安装的其他 extras 顶掉——例如只装 `[chinese]` 后，语义抽取会报 `the 'openai' package is required`。**升级/加装 extras 时必须一次列出全部需要的**，并加 `--force` 覆盖。

### 3.2 中文查询分词（jieba） <a id="install-chinese"></a>

graphify 的 `query/path/explain` 检索对中文问题先分词再匹配节点。装了 jieba 用词典分词；未装则降级为「两字滑动窗口」匹配，效果差一截。本项目已安装：

```bash
uv tool install "graphifyy[chinese,openai]" --force
```

验证：`graphify query "视觉识图用什么实现的"`，首次运行会构建 jieba 词典缓存（约 0.3 秒），之后即用。

> 安装/升级类命令建议加 `UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple` 前缀走国内源（见 3.1 节）。

### 3.3 （可选）配置 Gemini 语义抽取 <a id="install-gemini"></a>

```bash
# 先安装 gemini 扩展，再设置环境变量
uv tool install "graphifyy[gemini,chinese]" --force
setx GEMINI_API_KEY "你的Key"   # 或 GOOGLE_API_KEY
```

设置后重启终端生效。未配置时语义抽取自动降级为由 AI 助手自身完成（见 4.2 节），不影响代码图谱。

### 3.4 集成到 AI 编程助手 <a id="install-agent"></a>

graphify 内置了对主流编程助手的安装命令，可把 skill 与钩子写入对应平台配置：

```bash
graphify install opencode   # 写入 AGENTS.md 说明 + 插件
graphify install claude     # 写入 CLAUDE.md + PreToolUse 钩子
graphify install cursor     # 写入 .cursor/rules/graphify.mdc
graphify uninstall opencode # 卸载（--purge 可同时删除 graphify-out/）
```

> 本项目已通过 opencode 集成，skill 位于 `~/.config/opencode/skills/graphify/`（Windows 为 `C:\Users\<用户名>\.config\opencode\skills\graphify\`），项目内由 `.opencode/` 插件支撑。

## 4. 首次构建图谱 <a id="first-run"></a>

### 4.1 图谱的两层：AST 层与语义层 <a id="two-layers"></a>

理解图谱节点构成，才能看懂「节点变多/变少」：

| 层 | 来源 | 覆盖 | 是否需要 LLM |
| --- | --- | --- | --- |
| AST 层 | tree-sitter 解析 | 代码函数、类；md 文档标题（快扫） | 否，免费离线 |
| 语义层 | LLM 抽取 | 概念（concept）、设计理由（rationale）、跨文档关联 | 是（Gemini Key 或 AI 助手） |

语义层通常是节点大头（本项目 951 节点中语义层占 712 个）。**语义层一旦删除，只有重新跑 LLM 语义抽取才能恢复**——
`graphify update` 只重建 AST 层、保留已有语义层；纯命令行无 LLM 的「彻底删除重建」会丢掉全部语义节点（见 7.3 节）。

### 4.2 语义抽取的标准流程（子代理） <a id="semantic-flow"></a>

在 AI 助手中运行 `/graphify` 时，文档语义抽取由**助手会话的模型经子代理并行完成**，这是标准做法：

1. **detect**：扫描目录，分类统计代码/文档/论文/图片/视频文件。
2. **AST 抽取（Part A）**：代码文件本地解析，与语义抽取并行。
3. **语义抽取（Part B）**：文档按 20-25 个文件分块，每块派一个子代理；子代理读取文件、按抽取规范（extraction-spec.md）输出节点/边/超边 JSON。OpenCode 平台用并行 agent 分发，全部子代理同一消息派发。
4. **合并（Part C）**：AST + 语义节点去重合并，写入 `graphify-out/.graphify_extract.json`。
5. **构建与聚类（Step 4-5）**：生成 graph.json、GRAPH_REPORT.md，并给社区命名（中文名由助手手工拟定，见 7.4 节）。
6. **输出（Step 6）**：生成 graph.html 可视化。

> token 由助手会话承担，graphify 的 `cost.json` 不记账；语义抽取结果会写入缓存（`graphify-out/cache/semantic/`），文档不变则增量更新不再重复抽取。

## 5. 输出产物说明 <a id="outputs"></a>

所有产物都在 `graphify-out/` 目录下：

| 文件 | 说明 |
| --- | --- |
| `graph.html` | 交互式图谱，浏览器直接打开，可缩放、点节点看详情（本项目已汉化界面）。 |
| `CALLFLOW.html` | 中文界面架构图（Mermaid 调用流程），`graphify export callflow-html --lang zh-CN` 生成。 |
| `graph.json` | 原始图数据（GraphRAG 就绪），供 query/path/explain 等命令查询。 |
| `GRAPH_REPORT.md` | 人话版审计报告：God Nodes、意外关联、建议问题。 |
| `.graphify_labels.json` | 社区中文名映射（cid → 名称），可视化图例与报告共用。 |
| `manifest.json` | 文件清单与语义哈希，`update` 增量更新依赖它。 |
| `cost.json` | 累计 token 成本跟踪（子代理抽取不计入）。 |
| `.graphify_python` / `.graphify_root` | 记录本次使用的 Python 解释器路径与扫描根目录（skill 内部使用）。 |
| `cache/` | AST 与语义抽取缓存，未变更文件不重复抽取。 |
| `2026-08-xx/` | graphify 自动备份的当日图谱快照（graph.json/报告/标签等）。 |

## 6. 日常使用 <a id="daily"></a>

### 6.1 自然语言查询（含中文） <a id="daily-query"></a>

```bash
graphify query "认证流程如何处理token刷新？"   # BFS 广度遍历（中文问题自动分词）
graphify query "数据如何流入审计模块？" --dfs   # DFS 深度追踪
graphify query "……" --budget 1500              # 限制回答 token 数
```

### 6.2 路径与概念 <a id="daily-path"></a>

```bash
graphify path "事件总线" "工作流"        # 两概念间最短路径（支持中文）
graphify explain "多租户路由"             # 用大白话解释某节点及其邻居
```

### 6.3 影响面与枢纽 <a id="daily-affected"></a>

```bash
graphify affected "事件总线" --depth 2   # 反向遍历：谁会被它影响
graphify god-nodes --top 10               # 架构枢纽节点排行
```

### 6.4 增量构建常用参数 <a id="daily-incremental"></a>

```bash
graphify update .                  # 只抽取新增/变更代码，免费无 LLM
graphify update . --force          # 重建后节点数变少时覆盖（大重构后使用）
graphify watch 文档/               # 监视目录，代码变更自动重建
graphify cluster-only .            # 只重跑聚类和报告
```

## 7. 维护与更新 <a id="maintain"></a>

### 7.1 排除规则（.graphifyignore） <a id="maintain-ignore"></a>

项目根目录的 `.graphifyignore`（语法同 .gitignore）控制哪些文件不进图谱：

```bash
# 本项目当前排除项
文档/资源/              # 第三方压缩 JS/CSS（mermaid.min.js 等），避免英文函数节点刷屏
.opencode/skills/graphify/   # graphify 自带英文 skill 文档，非本项目内容
```

新增排除项后运行 `graphify update --force .`，图谱会自动修剪被排除文件的节点。

### 7.2 一键收尾：汉化与架构图 <a id="maintain-finalize"></a>

graph.html 的可视化模板是固定英文界面，无法配置。本项目用一个脚本完成两件收尾（幂等，可反复执行）：

```bash
graphify update --force .        # 重建图谱
python scripts/tools/graphify/localize-graph.py   # 汉化 graph.html + 生成 CALLFLOW.html
```

脚本位置：`scripts/tools/graphify/localize-graph.py`。callflow 架构图也可单独生成：`graphify export callflow-html --lang zh-CN`（`--lang` 支持 auto 自动检测，本项目图谱以中文为主可省略）。

### 7.3 重建的取舍：语义层不可再生 <a id="maintain-rebuild"></a>

- **代码改动**：`graphify update .` 即可，AST 层重抽、语义层保留。
- **彻底删除重建（清空 graphify-out/ 后 update）**：AST 层全量重抽，但**语义层永久丢失**——文档概念节点退化为标题级，节点数大幅缩水（本项目实测 951 → 139）。恢复只能重新跑语义抽取（4.2 节）或从备份恢复。
- **备份**：重建前先整体复制 `graphify-out/` 到临时目录；graphify 自身也会按日期备份当日图谱。

### 7.4 社区命名 <a id="maintain-label"></a>

标准做法：助手阅读 `.graphify_analysis.json` 中各社区的成员标签，手工拟定 2-5 字中文名，写入 `.graphify_labels.json` 并重新生成报告与 graph.json（skill Step 5）。

## 8. 与 AI 编程助手的集成 <a id="agent"></a>

项目根目录 `AGENTS.md` 中已写入 graphify 使用规则，AI 助手会遵循（这些是运行时规则，细节见本文档）：

- 代码库问题优先 `graphify query "<问题>"`，关系用 `graphify path`，概念用 `graphify explain`——返回的子图比全文 grep 小得多。
- 有 `graphify-out/wiki/index.md` 时用其做广域导航。
- 钩子或增量更新后 graphify-out/ 变脏属正常现象，不跳过 graphify。

## 9. 常见问题 <a id="faq"></a>

| 问题 | 处理 |
| --- | --- |
| 提示需要 API Key？ | 纯代码目录不需要。文档语义抽取可选配 `GEMINI_API_KEY`，否则由 AI 助手自身完成（4.2 节）。 |
| 报 `the 'openai' package is required`？ | extras 被顶掉了，重装时一次带全：`uv tool install "graphifyy[chinese,openai]" --force`（3.1 节）。 |
| 图谱节点怎么变少了？ | 先分清 AST 层与语义层（4.1 节）。`update` 不会丢语义层；彻底删除重建才会丢，且不可再生（7.3 节）。 |
| 图谱里怎么全是英文节点？ | 多半是第三方 JS 库的函数名进了图。用 `.graphifyignore` 排除后 `update --force` 修剪（7.1 节）。 |
| graph.html 界面是英文？ | 可视化模板固定英文。运行 `scripts/tools/graphify/localize-graph.py` 汉化（7.2 节）。 |
| update 后节点变少、拒绝覆盖？ | graphify 有防缩保护（#479）。确实删了代码请加 `--force`。 |
| 报告提示 Graph Health Warning？ | 存在悬空/折叠边，图可能不完整但可用；用 `graphify diagnose multigraph` 排查。 |
| 目录太大跑不动？ | 按子目录分次构建，或加 `--no-cluster` 跳过昂贵的聚类步骤。 |
| 从 Windows 迁移到 Linux 后 `graphify` 命令找不到？ | graphify 靠 uv 安装、不随仓库迁移，需在 Linux 上重装 uv + graphify（3.1 节）；图谱产物 `graphify-out/` 已入库不受影响。装好后把 `graphify-out/.graphify_python` 改为 Linux 解释器路径（`~/.local/share/uv/tools/graphifyy/bin/python`），否则 skill 调用 Python 会失败。 |
| 如何彻底卸载？ | `uv tool uninstall graphifyy`；连同图谱一并删除用 `graphify uninstall --purge`。 |

## 10. 替代方案评估 <a id="alternatives"></a>

> 结论（2026-08-28 调研）：维持 graphify 不变；唯一值得留意的备选是 LightRAG（文档语义问答场景）。以下为选型备忘，不作为迁移计划。

graphify 的独特价值在于**同时**做了两件事：代码 AST 抽取（tree-sitter，免费离线）+ 文档语义抽取（LLM）。主流 GraphRAG 工具几乎只做「文档 → 知识图谱」的 LLM 语义抽取，**不解析代码**，因此没有一键平替。

| 工具 | 定位 | 解析代码? | 离线免费? | 与 graphify 的差距 |
| --- | --- | --- | --- | --- |
| graphify（现用） | 代码+文档→KG | ✅ AST | ✅ | — |
| Microsoft GraphRAG | 文档 GraphRAG | ❌ | 需 LLM | 社区检测+报告最接近 graphify，但文档专用、构建成本高 |
| LightRAG | 文档 GraphRAG | ❌ | 可本地 Ollama | 查询 token 成本极低（约 GraphRAG 1/6000）、支持增量更新，最贴合轻量本地诉求 |
| Cognee / Graphiti | agent 记忆 | ❌ | 可本地 | 定位是 agent 记忆，非代码/文档知识库 |
| Neo4j GraphRAG | 图库+抽取 | ❌ | 服务化 | 生态最成熟，但要搭服务 + 自己拼抽取 |
| KuzuDB | 嵌入式图数据库 | ❌ | — | 只替换「存储+查询」层，无抽取能力，且已被 Apple 收购、开源维护停止 |

**结论**：

- 代码 AST 图谱 + 中文 callflow 架构图是 graphify 独一份，无对等开源替代。
- 若未来只想对 `文档/` 规划做语义问答（不要代码图谱），再评估 LightRAG 本地版（HKUDS/LightRAG，MIT，可 Ollama 离线）。
- GraphRAG / Neo4j / KuzuDB 均与「轻量本地、离线免费」诉求相悖，不建议折腾。

> 本文档基于 graphify 0.9.51（Linux 环境）编写。项目：[github.com/safishamsi/graphify](https://github.com/safishamsi/graphify) · 生成日期：2026-08-14 · 修订：2026-08-28（Windows 迁移 Linux + 替代方案评估）