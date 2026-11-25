#!/usr/bin/env bash
# 推送入口（Linux）：预检通过后自动推送
# 档位按待推提交自动选（全文档→快速档 / 含代码→定向档）；工作树脏即拒
# 用法: ./推送.sh [--full] [--remote origin] [--branch <分支>] [--jobs auto|N|off]
#
# 解释器只用仓内 venv：预检里的 {python} 取启动解释器（sys.executable），
# 用 PATH 上的 python3 会把 pyright / 护栏指向缺依赖的系统解释器。
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
VENV_PY="backend/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[推送] 未找到仓内解释器：$PWD/$VENV_PY" >&2
  echo "  请先按《开发机部署使用说明》准备 backend/.venv（依赖外置时先还原依赖再同步）。" >&2
  exit 2
fi
exec "$VENV_PY" scripts/tools/preflight/推送.py "$@"
