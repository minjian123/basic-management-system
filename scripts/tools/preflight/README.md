# 说明：本目录存放推送前本地预检脚本（在 bms 仓库根执行）
#
# 目录内容
#   check-preflight.py   预检入口：CI 配置 / 后端静态 / 基座与边界 / 文档 / 界面 / 网关 / 契约，
#                        缺省按 git 变更**定向**跑受影响工程用例与变更源文件覆盖率门禁；
#                        带单步 / 总体耗时预算护栏（超时即中止）；失败汇总并在末尾给结论
#   run-once.py          重命令「短窗内只真跑一次」包装：同命令 + 同工作区指纹命中即回放上次完整输出
#                        （含退出码）；改一个源文件指纹即变，确需重跑加 --force
#   requirements.txt     本预检的**可选**第三方依赖清单（pyyaml；未安装只影响「CI 配置自检」段）
#
# 用法（在 bms 仓库根）
#   python3 scripts/tools/preflight/check-preflight.py            # 定向档（缺省快路径：静态 + 基座/边界 +
#                                                                #   受影响工程用例 + 变更源文件覆盖率 100%）
#   python3 scripts/tools/preflight/check-preflight.py --fast     # 秒级自检（跳过 pytest，日常用）
#   python3 scripts/tools/preflight/check-preflight.py --full     # 全量档（聚合全量 + 工程级范围；显式申请）
#   python3 scripts/tools/preflight/check-preflight.py --no-cov   # 跳过覆盖率门禁
#   python3 scripts/tools/preflight/check-preflight.py --self-test  # 自测定向推导与预算护栏
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
# 预算护栏：单步 / 总体耗时双上限（定向档 120s / 180s，全量档 600s / 1200s；可用
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
