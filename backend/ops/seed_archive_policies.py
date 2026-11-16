"""归档策略种子 CLI 薄壳（实现归 `bms_core.tenant.seed.archive`）。

口径同 `ops/seed_tasks.py`：`ops/` 属运维通道，本脚本只做入口转发；统一编排请用
`python -m ops.seed_platform`（平台库种子按 `deploy/registry/platform.toml` 的 `[[seeds]]` 执行）。
"""

from typing import Any

from bms_core.tenant.seed.archive import (
    seed_archive_policies_entry,
)

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""

__all__ = ["seed_archive_policies_entry"]


def __getattr__(name: str) -> Any:
    """把未显式导入的属性转发到基座实现模块（供测试 monkeypatch）。

    Args:
        name: 属性名。

    Returns:
        Any: 基座模块中的同名属性。
    """
    from bms_core.tenant.seed import archive as _impl

    return getattr(_impl, name)
