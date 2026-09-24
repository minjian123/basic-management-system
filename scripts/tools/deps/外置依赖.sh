#!/bin/sh
# 依赖外置：把项目内依赖目录整体搬移至本地依赖仓，原位置留目录级符号链接。
# 效果：磁盘占用归零、内容不出项目（检索/扫描工具默认不跟随符号链接即扫不到）。
# 适用对象：pnpm workspace 的 node_modules 目录。
#
# 用法：
#   bms/scripts/tools/deps/外置依赖.sh [--dry-run]
#
# 本地依赖仓目录（本地资源信息，不入公开文档）：
#   1) 环境变量 DEPS_DIR；
#   2) bms/deploy/.env 中的 DEPS_DIR=（bms 仓根相对路径执行时自动读取）；
#   3) 缺省 $HOME/dev-deps/bms。
#
# 配套：还原依赖.sh（搬回原位）、重装依赖.sh（还原→安装→再外置）。
set -eu

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

# ---- 解析本地依赖仓目录（环境变量 > deploy/.env > 缺省）----
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
DEPS_DIR="$(cd "$DEPS_DIR" 2>/dev/null && pwd || printf '%s' "$DEPS_DIR")"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

run() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

echo "[外置依赖] 本地依赖仓：$DEPS_DIR"

tmp_list=$(mktemp)
find . -type d -name node_modules -not -path '*/.pnpm/*' > "$tmp_list"
count=0
while IFS= read -r d; do
    # 已外置（原位为符号链接且指向外部）则跳过
    if [ -L "$d" ]; then
        target=$(readlink "$d")
        case "$target" in
            "$DEPS_DIR"*) echo "[跳过] $d 已是外置符号链接" && continue ;;
        esac
    fi
    rel="${d#./}"
    dest="$DEPS_DIR/$rel"
    echo "[外置] $rel"
    count=$((count + 1))
    if [ "$DRY_RUN" = 1 ]; then continue; fi
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest" 2>/dev/null || true
    mv "$d" "$dest"
    ln -s "$dest" "$d"
done < "$tmp_list"
rm -f "$tmp_list"
echo "[外置] 完成：共 $count 个依赖目录。"

# ---- 修复 workspace 包软链 ----
# pnpm 的 workspace 包（如 @bms/core）在 node_modules 内是**指向项目源码目录的相对软链**
# （例：node_modules/@bms/core -> ../../../core）。依赖目录整体搬到依赖仓后，该相对路径改以
# 依赖仓为基准解析，指向依赖仓内并不存在的源码目录而断裂，依赖它的包（如 @bms/vue）随之
# 报「Cannot find module '@bms/core'」，本地类型检查 / 测试失败（CI 现装态不受影响）。
# 此处把这类断链重写为指向项目源码的绝对路径：外置收益（依赖不占项目树、检索不跟随软链）
# 不变，本地门禁与 CI 口径一致。
# 幂等：已指向项目内的软链解析后不以依赖仓开头，天然跳过。
fix_workspace_links() {
    find "$DEPS_DIR" -type l 2>/dev/null | while IFS= read -r link; do
        target=$(readlink -f "$link" 2>/dev/null || true)
        [ -n "$target" ] || continue
        case "$target" in
            "$DEPS_DIR"/*) ;;
            *) continue ;;
        esac
        # 完整包目录（含 package.json）或存在的文件类链接 → 正常，跳过；
        # 其余（目录缺 package.json、断链）→ 视为 workspace 链接候选
        if [ -f "$target/package.json" ]; then continue; fi
        if [ ! -d "$target" ] && [ -e "$target" ]; then continue; fi
        rel="${target#"$DEPS_DIR"/}"
        src="$ROOT/$rel"
        [ -e "$src" ] || continue
        echo "[修复] 工作区软链 ${link#"$DEPS_DIR"/} -> $src"
        run ln -snf "$src" "$link"
    done
}
fix_workspace_links

echo "[外置] 查看本地依赖仓体积： du -sh \"$DEPS_DIR\""
echo "[外置] 确认项目内为符号链接： ls -la <包>/node_modules"