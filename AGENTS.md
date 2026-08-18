# AGENTS.md

**注意**：用户是中国人，英文看不懂，尽量使用中文。

## 项目现状

- BMS（基础管理系统）：后端管理用途。当前**尚无源代码**，规划已定案；技术栈、功能模块、开发计划与验收标准见 `文档/规划/项目规划说明.md`，**动手写代码前先读该文件**。
- 文档目录使用中文名（`文档/`），README 与规划文档均为中文；回复与文档保持中文。
- `.opencode/` 中 graphify 安装脚本生成的产物（plugins/graphify.js、skills/graphify 等）勿手动修改；`opencode.json` 的 plugin 数组登记自定义插件是既定扩展方式（bg.js 如此，vision.js 已退役），MCP server 走 `opencode.json` 的 `mcp` 段登记；`.reasonix/`、reasonix.toml 由 IDE 工具生成——勿手动修改。
- 入口文档：`README.md`（导航）、`文档/规划/项目规划说明.md`（规划）、`文档/规划/开发部署规划.html`（开发环境部署）、`文档/资料/开发服务器部署使用说明.html`（mjbk 远程操作实录）。

## 开发环境与远程操作

- 开发服务器 **mjbk**（192.168.0.107，常开：GitLab CE、开发依赖服务、MySQL/PostgreSQL/达梦 DM8 三库）与开发机 **mjpc**（192.168.0.124）。远程操作方式、SSH/WinRM 凭据与命令模板见 `文档/资料/开发服务器/开发服务器部署使用说明.html`，需要时再读，不常驻上下文。
- **服务器电源控制**（唤醒/关机工具链，文档：`文档/资料/工具/开发服务器电源控制使用说明.html`）：
  - 远程唤醒：`python deploy/tools/wol/wake_mjbk.py`（发 WOL 魔术包并等待 SSH 就绪，低风险）；双击入口 `deploy/tools/wol/唤醒mjbk.bat`。
  - 远程关机：`python deploy/tools/wol/shutdown_mjbk.py`（**破坏性操作，执行前必须经用户确认**）；双击入口 `deploy/tools/wol/关机mjbk.bat`。
  - mjbk 的 sudo 密码等凭据从 `deploy/.env` 读取（键位见 `deploy/.env.example`），脚本不硬编码密码；SSH 连接走 mjpc 公钥免密。
- 机器凭据见 `文档/用户文档/本地资源.md`（已 gitignore，**勿恢复跟踪、勿提交、勿写入其他文档**）；凭据副本统一存 `deploy/.env`（已 gitignore，勿提交，勿将 .env 内容写入其他文档）。

## 文档要求

- md 文档是用户写的，AI 生成的文档使用 html；格式与布局遵循 `文档/规范/文档生成规范.html`，**生成文档前先读该文件**。
- html 的相关图片、音频、视频等资源文件统一放到同级目录的"资源"文件夹下的同名目录中。
- 项目内全部命名（代码、数据库、API、基础设施）遵循 `文档/规范/命名规范.html`。

## 网络与镜像

- 涉及软件、组件、依赖、容器镜像等下载安装时，**优先使用国内镜像**（阿里云、清华 TUNA、中科大、华为云等），默认源访问不畅时立即切换镜像，不长时间等待。
- 常用镜像：PyPI 用阿里云/清华源、npm 用淘宝（npmmirror）源、Docker Hub 用阿里云/华为云加速器、GitHub 下载用镜像代理（如 ghproxy）、Windows 组件安装卡在微软源时改用本地/镜像分发方式。
- 安装类命令默认带国内源参数，文档与脚本中写明所用镜像地址。

## 讨论与确认（强制执行）

- **凡是待用户拍板的事项（技术选型、方案取舍、范围划分、是否执行某项修改、执行方式等），必须先逐项提出并逐一确认，严禁擅自替用户拍板——包括不得按推荐值或默认值直接执行。**
- **逐项确认必须使用 question 工具**，把本次所有待决项一次性列出（一项一个问题），每项格式固定：
  - 候选选项至少 2 个；
  - 推荐项放在第一位并标注"（推荐）"；
  - 每个选项附一句差异说明。
- 不要顾虑问题数量，问的越多越细越好；宁可把一项拆成多项，也不要合并、遗漏或简化成"你看着办"。
- 用户未明确回答的项目保持未定，不得默认通过；继续追问，直到逐项确认完毕。
- 全部确认后，把确认结果汇总成表格回显给用户，用户无异议后才进入执行。
- 执行中如出现新的待拍板事项（原确认范围外），同样先询问再执行，不得自行扩展。

## 提交与推送

- **不要擅自提交**（git commit），也不要擅自推送（git push）；完成工作后询问用户是否提交，得到明确指令后再执行。
- 用户说"提交"才提交；用户说"推送"（或确认推远程）才推送；不确定时继续询问，不猜测意图。
- 提交信息遵循《命名规范》：`type(scope): 中文描述`；只暂存本次任务相关文件，不夹带无关改动。

## graphify

本项目通过知识图谱（graphify-out/）辅助代码理解与架构分析，已启用中文查询分词。

当用户输入 `/graphify` 时，先使用已安装的 graphify skill（`.opencode/skills/graphify/SKILL.md`）或下述规则，再做其他事。

规则：

