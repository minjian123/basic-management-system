#!/bin/sh
# engkit 克隆准备（13_07 抽公共片段）：凡跑 ruff / pyright / 包装入口的 CI job 都需要 engkit 克隆。
#
# 用法（**source**，不是执行——需要把 ENGKIT_HOME 导给后续步骤）：
#
#     - . scripts/tools/ci/engkit_setup.sh
#
# 口径：
#   1. 按 `ENGKIT_REV` 检出：**缺省 `main` = 每次取 engkit 远端 main 头**（与本地「路径依赖、改基座即时
#      生效」同口径，升级零维护；2026-10-28 用户拍板取代此前的固定 SHA 锁定）。需要钉版本时把
#      `ENGKIT_REV` 给成分支 / 标签 / 提交 SHA；
#   2. 克隆地址用 `CI_SERVER_URL`（含协议与端口）——`CI_SERVER_HOST` 不含端口，拼出来会连到 :80 超时；
#   3. runner 工作区跨作业复用：已有克隆即只做 fetch + checkout，不重复下载；复用目录里的 origin 存的是
#      **上一次 job** 的 URL（含当时的 `CI_JOB_TOKEN`），故每次先 `remote set-url` 再 fetch；
#   4. 本仓 ruff 基线 `extend = "../../engkit/toolchain/ruff-base.toml"` 读的是**文件路径**
#      （ruff 读不了安装包内资源），故克隆与 `uv sync` 拉的 engkit 包是**两条都要有**的路径。

ENGKIT_REPO_ROOT="${CI_PROJECT_DIR:-$(cd "$(dirname "$0")/../../.." && pwd)}"
ENGKIT_CLONE_DIR="${ENGKIT_REPO_ROOT}/../engkit"
ENGKIT_REF="${ENGKIT_REV:-main}"

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

fetch_all() {
    # 拉全部分支 / 标签：`main` 取到最新头，显式 SHA 也能借此补齐对象；网络抖动时不立刻判死（下面验对象）
    git -C "${ENGKIT_CLONE_DIR}" fetch --quiet --prune origin \
        "+refs/heads/*:refs/remotes/origin/*" "+refs/tags/*:refs/tags/*" || true
}

has_commit() {
    git -C "${ENGKIT_CLONE_DIR}" rev-parse --verify --quiet "${1}^{commit}" >/dev/null 2>&1
}

clone_engkit
# 复用目录里 origin 存的是**上一次 job** 的 URL（含当时的 CI_JOB_TOKEN，每个 job 都不同），
# 直接 fetch 会 401/403 并误触发「删除重克隆」（2026-10-28 #1281 实测）——先刷新 remote URL。
if [ -n "${ENGKIT_URL}" ]; then
    git -C "${ENGKIT_CLONE_DIR}" remote set-url origin "${ENGKIT_URL}"
fi
fetch_all

case "${ENGKIT_REF}" in
    main | latest) TARGET="origin/main" ;;
    *) TARGET="${ENGKIT_REF}" ;;
esac

# runner 工作区跨作业复用：已有克隆可能残缺（历史 shallow / 中途失败），缺对象则删除重克隆
if ! has_commit "${TARGET}"; then
    echo "[engkit] 已有克隆缺 ${TARGET} 的对象，删除重克隆：${ENGKIT_CLONE_DIR}"
    rm -rf "${ENGKIT_CLONE_DIR}"
    clone_engkit
    fetch_all
fi
if ! has_commit "${TARGET}"; then
    echo "[engkit] 克隆仍缺 ${TARGET}：请核对 ENGKIT_REV 是否为远端可达的分支 / 标签 / 提交" >&2
    exit 1
fi
git -C "${ENGKIT_CLONE_DIR}" checkout --quiet --force --detach "${TARGET}"

ENGKIT_HOME="${ENGKIT_CLONE_DIR}"
export ENGKIT_HOME
echo "[engkit] 克隆就绪：${ENGKIT_HOME} @ ${ENGKIT_REF}（$(git -C "${ENGKIT_CLONE_DIR}" rev-parse --short HEAD)）"
