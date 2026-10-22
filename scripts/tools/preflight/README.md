# 说明：本目录存放推送前本地预检的**薄包装**（在 bms 仓库根执行）
#
# 13_05 起，选测器 / 预检引擎 / 覆盖率门禁 / 重命令包装的**唯一实现**迁入独立仓 `engkit`
# （`engkit <子命令>`，包内用例 281 条、覆盖率 100%）；本目录只保留**行为零回退的入口**：
#
# 目录内容
#   engkit_boot.py        engkit 定位：先 import，失败按 ENGKIT_HOME → 同级 ../engkit 注入 sys.path
#   check-preflight.py    预检入口：转发 `engkit preflight`（位置根 → --root）
#   run-once.py           重命令包装：转发 `engkit run-once`（缓存回放）
#   run-selected.py       定向执行器：转发 `engkit run-selected`
#   test_selection.py     选测器：转发 `engkit selection`
#   coverage_gate.py      覆盖率门禁：转发 `engkit coverage`
#   parallel_jobs.py      `--jobs` 映射：转发 `engkit.preflight.jobs_args / describe`
#   heavy_command_guard.py 重命令拦截：转发 `engkit.guard`（判定 / 提示 / pytest 插件入口）
#   full_test_guard.py    全量测试守卫：转发 `engkit.guard`（`--full` / 显式声明 / CI 放行）
#   heavy_guard_boot.py   `.pth` 启动钩子：转发 `engkit.guard`（旧钩子文件仍可加载）
#   install-guard-hook.py 钩子安装 / 校验 / 卸载：转发 `engkit guard install-hook|check-hook|remove-hook`
#   check-ci-config.py    本仓专属：CI / 编排 YAML 解析 + pytest 选项校验 + GitLab Lint + 门禁资产
#   check-frontend-types.py 本仓专属：按变更逐包 typecheck / build
#
# 用法（在 bms 仓库根）
#   python3 scripts/tools/preflight/check-preflight.py            # 定向档（缺省快路径）
#   python3 scripts/tools/preflight/check-preflight.py --fast     # 秒级自检（跳过测试段，自测全跑）
#   python3 scripts/tools/preflight/check-preflight.py --full     # 全量档（显式申请）
#   python3 scripts/tools/preflight/check-preflight.py --no-cov   # 跳过覆盖率门禁
#   python3 scripts/tools/preflight/check-preflight.py --jobs 4   # 并行档位（auto 缺省 / 正整数 / off）
#   python3 scripts/tools/preflight/check-preflight.py --self-test
#
# 预检步骤不再写在本目录：**步骤清单在仓根 `engkit.toml` 的 `[[preflight.steps]]`**，改步骤即改配置；
# 逐条口径（静态 / 测试段 / 基座与边界 / 契约 / 前端 / 自测按需）见该文件注释与 engkit 文档。
#
# 运行前提
#   本地：工作区里平级克隆 `engkit`（`../engkit`），或 `pip install engkit`，或设 `ENGKIT_HOME`；
#   CI：job 内按锁定 SHA 克隆并 `export ENGKIT_HOME`（见 `.gitlab-ci.yml` 各 job 的 engkit 接入段）。
#
# 关键约束（改动脚本时务必遵守）
#   1. 包内口径改在 `engkit` 仓（用例与覆盖率 100% 门禁在那侧）；本目录**不得**再写推导 / 判定逻辑。
#   2. 选测、并行、覆盖率、拦截的实现只有一份：`engkit` 的 `selection.py` / `preflight.py` /
#      `coverage.py` / `guard.py`；bms 侧护栏用例锁「包装只转发」。
#   3. 预算护栏（单步 / 总体）与步骤清单在 `engkit.toml`；改预算即改配置，不要改代码。
#   4. 覆盖率门禁口径见《AI开发规范》「覆盖率要求」节。
#   5. 分钟级重命令一律经 `run-once.py` 包装；只为看报错时用定向命令，不得整轮重跑。
