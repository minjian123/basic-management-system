# 说明：本目录存放推送前本地预检的**薄包装**（在 bms 仓库根执行）
#
# 13_05 起，选测器 / 预检引擎 / 覆盖率门禁 / 重命令包装的**唯一实现**迁入独立仓 `engkit`
# （`engkit <子命令>`，包内用例 281 条、覆盖率 100%）；本目录只保留**行为零回退的入口**：
#
# 目录内容
#   engkit_boot.py        engkit 定位：先 import，失败按 ENGKIT_HOME → 同级 ../engkit 注入 sys.path
#   check_preflight.py    预检入口：转发 `engkit preflight`（位置根 → --root）
#   run_once.py           重命令包装：转发 `engkit run_once`（缓存回放）
#   run_selected.py       定向执行器：转发 `engkit run_selected`
#   测试改动内容.py        开发环：转发 `engkit run-changed`（只跑改动相关：直接依赖测试 + 前端受影响包 + 改动文件 ruff）
#   test_selection.py     选测器：转发 `engkit selection`
#   coverage_gate.py      覆盖率门禁：转发 `engkit coverage`
#   parallel_jobs.py      `--jobs` 映射：转发 `engkit.preflight.jobs_args / describe`
#   heavy_command_guard.py 重命令拦截：转发 `engkit.guard`（判定 / 提示 / pytest 插件入口）
#   full_test_guard.py    全量测试守卫：转发 `engkit.guard`（`--full` / 显式声明 / CI 放行）
#   heavy_guard_boot.py   `.pth` 启动钩子：转发 `engkit.guard`（旧钩子文件仍可加载）
#   install_guard_hook.py 钩子安装 / 校验 / 卸载：转发 `engkit guard install-hook|check-hook|remove-hook`
#   check_ci_config.py    本仓专属：CI / 编排 YAML 解析 + pytest 选项校验 + GitLab Lint + 门禁资产
#   check_frontend_types.py 本仓专属：按变更逐包 typecheck / build
#
# 用法（在 bms 仓库根）
#   python3 scripts/tools/preflight/测试改动内容.py           # 开发环：只跑 git 改动相关（推荐改 bug 即测）
#   python3 scripts/tools/preflight/check_preflight.py            # 无参 = 快速档（只静态 + 护栏 + 自测，分钟级）
#   python3 scripts/tools/preflight/check_preflight.py --push     # 推送前定向档（静态 + 护栏 + 定向用例 + 覆盖率）
#   python3 scripts/tools/preflight/check_preflight.py --full     # 全量档（显式申请，隐含 --push）
#   python3 scripts/tools/preflight/check_preflight.py --no-cov   # 跳过覆盖率门禁
#   python3 scripts/tools/preflight/check_preflight.py --jobs 4   # 并行档位（auto 缺省 / 正整数 / off）
#   python3 scripts/tools/preflight/check_preflight.py --self-test
#   python3 scripts/tools/preflight/check_preflight.py --allow-dirty --fast   # 脏树上验证护栏本身（仅快速档）
#
# 场景闸门（2026-10-29 起）：预检是**推送前门禁**，不是开发中的反馈环。工作树有未提交改动（含未跟踪文件）
# 即拒绝执行、零步骤执行，提示改用开发环；确需在脏树上验证护栏本身，加 `--allow-dirty`（**只对快速档
# 开放**，定向 / 全量档必须干净树），并记入 `.cache/preflight/audit.jsonl` 审计：真跑 / 被拒 / 绕过三类
# 事件，写盘失败 fail-open。
#
# 开发环口径（`测试改动内容.py`，等价 `engkit run-changed`）：依赖深度 direct（不做传递闭包、
# 不退化工程级全量）、不采集覆盖率、只对改动文件跑 ruff、前端只跑直接命中包；间接依赖与覆盖率
# 由推送前定向档（闭包选测 + 100% 门禁）与 CI 全量兜底。Windows 入口同名 `.bat`、Linux 为 `.sh`。
#
# 预检步骤不再写在本目录：**步骤清单在仓根 `engkit.toml` 的 `[[preflight.steps]]`**，改步骤即改配置；
# 逐条口径（静态 / 测试段 / 基座与边界 / 契约 / 前端 / 自测按需）见该文件注释与 engkit 文档。
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
#   4. 覆盖率门禁口径见《AI开发规范》「覆盖率要求」节。
#   5. 分钟级重命令一律经 `run_once.py` 包装；只为看报错时用定向命令，不得整轮重跑。
