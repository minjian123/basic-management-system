"""后端工程根定位（唯一入口）：环境变量优先，其次自本文件向上搜标记文件。

工程根（`backend/`）的绝对位置随部署形态变化——源码工作区下即仓库 `backend/`；本地把 `.venv`
外置为符号链接后，`bms_core` 随解释器落进依赖仓，`backend/` 反而在链接链的另一端。故根定位
不写死层级，统一走本模块：

1. 环境变量 `BMS_BACKEND_ROOT`（显式指定，优先级最高；供容器、依赖外置等非常规布局使用）；
2. 自本文件向上搜索「含指定标记文件的最近祖先目录」。

**搜索用 `Path.absolute()` 而非 `Path.resolve()`**：后者会穿透符号链接，`.venv` 外置为符号链
接时会被解析到依赖仓真实路径，向上再也搜不到工程根（2026-10-14 实测：外置态 `resolve` 失败、
`absolute` 命中）。`absolute()` 保留链接路径、按字面层级上溯，正是所需语义。

配置唯一来源：工程根的判定只此一处，`core/config.py`（配置目录）与 `db/migration.py`（迁移
工程根）均经本模块解析，避免两处各自搜根、口径漂移。
"""

import os
from pathlib import Path

from bms_core.core.exceptions import ConfigError

BACKEND_ROOT_ENV = "BMS_BACKEND_ROOT"
"""工程根覆盖环境变量名：显式指定工程根目录；取值无效时 fail-closed（不静默回落）。"""


def resolve_backend_root(marker: str, *, anchor: Path | None = None) -> Path:
    """定位后端工程根：环境变量优先，其次自 `anchor` 向上取其首个含 `marker` 的祖先目录。

    Args:
        marker: 工程根标记文件名（如 `alembic.ini`、`config.toml`）。
        anchor: 上溯起点文件（默认本模块文件）；显式传入便于用例注入异常布局。

    Returns:
        Path: 含 `marker` 的工程根目录（环境变量命中时为其取值本身，不做链接解析）。

    Raises:
        ConfigError: 环境变量指向的目录不含 `marker`（显式指定却无效），或向上未搜到含
            `marker` 的目录（工程布局异常）。两者均 fail-closed，不静默回落到其他目录。
    """
    override = os.environ.get(BACKEND_ROOT_ENV)
    if override:
        root = Path(override).expanduser()
        if not (root / marker).is_file():
            raise ConfigError(
                f"{BACKEND_ROOT_ENV} 指向的目录缺少 {marker}：{root}"
                f"（工程布局异常或变量取值有误；请指向含 {marker} 的后端工程根）"
            )
        return root
    for parent in (anchor or Path(__file__)).absolute().parents:
        if (parent / marker).is_file():
            return parent
    raise ConfigError(f"未找到后端工程根（向上无含 {marker} 的目录）")
