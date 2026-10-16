# 说明：本目录存放推送前本地预检脚本（在 bms 仓库根执行）
#
# 目录内容
#   check-preflight.py   预检入口：CI 配置 / 后端静态 / 后端测试与覆盖率门禁 / 基座与边界 / 文档 /
#                        界面 / 网关 / 契约，失败汇总并在末尾给结论
#   requirements.txt     本预检的**可选**第三方依赖清单（pyyaml；未安装只影响「CI 配置自检」段）
#
# 用法（在 bms 仓库根）
#   python3 scripts/tools/preflight/check-preflight.py            # 完整预检（含覆盖率硬门禁，推送前跑）
#   python3 scripts/tools/preflight/check-preflight.py --fast     # 秒级自检（跳过 pytest，日常用）
#   python3 scripts/tools/preflight/check-preflight.py --no-cov   # 跳过覆盖率门禁
#
# 背景与完整说明见 bms 文档《AI 开发规范》（预检与覆盖率门禁口径）与仓库根 README「推送前预检」：
#   bms文档/规范/AI开发规范.md
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
#   2. 推送前跑**完整预检**（不带 --fast，含覆盖率硬门禁 100%）；--fast 只作日常快速自检。
#   3. 本目录脚本纳入 ruff 门禁（scripts/tools 全量），改动后随 preflight 静态段一并校验。
