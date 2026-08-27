# AGENTS.md

**注意1**：用户是中国人，英文看不懂，尽量使用中文。
**注意2**：如果缺乏对应知识，就去网上查资料。

## 项目现状

- BMS（基础管理系统）：后端管理用途。当前**尚无源代码**，规划已定案；技术栈、功能模块、开发计划与验收标准见 `文档/规划/项目规划说明.md`，**动手写代码前先读该文件**。
- 文档目录使用中文名（`文档/`），README 与规划文档均为中文；回复与文档保持中文。
- `.opencode/` 中 graphify 安装脚本生成的产物（plugins/graphify.js、skills/graphify 等）勿手动修改；`opencode.json` 的 plugin 数组登记自定义插件是既定扩展方式（bg.js 如此，vision.js 已退役），MCP server 走 `opencode.json` 的 `mcp` 段登记；`.reasonix/`、reasonix.toml 由 IDE 工具生成——勿手动修改。
- 入口文档：`README.md`（导航）、`文档/文档首页.md`（全量导航）、`文档/规划/项目规划说明.md`（规划）、`文档/规划/开发部署规划.md`（开发环境部署）、`文档/资料/开发服务器/开发服务器部署使用说明.md`（mjbk 远程操作实录）。

## 开发环境与远程操作

- 开发服务器 **mjbk**（常开：GitLab CE、开发依赖服务、MySQL/PostgreSQL/达梦 DM8 三库）与开发机 **mjpc**。远程操作方式、SSH/WinRM 凭据与命令模板见 `文档/资料/开发服务器/开发服务器部署使用说明.md`（内网 IP 与账号见 `文档/用户文档/本地资源.md`），需要时再读，不常驻上下文。
- **服务器电源控制**（唤醒/关机工具链，文档：`文档/资料/工具/开发服务器电源控制使用说明.md`）：
  - 远程唤醒：`python scripts/tools/wol/wake_mjbk.py`（发 WOL 魔术包并等待 SSH 就绪，低风险）；双击入口 `scripts/tools/wol/唤醒mjbk.bat`。
  - 远程关机：`python scripts/tools/wol/shutdown_mjbk.py`（**破坏性操作，执行前必须经用户确认**）；双击入口 `scripts/tools/wol/关机mjbk.bat`。
  - mjbk 的 sudo 密码等凭据从 `deploy/.env` 读取（键位见 `deploy/.env.example`），脚本不硬编码密码；SSH 连接走 mjpc 公钥免密。
- 机器凭据见 `文档/用户文档/本地资源.md`（已 gitignore，**勿恢复跟踪、勿提交、勿写入其他文档**）；凭据副本统一存 `deploy/.env`（已 gitignore，勿提交，勿将 .env 内容写入其他文档）。

## 文档要求

- 格式与布局遵循 `文档/规范/文档生成规范.md`，**生成文档前先读该文件**。
- 图形按形态选画法（该文件 7.7 节）：**逻辑图形**（流程/时序/状态/类/关系/甘特）一律 mermaid；**目录树、文件清单**等罗列型内容用框线文本目录清单（`└├│─` + 行尾 `#` 注释），不得画成 mermaid（mindmap / graph TD）；**线框图/可交互原型**用 html 资产。
- HTML 正文文档已全部迁 md（2026-08-20）：正文 md，线框图与可交互原型留 html 资产。
- md 在 VS Code 预览 mermaid 需安装 "Markdown Preview Mermaid" 扩展。
- html 的相关图片、音频、视频等资源文件统一放到同级目录的"资源"文件夹下的同名目录中。
- 项目内全部命名（代码、数据库、API、基础设施）遵循 `文档/规范/命名规范.md`。
- **公开文档红线**：随仓库推送到 GitHub 的文档（README.md、LICENSE 等）不得出现本地资源信息——开发服务器/开发机名称、内网 IP、端口、磁盘与目录、SSH/服务账号等一律不写，只保留泛化描述并指向本地文档（如《开发服务器部署使用说明》）；本地资源细节只允许存在于已 gitignore 的凭据文档与内网部署文档中。

## 网络与镜像

- 涉及软件、组件、依赖、容器镜像等下载安装时，**优先使用国内镜像**（阿里云、清华 TUNA、中科大、华为云等），默认源访问不畅时立即切换镜像，不长时间等待。
- 常用镜像：PyPI 用阿里云/清华源、npm 用淘宝（npmmirror）源、Docker Hub 用阿里云/华为云加速器、Windows 组件安装卡在微软源时改用本地/镜像分发方式。
- **GitHub 加速用 ghfast.top**（实测有效）：前缀拼接法——`https://ghfast.top/https://github.com/<owner>/<repo>`，支持 release 下载与 `git ls-remote --tags`；取最新版本号用 `git ls-remote --tags <加速URL> | tail`（GitHub API 不走镜像代理）。mirror.ghproxy.com 已实测失效（页面抓不到 tag、API 不可代理），勿再用。
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
- **两级指令独立确认（2026-08-23 修订）**：说"提交"只做 commit；说"推送"只做 push 至 main。单人开发期**直推 main，不走 MR**（纯文档改动 CI 自动跳过；含代码改动 main 自动跑冒烟验证）。
- **MR 流程暂缓（2026-08-23）**：MR 创建、合并按钮红线、MR 描述三要素、核心模块 AI 交叉评审等条款（2026-08-22 定稿）整体暂缓——单人开发且尚无基本产品，MR 门禁收益为零、流程开销显著；待产品成型或团队扩为多人协作时恢复，详见《Git协作规范》暂缓说明。

