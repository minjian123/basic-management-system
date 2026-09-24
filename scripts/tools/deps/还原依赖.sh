#!/bin/sh
# 依赖还原：删除项目内的外置符号链接，把本地依赖仓中的依赖目录搬回项目原位。
# 配套用场景：执行 pnpm install / uv sync 等安装动作前的必要前置（安装器会重建项目内目录）。
# 用法：bms/scripts/tools/deps/还原依赖.sh [--dry-run]
set -eu

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

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
DEPS_DIR="$(resolve_deps_dir)"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

run() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

echo "[还原依赖] 本地依赖仓：$DEPS_DIR"

count=0
if [ -d "$DEPS_DIR" ]; then
    tmp_list=$(mktemp)
    # 先收集全部清单再统一搬移：find 遍历中搬走目录会中断遍历（经典陷阱）
    find "$DEPS_DIR" -type d -name node_modules > "$tmp_list" 2>/dev/null
    while IFS= read -r src; do
        rel="${src#"$DEPS_DIR"/}"
        dst="$ROOT/$rel"
        if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
            echo "[还原] $rel"
            count=$((count + 1))
            if [ "$DRY_RUN" = 1 ]; then continue; fi
            rm -f "$dst"
            # 目录整体搬回（同分区 rename，保留硬链接 / 链接结构）
            mv "$src" "$dst"
        fi
    done < "$tmp_list"
    rm -f "$tmp_list"
fi
echo "[还原] 完成：共 $count 个依赖目录已搬回。"