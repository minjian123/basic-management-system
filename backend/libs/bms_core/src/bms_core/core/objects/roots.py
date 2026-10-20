"""core 层体系统根（薄再导出）：实现已上移至 `bms_core.core.roots`（08_05 结构性破环）。

**为什么上移**：`core/concurrent.py` 与 `core/collections.py` 经 `core/locking.py` / `core/holder.py` 需要
`BaseFrameworkObject`；若从本模块导入，会先执行 `core/objects/__init__.py` 的**全链聚合**，其中
`tally` / `options` 运行期反向依赖 `core.concurrent`，形成
`core.concurrent → core.locking/holder → core.objects → 链模块 → core.concurrent` 导入环。实现上移到
`core/roots.py` 后依赖链只剩 `core.roots → core.base`（无环），值对象字段名常量（`COMMON_FIELDS` /
`COUNT_FIELDS` / `SECRET_FIELDS`）才可落集合类（08_05 存量整改最后一类）。

**兼容口径**：本模块保留原有导出与 `__all__`，既有 `from bms_core.core.objects.roots import ...` 调用方
零改动；新代码可直接从 `bms_core.core.roots` 导入（少一层包聚合）。

体系根语义（值对象 / 数据契约 / 框架对象）见 `bms_core.core.roots` 模块文档。
"""

from __future__ import annotations

from bms_core.core.roots import (
    FRAMEWORK_OBJECT_KIND,
    BaseDataContract,
    BaseFrameworkObject,
    BaseValueObject,
)

__all__ = [
    "FRAMEWORK_OBJECT_KIND",
    "BaseDataContract",
    "BaseFrameworkObject",
    "BaseValueObject",
]
