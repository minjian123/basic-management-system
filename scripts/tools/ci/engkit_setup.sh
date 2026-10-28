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
ENGKIT_REF="${ENGKIT_REV:-729be9da3db53c4de5cdddddf9d77a4a652dae81}"

ENGKIT_SCHEME="${CI_SERVER_URL%%://*}"
ENGKIT_HOSTPORT="${CI_SERVER_URL#*://}"
if [ -n "${CI_SERVER_URL}" ]; then
    ENGKIT_DEFAULT_URL="${ENGKIT_SCHEME}://gitlab-ci-token:${CI_JOB_TOKEN:-}@${ENGKIT_HOSTPORT}/bms/engkit.git"
else
    ENGKIT_DEFAULT_URL=""
fi
ENGKIT_URL="${ENGKIT_REPO_URL:-${ENGKIT_DEFAULT_URL}}"

clone_engkit() {
    if [ ! -d "${ENGKIT_CLONE_DIR}/.git" ]; then
        if [ -z "${ENGKIT_URL}" ]; then
            echo "[engkit] 缺少仓库地址：CI 外运行请设 ENGKIT_REPO_URL（或 CI_SERVER_URL + CI_JOB_TOKEN）" >&2
            exit 1
        fi
        git clone --quiet --no-checkout "${ENGKIT_URL}" "${ENGKIT_CLONE_DIR}"
    fi
}

has_tree() {
    git -C "${ENGKIT_CLONE_DIR}" cat-file -e "${ENGKIT_REF}^{tree}" 2>/dev/null
}

clone_engkit
# runner 工作区跨作业复用：已有克隆可能残缺（历史 shallow / 中途失败），先补齐对象再 checkout。
# 2026-10-28 实测：残留克隆里缺锁定 rev 的 tree，直接 checkout 报
# `fatal: unable to read tree (<sha>)`，故先验对象、缺则补拉、仍缺则重克隆。
if ! has_tree; then
    echo "[engkit] 已有克隆缺 ${ENGKIT_REF} 的对象，补拉全部分支 / 标签"
    git -C "${ENGKIT_CLONE_DIR}" fetch --quiet --prune origin \
        "+refs/heads/*:refs/remotes/origin/*" "+refs/tags/*:refs/tags/*" || true
fi
if ! has_tree; then
    echo "[engkit] 补拉后仍缺对象，删除重克隆：${ENGKIT_CLONE_DIR}"
    rm -rf "${ENGKIT_CLONE_DIR}"
    clone_engkit
fi
if ! has_tree; then
    echo "[engkit] 克隆仍缺 ${ENGKIT_REF}：请核对 ENGKIT_REV 是否为远端可达提交" >&2
    exit 1
fi
git -C "${ENGKIT_CLONE_DIR}" checkout --quiet "${ENGKIT_REF}"

ENGKIT_HOME="${ENGKIT_CLONE_DIR}"
export ENGKIT_HOME
echo "[engkit] 克隆就绪：${ENGKIT_HOME} @ ${ENGKIT_REF}"
