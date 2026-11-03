"""国际化种子脚本入口（08 `05_01`）：语言清单与固定文案语言包（平台默认，幂等）。

实现下沉基座 `bms_core.i18n.seed`；本模块只做入口转发与 `RUN_IMAGE` 声明，
便于运维单跑与测试 monkeypatch（与 `ops/seed_config.py` 同形）。
"""

from typing import Any

from bms_core.i18n.seed import (
    MESSAGE_SEEDS,
    build_parser,
    main,
    seed_i18n_entry,
    seed_i18n_in_session,
)
from ops._worker import worker_id_lease_sync

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""

__all__ = [
    "MESSAGE_SEEDS",
    "build_parser",
    "main",
    "seed_i18n_entry",
    "seed_i18n_in_session",
]


def __getattr__(name: str) -> Any:
    """把未显式导入的属性转发到基座实现模块（含内部辅助函数，供测试 monkeypatch）。

    Args:
        name: 属性名。

    Returns:
        Any: 基座模块同名属性。
    """
    from bms_core.i18n import seed as _impl

    return getattr(_impl, name)


if __name__ == "__main__":  # pragma: no cover - 模块直跑入口（部署与用例都走 main()）
    with worker_id_lease_sync():
        raise SystemExit(main())
