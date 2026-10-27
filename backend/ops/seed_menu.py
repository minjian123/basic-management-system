"""菜单元数据种子 CLI 薄壳（实现已下沉 `bms_core.tenant.seed.menu`；07B `02_03`）。

命令、参数与退出码**不变**：

```bash
cd backend
uv run python -m ops.seed_menu --dry-run
uv run python -m ops.seed_menu
```

口径：`ops/` 属运维通道，本脚本只做入口转发；实现、参数解析与种子数据全部归基座
（`bms_core.tenant.seed.menu`），避免运维包与基座两份实现漂移。

**内部单步**：本命令仅供排障；统一编排请用 `python -m ops.seed_platform`。

**模块级属性转发**：除显式导入的符号外，其余属性经 `__getattr__` 转发到基座模块——
既有测试会 `monkeypatch.setattr(ops.seed_x, "某个内部名", ...)`，转发保证这类用法继续有效。
"""

from typing import Any

from bms_core.tenant.seed.menu import (
    ACTION_SEEDS,
    BUSINESS_SEEDS,
    MENU_SEEDS,
    PERMISSION_SEEDS,
    build_parser,
    main,
    seed_menu,
    seed_menu_entry,
)

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""

__all__ = [
    "ACTION_SEEDS",
    "BUSINESS_SEEDS",
    "MENU_SEEDS",
    "PERMISSION_SEEDS",
    "build_parser",
    "main",
    "seed_menu",
    "seed_menu_entry",
]


def __getattr__(name: str) -> Any:
    """把未显式导入的属性转发到基座实现模块（含内部辅助函数，供测试 monkeypatch）。

    Args:
        name: 属性名。

    Returns:
        Any: 基座模块中的同名属性。

    Raises:
        AttributeError: 基座模块无该属性。
    """
    from bms_core.tenant.seed import menu as _impl

    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())
