"""达梦客户端通信加密模块（`dmssl`）加载路径：定位、自检与平台自适应修复。

- **背景**：`dmPython` 轮子自带通信加密模块目录（`site-packages/dmssl`：Windows 为
  `libeay32.dll` / `ssleay32.dll`，Linux 为 `libssl.so` / `libcrypto.so`）；该目录不在动态库搜索路径内时，
  达梦建连**直接失败**：`DatabaseError [CODE:-70089] 加密模块加载失败 / Encryption module failed to load`
  （2026-10-18 实测复现）。
- **平台差异（实测）**：**Windows** 运行期把该目录前置到 `PATH` 即生效；**POSIX 只能在进程启动前**
  注入 `LD_LIBRARY_PATH`——运行期改 `PATH`、`ctypes` 预载（`RTLD_GLOBAL`）、`site-packages/lib`
  候选布局、`dmsvc_path` + `LIBSSL_LOAD_PATH`（四种写法）**均实测无效**，与官方 `dmPython`
  `METADATA`「`export LD_LIBRARY_PATH=<site-packages>/dmssl`」同口径。
- **落法**：本模块负责 **Windows 自动修复** 与 **POSIX 自检**（缺失时给出可直接复制的修复命令，
  **明确告警、不静默降级**）；POSIX 的注入入口＝仓内启动包装 `scripts/tools/db/达梦环境.sh`
  （本地 Linux 与 CI 作业共用同一入口）。
- 结论与排障登记见《数据库设计 · 方言特性 · 达梦》「事务与连接」与《达梦 DM8 部署使用说明》排障表。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

__all__ = [
    "DM_SSL_MISSING",
    "DM_SSL_MODULE",
    "DM_SSL_OK",
    "DM_SSL_UNAVAILABLE",
    "dm_ssl_dir",
    "dm_ssl_hint",
    "ensure_dm_ssl_module",
]

DM_SSL_MODULE = "dmssl"
"""通信加密模块目录名（`dmPython` 轮子内置；Windows 为包形态、POSIX 为命名空间目录）。"""

DM_SSL_OK = "ok"
"""状态：加载路径已就绪（Windows 已自动前置 `PATH`，或 POSIX 已在 `LD_LIBRARY_PATH` 内）。"""

DM_SSL_MISSING = "missing"
"""状态：目录已定位但 **POSIX 未注入**——须在进程启动前注入，否则建连报 `-70089`。"""

DM_SSL_UNAVAILABLE = "unavailable"
"""状态：未定位到目录（未安装 `dmPython` 或轮子布局变化）——本驱动无需处理。"""

_WINDOWS: bool = sys.platform == "win32"
"""运行平台判定（Windows 可运行期修复；其余平台须进程启动前注入）。"""


def _search_path_env() -> str:
    """本平台动态库搜索路径环境变量名。

    Returns:
        str: Windows 为 `PATH`；POSIX 为 `LD_LIBRARY_PATH`。
    """
    return "PATH" if _WINDOWS else "LD_LIBRARY_PATH"


def dm_ssl_dir() -> Path | None:
    """定位 `dmPython` 轮子内的通信加密模块目录（**不导入该模块**）。

    Windows 轮子把 `dmssl` 装为常规包（`__init__.py`），POSIX 轮子装为无 `__init__.py` 的
    命名空间目录——两者分别经 `spec.origin` 与 `spec.submodule_search_locations` 取目录。

    Returns:
        Path | None: 目录路径；未安装 `dmPython` / 布局变化时为 None。
    """
    spec = importlib.util.find_spec(DM_SSL_MODULE)
    if spec is None:
        return None
    if spec.origin is not None:
        return Path(spec.origin).parent
    locations = spec.submodule_search_locations
    if not locations:
        return None
    return Path(next(iter(locations)))


def _on_search_path(directory: Path, value: str | None) -> bool:
    """判定目录是否已在给定搜索路径环境变量的条目内。

    Args:
        directory: 目标目录。
        value: 环境变量取值（未设置 / 空串为 None）。

    Returns:
        bool: 已在路径内为 True。
    """
    if not value:
        return False
    target = os.path.normcase(str(directory.resolve()))
    return any(os.path.normcase(str(Path(item).resolve())) == target for item in value.split(os.pathsep) if item)


def ensure_dm_ssl_module() -> str:
    """自检通信加密模块加载路径，并在 **Windows 上就地修复**（幂等）。

    Windows：把 `dmssl` 目录前置到 `PATH`（运行期生效，实测；已在路径内则不重复前置）。
    POSIX：只做判定——已注入返回 `DM_SSL_OK`，未注入返回 `DM_SSL_MISSING`（**运行期无法修复**，
    调用方据此告警并给出 `dm_ssl_hint()`）。

    Returns:
        str: 状态（`DM_SSL_OK` / `DM_SSL_MISSING` / `DM_SSL_UNAVAILABLE`）。
    """
    directory = dm_ssl_dir()
    if directory is None:
        return DM_SSL_UNAVAILABLE
    env_name = _search_path_env()
    current = os.environ.get(env_name)
    if _on_search_path(directory, current):
        return DM_SSL_OK
    if not _WINDOWS:
        return DM_SSL_MISSING
    os.environ[env_name] = str(directory) + os.pathsep + (current or "")
    return DM_SSL_OK


def dm_ssl_hint(directory: Path | None = None) -> str:
    """给出可直接复制的修复命令（POSIX：进程启动前注入 `LD_LIBRARY_PATH`）。

    Args:
        directory: 加密模块目录（缺省现取 `dm_ssl_dir()`）。

    Returns:
        str: 告警 / 排障文案（未定位到目录时给出占位路径）。
    """
    target = directory if directory is not None else dm_ssl_dir()
    location = str(target) if target is not None else f"<site-packages>/{DM_SSL_MODULE}"
    return (
        f"达梦客户端通信加密模块未在加载路径内（建连将报 [CODE:-70089]）："
        f"export LD_LIBRARY_PATH={location}:$LD_LIBRARY_PATH"
        f"（POSIX 须在进程启动前注入；本地 Linux 与 CI 共用 scripts/tools/db/达梦环境.sh）"
    )
