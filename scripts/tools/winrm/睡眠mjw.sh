#!/usr/bin/env bash
# 远程让开发服务器 mjw 进入系统睡眠（S3）—— Linux 入口脚本
# 对应 Windows 版双击入口 睡眠mjw.bat；终端/桌面 .desktop 均可调用
# 用法: ./睡眠mjw.sh            （显示目标并输入 y 二次确认；依赖 pywinrm venv）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
PY="$HOME/tools/winrm-venv/bin/python"                    # sleep 需要 pywinrm
if [ ! -x "$PY" ]; then
  echo "缺少 pywinrm 虚拟环境（$PY）。请先按《开发服务器Windows电源控制使用说明》5.1 节创建:" >&2
  echo "  python3 -m venv ~/tools/winrm-venv && ~/tools/winrm-venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pywinrm" >&2
  exit 1
fi
exec "$PY" scripts/tools/winrm/sleep_mjw.py "$@"
