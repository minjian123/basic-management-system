#!/bin/sh
# engkit 克隆准备（13_07 抽公共片段）：凡跑 ruff / pyright / 包装入口的 CI job 都需要 engkit 克隆。
#
# 用法（**source**，不是执行——需要把 ENGKIT_HOME 导给后续步骤）：
#
#     - . scripts/tools/ci/engkit_setup.sh
#
# 口径：
#   1. 按 `ENGKIT_REV` 检出（缺省值即本文件下方一处）；升级只改这里 + 各仓 pyproject 的 `rev`；
#   2. 克隆地址用 `CI_SERVER_URL`（含协议与端口）——`CI_SERVER_HOST` 不含端口，拼出来会连到 :80 超时；
#   3. runner 工作区跨作业复用：已有克隆即只做 checkout，不重复下载；
#   4. 本仓 ruff 基线 `extend = "../../engkit/toolchain/ruff-base.toml"` 读的是**文件路径**
#      （ruff 读不了安装包内资源），故克隆与 `uv sync` 拉的 engkit 包是**两条都要有**的路径。

ENGKIT_REPO_ROOT="${CI_PROJECT_DIR:-$(cd "$(dirname "$0")/../../.." && pwd)}"
ENGKIT_CLONE_DIR="${ENGKIT_REPO_ROOT}/../engkit"
ENGKIT_REF="${ENGKIT_REV:-a880f5660b108fa8d23ce317bd5990f359b25266}"

if [ ! -d "${ENGKIT_CLONE_DIR}/.git" ]; then
    ENGKIT_SCHEME="${CI_SERVER_URL%%://*}"
    ENGKIT_HOSTPORT="${CI_SERVER_URL#*://}"
    ENGKIT_DEFAULT_URL="${ENGKIT_SCHEME}://gitlab-ci-token:${CI_JOB_TOKEN:-}@${ENGKIT_HOSTPORT}/bms/engkit.git"
    git clone --quiet --no-checkout "${ENGKIT_REPO_URL:-${ENGKIT_DEFAULT_URL}}" "${ENGKIT_CLONE_DIR}"
fi
git -C "${ENGKIT_CLONE_DIR}" checkout --quiet "${ENGKIT_REF}"

ENGKIT_HOME="${ENGKIT_CLONE_DIR}"
export ENGKIT_HOME
echo "[engkit] 克隆就绪：${ENGKIT_HOME} @ ${ENGKIT_REF}"