- 代码库相关问题，当 graphify-out/graph.json 存在时，先运行 `graphify query "<问题>"`（可直接用中文）。关系用 `graphify path "<A>" "<B>"`，概念用 `graphify explain "<概念>"`。返回的是范围受限的子图，通常比 GRAPH_REPORT.md 或原始 grep 输出小得多。
- 钩子或增量更新后 graphify-out/ 文件变脏属正常现象，不应因此跳过 graphify。只有任务涉及过期或错误的图输出、或用户明确不用时，才跳过。
- 若 graphify-out/wiki/index.md 存在，用它做广域导航，避免直接浏览源码。
- 仅在需要宏观架构审查、或 query/path/explain 信息不足时，才读 graphify-out/GRAPH_REPORT.md。
- 修改代码后运行 `graphify update .` 保持图谱最新（纯 AST，无 API 开销）；随后运行 `python deploy/tools/graphify/localize-graph.py` 收尾（汉化 graph.html + 生成中文架构图 CALLFLOW.html）。
- graphify 安装、排除规则、重建取舍、社区命名等细节见 `文档/资料/AI/graphify部署使用说明.html`，不在此展开。

## 本地多模态（MCP + 子代理）

让 AI 助手使用本机多模态模型的通用能力（方案文档：`文档/资料/AI/本地多模态接入方案.html`），工具链在 `deploy/tools/multimodal/`，由「MCP server + 子代理」双轨组成：

- **MCP server**（`deploy/tools/multimodal/mcp_server.py`，opencode.json 的 `mcp` 段登记，依赖 mcp 官方 SDK，用 `uv run --project deploy/tools/multimodal` 启动）暴露两个工具：
  - `multimodal_chat`：通用多模态对话——文本 + 可选图片 + 可选文本文档 + 可选系统提示，返回模型回复；主会话无视觉能力时用它看图/看文档。
  - `screenshot`：Edge/Chrome 无头截图（HTML 或 URL → PNG），为识图提供图片来源。
- **子代理 `local-helper`**（`.opencode/agent/local-helper.md`）：本地模型（LM Studio qwen3.6-35b-a3b）作为"小弟"，只读 + 命令权限（禁改文件），承担简单重复劳动——识图分析、界面走查、文本整理、交叉检查。

规则：

- **任务分级（强制）**：先评估任务难度再决定派给谁——
  - **简单重复劳动 → 本地子代理 `local-helper`**：识图描述、界面截图走查、文本格式整理、翻译、摘要、清单提取、交叉检查引用、批量重复操作。此类任务结果容错要求低，本地模型（35B）足够胜任。
  - **较难任务 → 云端子代理（task 选内置 `general` 等，走云端默认模型）**：方案设计、代码编写/重构、多步推理、需要领域判断或一致性要求的产出。
  - **核心工作 → 主会话自己处理**：决策、架构与内容定稿、涉及准确性关键的产出不外包。
  - 本地模型能力一般（35B 量化），**拿不准难度时一律不派给 local-helper**，宁可主会话自己做或派云端子代理。
- **配置即用**：MCP 配置、provider（`lmstudio`，OpenAI 兼容 127.0.0.1:1234）、子代理 model 均已固化在 `.opencode/opencode.json` 与 `.opencode/agent/`，无需每次设置环境变量；**修改配置后须重启 opencode 才生效**。
- **模板即场景**：新场景 = 在 `deploy/tools/multimodal/prompts/` 新增一个 md 模板（已有 image-understanding / general-review / prototype-review / mobile-review），`multimodal_chat` 的 `prompt` 参数直接传模板名。
- **本地模型注意**：服务为本机 LM Studio（见 `文档/用户文档/本地资源.md`）。模型是推理模型，客户端默认 `reasoning_effort: "none"` 关闭思考（否则评审几万 token 不结束）；本地模型零费用，可对同一张图反复调用、聚焦区域迭代复查（如评审报告某处不清楚，再调一次着重看该区域）。
- **评审闭环**：截图评审 → 按问题清单修正 → 重新评审，直到无高危问题。评审组合动作（多档截图 + 逐图识图 + 报告）交给子代理 `local-helper` 执行，或主会话自己组合 MCP 工具完成。
- 截图与评审报告等产物一律输出到 `temp/vision/`（已 gitignore），**不入库、不提交**；需留档时输出到项目内其他位置。
- CLI 备用：`deploy/tools/multimodal/vision_analyze.py`（识图）与 `screenshot.py`（截图）可被 bash 直接调用（子代理干活用）。

## 后台任务执行（BG，强制执行）

**背景**：bash 工具是同步阻塞的，长命令执行期间无反馈，观感"卡死"。因此对命令做分级处理，禁止长时间无反馈等待。

- 工具链在 `deploy/tools/bg/`（bg-run/bg-status/bg-stop.py），已通过 opencode 插件注册 `bg_run` / `bg_status` / `bg_stop` 三个工具（opencode.json 已登记）。
- **执行纪律**：
  - 预计 **≤10 秒**的命令（查询、状态、文件操作、短命令）：直接执行。
  - 预计 **>10 秒**的命令（下载、安装、构建、ssh 远程、服务启动、备份等）：一律 **`bg_run` 后台化** → 立即返回 → 用 **`bg_status` 秒级轮询**（间隔 10-30 秒）直到 FINISHED；绝不直接同步等待。
  - 不写长 `Start-Sleep` 等待；探测服务就绪用短超时（2-3 秒）轮询。
  - 调用 `.cmd/.bat` 批处理或 npx 时注意输出缓冲（PowerShell 管道要等进程退出才吐输出），必要时绕开包装直接用可执行文件。
- 状态文件默认 `%USERPROFILE%\.bg`（-Base 可覆盖）；任务按 `-Name` 区分，同名会覆盖。
- 示例：`bg_run {name: 远程磁盘, command: "ssh minjian@192.168.0.107 df -h"}` → 立即返回；`bg_status {name: 远程磁盘}` → 秒级出结果。
