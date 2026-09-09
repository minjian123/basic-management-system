#!/usr/bin/env bash
# 远程关闭开发服务器 mjw（S5 关机）—— Linux 入口脚本（破坏性操作）
# 对应 Windows 版双击入口 关机mjw.bat；终端/桌面 .desktop 均可调用
# 用法: ./关机mjw.sh            （显示目标并输入 y 二次确认；依赖 pywinrm venv）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
PY="$HOME/tools/winrm-venv/bin/python"                    # shutdown 需要 pywinrm
if [ ! -x "$PY" ]; then
  echo "缺少 pywinrm 虚拟环境（$PY）。请先按《开发服务器Windows电源控制使用说明》5.1 节创建:" >&2
  echo "  python3 -m venv ~/tools/winrm-venv && ~/tools/winrm-venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pywinrm" >&2
  exit 1
fi
exec "$PY" scripts/tools/winrm/shutdown_mjw.py "$@"
