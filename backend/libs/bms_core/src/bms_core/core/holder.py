"""core 层值容器：`get_locked` 上下文内可替换的值持有点。

**落点说明（09_05 批次 ②b，2026-09-28）**：`ValueHolder` 原定义在 `core/base.py`（根系所在模块）。
根系模块**不能**导入 `core/objects/`（`core/objects/roots.py` 反向依赖 `core/base.BaseObject`，会形成
循环导入），故迁出到本模块后挂 `BaseFrameworkObject`（框架对象：非数据对象 + `object_kind` 标识）；
导入方由 `bms_core.core.base` 改从本模块导入。
"""

from __future__ import annotations

from bms_core.core.objects import BaseFrameworkObject

__all__ = ["ValueHolder"]


class ValueHolder[ValueT](BaseFrameworkObject):
    """`get_locked` 类上下文内可替换的值容器（进程内与 Redis 复用）。"""

    object_kind = "value_holder"

    def __init__(self, value: ValueT) -> None:
        """初始化。

        Args:
            value: 初始值（上下文内可经 `holder.value` 写回）。
        """
        self.value = value
