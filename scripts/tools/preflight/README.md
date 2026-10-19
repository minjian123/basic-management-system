# 说明：本目录存放推送前本地预检脚本（在 bms 仓库根执行）
#
# 目录内容
#   check-preflight.py   预检入口：CI 配置 / 后端静态 / 基座与边界 / 文档 / 界面 / 网关 / 契约，
#                        缺省按 git 变更**定向**跑受影响工程用例与变更源文件覆盖率门禁；
#                        带单步 / 总体耗时预算护栏（超时即中止）；失败汇总并在末尾给结论
#   run-once.py          重命令「短窗内只真跑一次」包装：同命令 + 同工作区指纹命中即回放上次完整输出
#                        （含退出码）；改一个源文件指纹即变，确需重跑加 --force
#   test_selection.py    选测器（单一来源）：变更 → 受影响测试文件 / 前端包。后端＝目录同构 + AST
#                        导入图双重收敛 + 基础模块显式退化；前端＝workspace:* 依赖反向闭包 +
#                        根配置全包退化。预检与 CI 四个 job 共用，禁止另写映射规则
#   run-selected.py      选测执行器：推导 → 跑 pytest → 读覆盖率缺口 → 扩圈（最多 2 轮）→ 退化兜底 → 度量
#   parallel_jobs.py     并行档位解析（--jobs → -n）：预检与执行器单一来源（13_02）
#   coverage_gate.py     覆盖率门禁：合并并行采集数据、导出 JSON 并判定「行 + 分支 100%」（13_02）
#   requirements.txt     本预检的**可选**第三方依赖清单（pyyaml；未安装只影响「CI 配置自检」段）
#
# 用法（在 bms 仓库根）
#   python3 scripts/tools/preflight/check-preflight.py            # 定向档（缺省快路径：静态 + 基座/边界 +
#                                                                #   受影响工程用例 + 变更源文件覆盖率 100%）
#   python3 scripts/tools/preflight/check-preflight.py --fast     # 秒级自检（跳过 pytest，自测全跑，日常用）
#   python3 scripts/tools/preflight/check-preflight.py --full     # 全量档（聚合全量 + 工程级范围；显式申请）
#   python3 scripts/tools/preflight/check-preflight.py --no-cov   # 跳过覆盖率门禁
#   python3 scripts/tools/preflight/check-preflight.py --jobs 4   # 并行档位（auto 缺省 / 正整数 / off 串行）
#   python3 scripts/tools/preflight/check-preflight.py --self-test  # 自测定向推导、预算与自测登记
#
# 并行执行（13_02）
#   --jobs auto|N|off（缺省 auto）同时作用于定向档执行器与全量档两条 pytest 调用；CI 显式传 --jobs auto。
#   并行安全的根：pytest-xdist 下测试基座按 PYTEST_XDIST_WORKER 注入独立 BMS_DATABASE__SQLITE_DIR
#   （<basetemp>/sqlite-<worker>），SQLite 文件库不再跨 worker 共享；串行不注入（沿配置原值）。
#
# 覆盖率采集（13_02）
#   采集由 backend/bms_testing_plugin.py 在**被测模块导入前**启动（pytest addopts 的 -p 入口），
#   每个进程落一份 <data-file>.<pid>；结束后由 coverage_gate.py 合并并判定「行 + 分支 100%」。
#   不要再用 `pytest --cov` / `--cov-fail-under`：探针晚于 conftest 与包导入，导入期执行的行会整片
#   漏计（实测全仓曾停在 93.36%，改用本口径后同一批用例为 100%）。
#   env：BMS_COVERAGE_DATA=<数据文件基址>、BMS_COVERAGE_SOURCE=<逗号分隔的顶层包>。
#
# 自测按需（13_02）
#   7 个 --self-test 步按「脚本自身 + 依赖前缀」映射表判定（脚本自身 / backend/libs/bms_core/ /
#   bms文档/设计/原型设计/），未触及逐条打印「跳过（变更未触及 …）」；--fast / --full 档全跑；
#   变更基准不可判定（git 命令均失败）时全跑，不静默跳过。
#
# 选测器 / 执行器（单一来源，预检与 CI 共用；13_01 / 13_02）
#   python3 scripts/tools/preflight/test_selection.py --changed-from origin/main --format json
#   python3 scripts/tools/preflight/test_selection.py --scope frontend --changed-from origin/main --format packages
#   python3 scripts/tools/preflight/test_selection.py --changed-from origin/main --format changed-services
#   python3 scripts/tools/preflight/run-selected.py --changed-from origin/main   # 跑选中的测试 + 覆盖率门禁 + 扩圈
#   退化（全局配置 / 基础模块 / 无引用者 / 基准不可解析）一律显式打印原因，不做「假精细」；
#   扩圈最多 2 轮，不收敛退化工程级全量；门禁口径恒为变更模块的行 + 分支 100%。
#   覆盖率目标不再排除任何模块（采集前置后插件入口与 fixtures 均可观测）。
#
# CI 重复面（13_02）
#   service-test 用 --format changed-services 判定本服务是否有**直接变更**；仅共享底座
#   （uv.lock / Dockerfile / libs 等）变更时跳过本服务测试（由 backend-test 兜底），build / release 照常；
#   基准不可解析或判定失败时保守执行（宁可重复不漏测）。
#
# 重命令「跑一次」（run-once.py）——防重复消耗
#   分钟级命令（预检 / 全量 pytest / 全仓 ruff / pyright）第一次已给出结论后，再为「从输出里挑
#   几行报错」整轮重跑是纯浪费。本包装把这条变成技术约束：缓存键 =「命令 + 工作目录 + 工作区指纹」，
#   工作区指纹 = HEAD + 全部已跟踪变更与未跟踪文件内容哈希（**改一个源文件即失效**）；
#   窗口内（缺省 30 分钟）命中直接回放上次完整输出与退出码并标注「回放」。
#   要看具体报错时，改用**定向**命令（单文件 ruff / pyright / 单目录 pytest），不要整轮重跑重命令。
#   python3 scripts/tools/preflight/run-once.py -- python3 scripts/tools/preflight/check-preflight.py
#   python3 scripts/tools/preflight/run-once.py --show -- <命令...>    # 只看缓存状态
#   python3 scripts/tools/preflight/run-once.py --force -- <命令...>   # 改完代码立刻重验
#   python3 scripts/tools/preflight/run-once.py --window-seconds 600 -- <命令...>
#   缓存落 `.cache/run-once/`（`.gitignore` 已忽略 `.cache`），不入库。
#
# 预算护栏：单步 / 总体耗时双上限（定向档 300s / 420s，全量档 900s / 1800s；可用
#   --step-seconds / --budget-seconds 覆盖）；超时立即中止并提示「全量交 CI」。
# 背景与完整说明见 bms 文档《AI 开发规范》（覆盖率与验收口径）、《测试规范》「执行方式」节
# 与仓库根 README「推送前预检」：
#   bms文档/规范/AI开发规范.md
#   bms文档/规范/测试规范.md
#   README.md
#
# 可选依赖（pyyaml）
#   仅「CI 配置自检」段需要：把 CI / 编排 YAML（.gitlab-ci.yml、deploy/ci/templates/*.yml、
#   deploy/compose/*.yml）解析成结构校验语法，并核对 backend-test 里 uv run pytest 的长选项
#   （防 --kiwicms 之类拼错）。未安装时该段打印「跳过（本机无 pyyaml）」并整段跳过（连同
#   release.py / 契约门禁资产的存在性检查也一并不查），其余检查照常；CI 侧自带环境不受影响。
#   安装（国内镜像，装到本机 python3）：
#     python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
#
# 关键约束（改动脚本时务必遵守）
#   1. 一律在 bms 仓库根执行：脚本按传入的仓库根 / 当前目录定位 .gitlab-ci.yml、backend/ 等。
#   2. 缺省即**定向档**（本地不缺省跑全量）；**全量档须显式 `--full`**，`--fast` 只作秒级静态自检。
#      定向范围由 git 变更推导（受影响工程测试目录 + 变更源文件覆盖率 100%），全量与集成交 CI。
#   3. 预算护栏（单步 / 总体耗时）不得为提高本地耗时而放宽；确需长跑请显式 `--full` 或交 CI。
#   4. 本目录脚本纳入 ruff 门禁（scripts/tools 全量），改动后随 preflight 静态段一并校验。
#   5. 分钟级重命令一律经 run-once.py 调用；只为看报错时用定向命令，不得整轮重跑（见上节）。
#   6. 「变更 → 受影响测试 / 前端包」只在 test_selection.py 维护一处：预检、CI 四个 job 与前端
#      三个 job 都只经该 CLI / run-selected.py 取值，不得在别处再写映射规则（13_01）。
#   7. 并行档位只在 parallel_jobs.py 解析一处：预检、run-selected 与 CI 都经它取 `-n` 参数；
#      自测按需的触发映射只在 check-preflight.py 的 `_SELF_TESTS` 维护一处（13_02）。
