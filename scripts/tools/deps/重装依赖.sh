#!/bin/sh
# 依赖重装：还原 → 重新安装（前端 pnpm / 后端 uv）→ 再次外置。
# 用法：bms/scripts/tools/deps/重装依赖.sh [--frontend-only|--backend-only]
#   --frontend-only ：只重装前端（pnpm install），后端环境不动
#   --backend-only  ：只重装后端（uv sync），前端不动
#   不带参数        ：前后端一起重装（uv sync + pnpm install）
set -eu

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
SCRIPTS_DIR="$(dirname "$0")"

MODE="${1:-all}"
case "$MODE" in
    --frontend-only) ;;
    --backend-only) ;;
    all) ;;
    *) echo "[重装依赖] 未知参数：$MODE（支持 --frontend-only / --backend-only）" >&2; exit 2 ;;
esac

# 后端环境外置：UV_PROJECT_ENVIRONMENT 指向本地依赖仓（与 deploy/.env 同源读取）
resolve_deps_dir() {
    if [ -n "${DEPS_DIR:-}" ]; then
        printf '%s' "$DEPS_DIR"
        return 0
    fi
    if [ -f "$ROOT/deploy/.env" ]; then
        if value=$(grep -E '^DEPS_DIR=' "$ROOT/deploy/.env" | head -1 | sed 's/^DEPS_DIR=//'); then
            if [ -n "$value" ]; then
                printf '%s' "$value"
                return 0
            fi
        fi
    fi
    printf '%s' "${HOME:-/home/shared}/dev-deps/bms"
}
export DEPS_DIR="$(resolve_deps_dir)"
# 后端环境外置：uv 项目环境指向本地依赖仓 backend-venv（仓库内不落 .venv）
export UV_PROJECT_ENVIRONMENT="$DEPS_DIR/backend-venv"

echo "[重装依赖] 本地依赖仓：$DEPS_DIR"

# 1) 先还原（移除外置符号链接，安装器才能正常重建项目内目录）
#    后端 .venv 走 UV_PROJECT_ENVIRONMENT 外置，不在 node_modules 还原范畴。
sh "$SCRIPTS_DIR/还原依赖.sh"

# 2) 安装
if [ "$MODE" = "--frontend-only" ]; then
    pnpm install --frozen-lockfile
elif [ "$MODE" = "--backend-only" ]; then
    uv sync --frozen
else
    uv sync --frozen
    pnpm install --frozen-lockfile
fi

# 3) 再次外置
sh "$SCRIPTS_DIR/外置依赖.sh"
echo "[重装依赖] 完成。"