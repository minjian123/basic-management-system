#!/bin/sh
# 依赖重装：还原 → 重新安装（前端 pnpm / 后端 uv）→ 再次外置。
# 用法：bms/scripts/tools/deps/重装依赖.sh [--frontend-only|--backend-only]
#   --frontend-only ：只重装前端（pnpm install），后端环境不动
#   --backend-only  ：只重装后端（uv sync），前端不动
#   不带参数        ：前后端一起重装（uv sync + pnpm install）
set -eu

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPTS_DIR/../../.." 2>/dev/null && pwd || true)"

# ---- 仓库根校验：路径前缀重复会把 ROOT 推深一层，后续 pnpm install / 外置都会落错位置。
if [ -z "$ROOT" ] || [ ! -f "$ROOT/pnpm-workspace.yaml" ]; then
    echo "[重装依赖] 仓库根定位失败：${ROOT:-（上跳三级目录不存在）} 下没有 pnpm-workspace.yaml" >&2
    echo "[重装依赖] 请在 bms 仓根执行 bash scripts/tools/deps/重装依赖.sh，勿叠加仓名前缀。" >&2
    exit 2
fi
cd "$ROOT"

MODE="${1:-all}"
case "$MODE" in
    --frontend-only) ;;
    --backend-only) ;;
    all) ;;
    *) echo "[重装依赖] 未知参数：$MODE（支持 --frontend-only / --backend-only）" >&2; exit 2 ;;
esac

# 后端环境外置：uv 项目环境走**符号链接口径**（`backend/.venv` -> 依赖仓 backend-venv），
# 不再依赖 UV_PROJECT_ENVIRONMENT —— 该变量只在交互式 shell 生效（.bashrc 有 interactive
# early-return），非交互调用（脚本 / agent / CI 外部工具）会落回仓内 `.venv`，且全局导出会
# 跨仓串环境（2026-10-14 实测：mdm 目录下 uv run 误装进 bms 共享环境）。
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

echo "[重装依赖] 本地依赖仓：$DEPS_DIR"

# 1) 先还原（移除外置符号链接，安装器才能正常重建项目内目录）
#    后端 .venv 走 UV_PROJECT_ENVIRONMENT 外置，不在 node_modules 还原范畴。
sh "$SCRIPTS_DIR/还原依赖.sh"

# 2) 安装
# 后端一律在 `backend/` 下执行（工程根在 `backend/`，仓根没有 pyproject.toml）：
# 还原后 `.venv` 已回到 `backend/.venv` 真实目录，uv sync 就地同步该环境。
if [ "$MODE" = "--frontend-only" ]; then
    pnpm install --frozen-lockfile
elif [ "$MODE" = "--backend-only" ]; then
    (cd "$ROOT/backend" && uv sync --frozen)
else
    (cd "$ROOT/backend" && uv sync --frozen)
    pnpm install --frozen-lockfile
fi

# 3) 再次外置
sh "$SCRIPTS_DIR/外置依赖.sh"
echo "[重装依赖] 完成。"