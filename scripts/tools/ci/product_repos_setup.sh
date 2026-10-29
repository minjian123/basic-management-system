#!/bin/sh
# 产品仓克隆准备（07B `04_02`）：把 `PRODUCT_REPOS` 声明的产品仓克隆到 CI 工作区**仓库树之外**。
#
# 用法（**执行**，不是 source——本脚本不导出任何变量）：
#
#     - sh scripts/tools/ci/product_repos_setup.sh
#
# 口径：
#   1. **仓库地址 / 分支 / 目录一律由 CI 变量声明，不写进仓库文件**（需求 04-2 内容 1）：
#      `PRODUCT_REPOS`（逗号分隔，元素可带组段 `group/repo`；**无缺省，未配置即报错**）、
#      `PRODUCT_REV`（分支 / 标签，缺省 `main`）、`PRODUCT_REPO_BASE_URL`（自建 GitLab / 迁移时覆盖基址）；
#   2. 落点 `$CI_PROJECT_DIR/../product/<repo>`：与 `engkit` 克隆同级，**不落仓库树**（不受工作区卫生护栏约束）；
#   3. runner 工作区跨作业复用：已有克隆先 `remote set-url` 再 `fetch`——复用目录里的 origin 存的是
#      上一次 job 的 URL（含当时的 `CI_JOB_TOKEN`，每个 job 都不同），直接 fetch 会 401/403；
#   4. 任一仓失败即非零退出：是否放行由调用方按 `CROSS_REPO_ALLOW_MISSING` 判定（不在此静默吞错）；
#   5. 打印每个仓的实际 HEAD，失败复现用。

PRODUCT_SETUP_ROOT="${CI_PROJECT_DIR:-$(cd "$(dirname "$0")/../../.." && pwd)}"
PRODUCT_CLONE_BASE="${PRODUCT_REPO_DIR:-${PRODUCT_SETUP_ROOT}/../product}"
PRODUCT_REF="${PRODUCT_REV:-main}"
PRODUCT_LIST="${PRODUCT_REPOS:-}"

if [ -z "${PRODUCT_LIST}" ]; then
    echo "[product] 未声明 PRODUCT_REPOS：请在项目 CI/CD 变量里配置（逗号分隔 group/repo），本仓库文件不写产品仓地址" >&2
    exit 1
fi

if [ -n "${PRODUCT_REPO_BASE_URL:-}" ]; then
    PRODUCT_BASE="${PRODUCT_REPO_BASE_URL%/}"
else
    PRODUCT_SCHEME="${CI_SERVER_URL%%://*}"
    PRODUCT_HOSTPORT="${CI_SERVER_URL#*://}"
    if [ -z "${CI_SERVER_URL:-}" ]; then
        echo "[product] 缺少 CI_SERVER_URL：CI 外运行请显式给 PRODUCT_REPO_BASE_URL" >&2
        exit 1
    fi
    PRODUCT_BASE="${PRODUCT_SCHEME}://gitlab-ci-token:${CI_JOB_TOKEN:-}@${PRODUCT_HOSTPORT}"
fi

mkdir -p "${PRODUCT_CLONE_BASE}" || exit 1

for product_spec in $(printf '%s' "${PRODUCT_LIST}" | tr ',' ' '); do
    [ -z "${product_spec}" ] && continue
    product_name="${product_spec##*/}"
    product_url="${PRODUCT_BASE}/${product_spec}.git"
    product_dir="${PRODUCT_CLONE_BASE}/${product_name}"
    if [ ! -d "${product_dir}/.git" ]; then
        if ! git clone --quiet --depth 1 --branch "${PRODUCT_REF}" "${product_url}" "${product_dir}"; then
            echo "[product] 克隆失败：${product_spec}（${PRODUCT_REF}）→ ${product_dir}" >&2
            exit 1
        fi
    else
        git -C "${product_dir}" remote set-url origin "${product_url}"
        if ! git -C "${product_dir}" fetch --quiet --depth 1 origin "${PRODUCT_REF}"; then
            echo "[product] 拉取失败：${product_spec}（${PRODUCT_REF}）" >&2
            exit 1
        fi
        if ! git -C "${product_dir}" checkout --quiet --force --detach FETCH_HEAD; then
            echo "[product] 检出失败：${product_spec}（${PRODUCT_REF}）" >&2
            exit 1
        fi
    fi
    echo "[product] ${product_name} 就绪：${product_dir} @ ${PRODUCT_REF}（$(git -C "${product_dir}" rev-parse --short HEAD)）"
done