## graphify

本项目通过知识图谱（graphify-out/）辅助代码理解与架构分析，已启用中文查询分词。

当用户输入 `/graphify` 时，先使用已安装的 graphify skill（`.opencode/skills/graphify/SKILL.md`）或下述规则，再做其他事。

规则：

- 代码库相关问题，当 graphify-out/graph.json 存在时，先运行 `graphify query "<问题>"`（可直接用中文）。关系用 `graphify path "<A>" "<B>"`，概念用 `graphify explain "<概念>"`。返回的是范围受限的子图，通常比 GRAPH_REPORT.md 或原始 grep 输出小得多。
- 钩子或增量更新后 graphify-out/ 文件变脏属正常现象，不应因此跳过 graphify。只有任务涉及过期或错误的图输出、或用户明确不用时，才跳过。
- 若 graphify-out/wiki/index.md 存在，用它做广域导航，避免直接浏览源码。
- 仅在需要宏观架构审查、或 query/path/explain 信息不足时，才读 graphify-out/GRAPH_REPORT.md。
- 修改代码后运行 `graphify update .` 保持图谱最新（纯 AST，无 API 开销）；随后运行 `python scripts/tools/graphify/localize-graph.py` 收尾（汉化 graph.html + 生成中文架构图 CALLFLOW.html）。
- graphify 安装、排除规则、重建取舍、社区命名等细节见 `文档/资料/AI/graphify部署使用说明.md`，不在此展开。


## 后台任务执行（BG，强制执行）

**背景**：bash 工具是同步阻塞的，长命令执行期间无反馈，观感"卡死"。因此对命令做分级处理，禁止长时间无反馈等待。

- 工具链在 `scripts/tools/bg/`（bg-run/bg-status/bg-stop/bg-wait.py），插件文件为 `.opencode/plugins/bg.js`（注册 `bg_run` / `bg_status` / `bg_wait` / `gl_watch_pipeline` / `bg_stop` 五个工具；python 脚本留在 scripts/tools/bg/，插件内按相对路径调用。注意：opencode 插件的相对路径基于 `.opencode/` 解析，且依赖包须位于 `.opencode/node_modules` 可解析范围）。
- **执行纪律**：
  - 预计 **≤10 秒**的命令（查询、状态、文件操作、短命令）：直接执行。
  - 预计 **>10 秒**的命令（下载、安装、构建、ssh 远程、服务启动、备份等）：一律 **`bg_run` 后台化** → 立即返回 → 用 **`bg_status` 秒级轮询**（间隔 10-30 秒）直到 FINISHED；绝不直接同步等待。
  - 发起 `bg_run` 后需要拿到结果才能继续时，用 **`bg_wait`** 阻塞等待到终态（带超时上限，默认 600 秒），替代手动反复 `bg_status` 轮询。
  - GitLab 流水线结果用 **`gl_watch_pipeline`**（内部自动走 bg 链路盯守到终态；凭据读 deploy/.env 的 GITLAB_API_*），不手动拼 API 轮询。
  - 不写长 `Start-Sleep` 等待；探测服务就绪用短超时（2-3 秒）轮询。
  - 调用 `.cmd/.bat` 批处理或 npx 时注意输出缓冲（PowerShell 管道要等进程退出才吐输出），必要时绕开包装直接用可执行文件。
- 状态文件默认 `%USERPROFILE%\.bg`（-Base 可覆盖）；任务按 `-Name` 区分，同名会覆盖。
- 示例：`bg_run {name: 远程磁盘, command: "ssh <账号>@<mjbk-IP> df -h"}` → 立即返回；`bg_status {name: 远程磁盘}` → 秒级出结果。

## 缺陷工具链（defect）

CI 自动化测试失败时的缺陷处理工具链在 `scripts/tools/defect/`（流程与口径详见《测试规范》第 9 节）：

- `defect_capture.py`：归档 REPRO 复现包（现场 dump + 失败堆栈 + repro.json + REPRO.md，默认 `/mnt/data/backup/defects/<缺陷ID>/`）并自动创建/复用 GitLab Issue（fingerprint 去重、`defect-auto` 标签）。
- `ai_fix.py`：AI 修复代理——扫描 defect-auto 未关闭 Issue 定位根因生成补丁，本地模型（LM Studio）优先、云端兜底；bot 推 `fix/defect-*` 分支提 MR，**人工 review 合入、人工关闭**。
- `reproduce.py`：按 commit 检出 + dump 导入 + 跑用例的一键复现验证。

## 设计文档编号重排（reorder-design）

调整设计文档体系节点编号时**勿手动改名**，用 `scripts/tools/reorder-design/reorder-design.py`：阅读顺序定义在同目录 `order.json`（覆盖架构/概要/布局/原型四体系），自动完成两步法重命名 + 全库引用替换（支持 md 与 html）；先 `--dry-run` 预览再执行；md 总览的节点表行序不自动排序，执行后人工核对。
