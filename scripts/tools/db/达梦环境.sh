#!/usr/bin/env bash
# 达梦客户端环境注入（POSIX）：把 dmPython 轮子内的通信加密模块目录（dmssl）并入 LD_LIBRARY_PATH。
#
# 用法（**必须 source**，否则环境变量不生效）：
#   source scripts/tools/db/达梦环境.sh                 # 用 python3 定位 dmssl 目录
#   DM_ENV_PYTHON="uv run python" source scripts/tools/db/达梦环境.sh   # 指定解释器（可为复合命令）
#
# 背景（2026-10-18 实测）：缺少该路径时达梦建连直接报
#   dmPython.DatabaseError [CODE:-70089] Encryption module failed to load / 加密模块加载失败
# POSIX 下**只能在进程启动前**注入 LD_LIBRARY_PATH——运行期改 PATH、ctypes 预载（RTLD_GLOBAL）、
# `site-packages/lib` 候选布局、dmsvc_path + LIBSSL_LOAD_PATH 均实测无效（官方 METADATA 同口径）。
# Windows 无需本脚本：基座（bms_core.db.dialects.dm_ssl）会在建引擎前自动前置 PATH。
# 结论与排障登记见《达梦 DM8 部署使用说明》与《数据库设计 · 方言特性 · 达梦》。
# 注意：本脚本被 **source** 使用，故**不改动调用方的 shell 选项**（不 `set -e` / `set -u`）。

_dm_env_py="${DM_ENV_PYTHON:-${VIRTUAL_ENV:-}}"
if [ -n "${DM_ENV_PYTHON:-}" ]; then
  _dm_env_py="${DM_ENV_PYTHON}"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  _dm_env_py="${VIRTUAL_ENV}/bin/python"
else
  _dm_env_py="python3"
fi

# 定位 dmssl 目录（只用标准库：与基座同口径，Windows 为常规包 / POSIX 为命名空间目录）
_dm_ssl_dir="$(
  # shellcheck disable=SC2086  # DM_ENV_PYTHON 允许为复合命令（如 "uv run python"）
  $_dm_env_py - <<'PY' 2>/dev/null
import importlib.util
import pathlib

spec = importlib.util.find_spec("dmssl")
if spec is None:
    raise SystemExit(0)
if spec.origin is not None:
    print(pathlib.Path(spec.origin).parent)
elif spec.submodule_search_locations:
    print(pathlib.Path(next(iter(spec.submodule_search_locations))))
PY
)"

if [ -z "$_dm_ssl_dir" ]; then
  echo "[达梦环境] 未定位到 dmssl 目录（dmPython 未安装或轮子布局变化）：跳过注入" >&2
  unset _dm_env_py _dm_ssl_dir
elif [ ! -e "$_dm_ssl_dir" ]; then
  echo "[达梦环境] dmssl 目录不存在：$_dm_ssl_dir（跳过注入）" >&2
  unset _dm_env_py _dm_ssl_dir
else
  case ":${LD_LIBRARY_PATH:-}:" in
    *":$_dm_ssl_dir:"*) echo "[达梦环境] dmssl 已在 LD_LIBRARY_PATH 内（跳过）：$_dm_ssl_dir" ;;
    *)
      export LD_LIBRARY_PATH="$_dm_ssl_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      echo "[达梦环境] dmssl 已并入 LD_LIBRARY_PATH：$_dm_ssl_dir"
      ;;
  esac
  unset _dm_env_py _dm_ssl_dir
fi
