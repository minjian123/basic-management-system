"""内置定时任务种子 CLI 薄壳（实现归 `bms_core.tenant.seed.tasks`）。

口径同 `ops/seed_config.py`：`ops/` 属运维通道，本脚本只做入口转发，实现与种子数据全部归基座，
避免运维包与基座两份实现漂移。**统一编排**请用 `python -m ops.seed_platform`
（租户开通流程按 `deploy/registry/platform.toml` 的 `[[seeds]]` 自动执行本入口）。
"""

from typing import Any

from bms_core.tenant.seed.tasks import (
    seed_tasks_entry,
)

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""

__all__ = ["seed_tasks_entry"]


def __getattr__(name: str) -> Any:
    """把未显式导入的属性转发到基座实现模块（供测试 monkeypatch）。

    Args:
        name: 属性名。

    Returns:
        Any: 基座模块中的同名属性。
    """
    from bms_core.tenant.seed import tasks as _impl

    return getattr(_impl, name)
