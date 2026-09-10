#!/usr/bin/env bash
# 基座变更提交前校验（bms 权威源侧）
#
# 1) 基座完整性：链接自洽 + 无跨层引用 + 无措辞残留 + 清单与磁盘一致（check-base.py）；
# 2) 产品仓库基座一致性：对 scripts/tools/base-sync/.targets 中登记的每个产品仓库运行
#    base-sync.py check（存在差异即失败）——该文件含本地路径，已 gitignore，不入库。
#
# 用法：
#   bash scripts/tools/base-sync/pre-commit.sh          # 手动运行
#   ln -sf ../../scripts/tools/base-sync/pre-commit.sh .git/hooks/pre-commit   # 装为 git 钩子
set -u
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 1

fail=0

echo "== 1/2 基座完整性 =="
if ! python3 scripts/tools/base-sync/check-base.py; then
  fail=1
fi

echo
echo "== 2/2 产品仓库基座一致性 =="
TARGETS_FILE="scripts/tools/base-sync/.targets"
if [ ! -f "$TARGETS_FILE" ]; then
  echo "（未登记产品仓库：$TARGETS_FILE 不存在，跳过；一行一个仓库路径，# 开头为注释）"
else
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    tgt="${line%%#*}"
    tgt="$(echo "$tgt" | sed 's/[[:space:]]*$//')"
    [ -z "$tgt" ] && continue
    if [ ! -d "$tgt" ]; then
      echo "[跳过] 目录不存在：$tgt"
      continue
    fi
    echo "-- $tgt"
    if ! python3 scripts/tools/base-sync/base-sync.py check --target "$tgt" >/dev/null; then
      echo "   [不一致] 运行：python3 scripts/tools/base-sync/base-sync.py sync --target $tgt --apply"
      fail=1
    else
      echo "   一致"
    fi
  done < "$TARGETS_FILE"
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "基座校验不通过，提交已中止。"
  exit 1
fi
echo
echo "基座校验通过。"
