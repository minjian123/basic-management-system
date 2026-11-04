# 说明：本目录存放推送前本地预检的**薄包装**（在 bms 仓库根执行）
#
# 13_05 起，选测器 / 预检引擎 / 覆盖率门禁 / 重命令包装的**唯一实现**迁入独立仓 `engkit`
# （`engkit <子命令>`，包内用例 281 条、覆盖率 100%）；本目录只保留**行为零回退的入口**：
#
# 目录内容
#   engkit_boot.py        engkit 定位：先 import，失败按 ENGKIT_HOME → 同级 ../engkit 注入 sys.path
#   推送.py               推送入口：转发 `engkit push`（先预检、通过才推送；位置根 → --root）
#   提交前预检.py          提交前门禁：跑 `[[preflight.steps]]` 全部步骤、范围收敛到改动文件（`.git/hooks/pre-commit` 调用）
#   install_precommit_hook.py 提交前钩子安装 / 校验 / 卸载（`--check` / `--remove`；重装后再校验）
#   run_selected.py       定向执行器：转发 `engkit run_selected`
#   测试改动内容.py        开发环：转发 `engkit run-changed`（只跑改动相关：直接依赖测试 + 前端受影响包 + 改动文件 ruff）
#   test_selection.py     选测器：转发 `engkit selection`
#   coverage_gate.py      覆盖率门禁：转发 `engkit coverage`
#   diff_coverage_gate.py 改动行覆盖率门禁：转发 `engkit coverage-changed`（**提交环专用**：只判本次 diff
#                         触达的可执行行；推送环仍走 coverage_gate 的模块级 100%）
#   parallel_jobs.py      `--jobs` 映射：转发 `engkit.preflight.jobs_args / describe`
#   heavy_command_guard.py 重命令拦截：转发 `engkit.guard`（判定 / 提示 / pytest 插件入口）
#   full_test_guard.py    全量测试守卫：转发 `engkit.guard`（开发期间一律拒绝；仅推送入口内部授权 / CI 放行）
#   heavy_guard_boot.py   `.pth` 启动钩子：转发 `engkit.guard`（旧钩子文件仍可加载）
#   install_guard_hook.py 钩子安装 / 校验 / 卸载：转发 `engkit guard install-hook|check-hook|remove-hook`
#   check_ci_config.py    本仓专属：CI / 编排 YAML 解析 + pytest 选项校验 + GitLab Lint + 门禁资产
#   check_frontend_types.py 本仓专属：按变更逐包 typecheck / build
#   check_workspace_hygiene.py 本仓专属：工作区卫生（临时 / 日志落点自查；`--clean` 隔离到 `tmp/_quarantine/`）
#
# 用法（在 bms 仓库根）
#   python3 scripts/tools/preflight/测试改动内容.py           # 开发环：只跑 git 改动相关（推荐改 bug 即测）
#   python3 scripts/tools/preflight/推送.py                # 推送入口：预检通过即推送（档位按待推提交自动选）
#   python3 scripts/tools/preflight/推送.py --check        # 只跑预检、不推送（唯一出口）
#   python3 scripts/tools/preflight/推送.py --full         # 全量静态 + 全部自测 + 定向用例（不含全量测试；全量测试只在 CI）
#   python3 scripts/tools/preflight/推送.py --jobs 4       # 并行档位（auto 缺省 / 正整数 / off）
#
# 场景闸门与档位（2026-10-29 二次拍板）：预检是**推送的内部步骤**，本地没有独立入口——
# 手动调用 `engkit preflight` 一律拒绝（CI 环境除外）。工作树有未提交改动（含未跟踪文件）即拒绝；
# 档位按**待推提交**自动选：全为文档 → 快速档（静态 + 护栏 + 自测，秒级）；含代码 → 定向档
# （静态 + 定向用例 + 覆盖率门禁）。**全量测试只由 CI 执行**：本地 `--full` 只到全量静态 + 定向用例。
# 真跑 / 被拒两类事件记入 `.cache/preflight/audit.jsonl`（写盘失败 fail-open）。
#
# 开发环口径（`测试改动内容.py`，等价 `engkit run-changed`）：依赖深度 direct（不做传递闭包、
# 不退化工程级全量）、不采集覆盖率、只对改动文件跑 ruff、前端只跑直接命中包；间接依赖与覆盖率
# 由推送入口的定向档（闭包选测 + 100% 门禁）与 CI 全量兜底。Windows 入口同名 `.bat`、Linux 为 `.sh`。
#
# 预检步骤不再写在本目录：**步骤清单在仓根 `engkit.toml` 的 `[[preflight.steps]]`**，改步骤即改配置；
# 逐条口径（静态 / 测试段 / 基座与边界 / 契约 / 前端 / 自测按需）见该文件注释与 engkit 文档。
#
# 提交前门禁（`提交前预检.py`，装为 `.git/hooks/pre-commit`）：**步骤表与推送预检同源**（同一份
# `[[preflight.steps]]`，一步不少），范围按「能增量就增量」——
#   · 选测 → 定向执行器（选测 + 覆盖率门禁 + 扩圈），只跑改动触及的用例；其中**覆盖率按「改动行」判**
#     （只要求本次 diff 触达的可执行行被执行，未改动代码不参与；无同名测试的模块不采集、跳过），
#     模块级 100% 只由推送环 / CI 判；
#   · `ruff` / `pyright` → 只跑改动文件，且**只收 `.py` / `.pyi`**（`LINT_SUFFIXES`）：`backend/` 下的
#     `config.toml`、JSON、YAML 等非源码改动不喂给解析器——2026-11-04 曾因 TOML 被 pyright 当 Python
#     解析而把「纯配置提交」判失败；过滤只影响「哪些文件进 lint」，不放松任何 `.py` 判据；
#   · 脚本级 12 个 + 模块级 6 个步骤 → 追加 `--files-from -`，清单经**标准输入管道**喂入（不落盘，
#     回避 Windows 命令行长度上限）；是否增量由 `[[devloop.steps]]` 带 `--files-from` 自动识别；
#   · 本次改动不触及的步骤 → 记「本次改动不触及」，不跑；
#   · **只剩「前端类型」一项**因 `tsc` / `vue-tsc` 的检查单元是整个工程（还按依赖闭包带上未改动的
#     下游工程）而登记于 `FULL_SCAN_STEPS`：触及即**报错拒绝提交**，需 `--allow-full-steps` 显式放行。
# 新增预检步骤若未登记进 `RUNNABLE_STEPS` / `FULL_SCAN_STEPS`，门禁 **fail-closed 直接拒绝**——
# 不允许出现「新加一步、提交前悄悄扫全仓」。
# 门禁面只认代码 / 配置后缀（`GATED_SUFFIXES`）+ `bms文档/` 下的 `.md`（`DOC_PREFIXES`）：`scripts/`、
# `frontend/` 里的目录说明文档（`.md`）**不进门禁**——它们不是判据来源，改说明不改变行为。此口径已拍板
# （2026-11-03）：**勿把 `.md` 加进 `GATED_SUFFIXES`**，否则纯说明改动也会被拖进整条判定链。
#
# 运行前提（13_07 起）
#   本地：`uv sync` 按 git 源依赖装好 engkit 包（`backend/pyproject.toml` 的 `[tool.uv.sources]`），
#         且工作区里平级克隆 `engkit`（`../engkit`）——**ruff 规则基线是文件路径，必须读克隆**：
#         缺克隆时 ruff 直接报 `Failed to load extended configuration` 并退出码 2（不静默回落，
#         仓内也不留副本）；包不可用时 `engkit_boot.py` 仍按 `ENGKIT_HOME` → 同级克隆兜底。
#   CI：job 内 `. scripts/tools/ci/engkit_setup.sh`（按锁定 SHA 克隆 + 导出 `ENGKIT_HOME`，一处维护）；
#       `uv sync --frozen` 另按同一 rev 拉 engkit 包——克隆与包是两条都要有的路径。
#
# 关键约束（改动脚本时务必遵守）
#   1. 包内口径改在 `engkit` 仓（用例与覆盖率 100% 门禁在那侧）；本目录**不得**再写推导 / 判定逻辑。
#   2. 选测、并行、覆盖率、拦截的实现只有一份：`engkit` 的 `selection.py` / `preflight.py` /
#      `coverage.py` / `guard.py`；bms 侧护栏用例锁「包装只转发」。
#   3. 预算护栏（单步 / 总体）与步骤清单在 `engkit.toml`；改预算即改配置，不要改代码。
#   4. 覆盖率门禁口径见《AI开发规范》「覆盖率要求」节；**两环分工不同**：提交环判「改动行」
#      （`diff_coverage_gate.py` → `engkit coverage-changed`），推送环 / CI 判「模块级 100%」
#      （`coverage_gate.py` → `engkit coverage`）。
#   5. 开发期只跑改动相关（开发环）与单文件 / 单节点；宽目录 pytest、无参数 ruff / pyright
#      由重命令守卫拦下，跨模块排查走推送预检 / CI，不得整轮重跑。
#   6. **全量测试只由 CI 执行**：开发期间无目标 / 宽目录 / `--pyargs` 的 pytest 一律被全量守卫拒绝
#      （没有 `--full` / 环境变量逃生口）；前端 vitest 同口径。
