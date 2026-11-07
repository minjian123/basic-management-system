"""审计留痕类别（07D `02_04`）：哪些操作必须留痕、是否强审计、是否带记录级定位。

**粒度问题的由来**：中间件按 HTTP 方法记全部写操作，读操作由端点显式声明——这对「普通新增」
够用，但分不清「重放 / 位点重置 / 删消息」这类**记录级高危操作**与「普通改一个字段」。本模块给出
可声明的类别，把「是否强审计」从业务分支里拿出来。

口径：

- **基座给缺省，产品可覆盖**：`DEFAULT_AUDIT_CLASSES` 覆盖通用动词语义；产品经
  `BaseServiceApplicationFactory.audit_classes()` 追加 / 覆盖（装配期合并进 `app.state.audit_classes`）。
- **普通读写不洪泛**：`read` 类不逐条留痕（只做指标），`write` 类走既有中间件；
  只有 `strong=True` 的操作才要求「写入失败即业务失败」。
- **不承载判定**：类别只描述留痕要求，不含权限或业务判定。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.objects import BaseValueObject

__all__ = [
    "AUDIT_CLASS_READ",
    "AUDIT_CLASS_RECORD_OPERATION",
    "AUDIT_CLASS_SENSITIVE",
    "AUDIT_CLASS_WRITE",
    "DEFAULT_AUDIT_CLASSES",
    "AuditClass",
    "audit_class_for",
    "merge_audit_classes",
]

AUDIT_CLASS_WRITE = "write"
"""普通写（新增 / 修改 / 删除）：走中间件普通留痕，失败不阻塞业务。"""

AUDIT_CLASS_SENSITIVE = "sensitive"
"""敏感写（配置 / 授权 / 密钥类）：强审计。"""

AUDIT_CLASS_RECORD_OPERATION = "record_operation"
"""记录级操作（重放 / 位点重置 / 删除消息 / 异常处置）：强审计 + 记录级定位。"""

AUDIT_CLASS_READ = "read"
"""普通读：不逐条留痕，只做指标统计。"""


@dataclass(frozen=True)
class AuditClass(BaseValueObject):
    """留痕类别：是否强审计、是否要求记录级定位。"""

    class_key: str
    """类别键（如 `record_operation`；产品自定义类别用 `{product}.{name}`）。"""

    strong: bool = False
    """强审计：写入失败即业务失败（`emit(required=True)`）。"""

    record_level: bool = False
    """要求记录级定位（`record_ref` 必填）。"""

    label: str = ""
    """中文说明（手册 / 运营视图用）。"""


DEFAULT_AUDIT_CLASSES: ConcurrentStableFrozenDict[str, AuditClass] = ConcurrentStableFrozenDict(
    {
        AUDIT_CLASS_WRITE: AuditClass(AUDIT_CLASS_WRITE, strong=False, record_level=False, label="普通写"),
        AUDIT_CLASS_SENSITIVE: AuditClass(
            AUDIT_CLASS_SENSITIVE, strong=True, record_level=False, label="敏感写（强审计）"
        ),
        AUDIT_CLASS_RECORD_OPERATION: AuditClass(
            AUDIT_CLASS_RECORD_OPERATION, strong=True, record_level=True, label="记录级操作（强审计 + 定位）"
        ),
        AUDIT_CLASS_READ: AuditClass(AUDIT_CLASS_READ, strong=False, record_level=False, label="普通读（只统计）"),
    }
)
"""基座缺省类别（覆盖通用动词语义）。"""

_FALLBACK_CLASS = DEFAULT_AUDIT_CLASSES[AUDIT_CLASS_WRITE]
"""未命中任何声明时的缺省类别（按普通写处理）。"""


def merge_audit_classes(
    overrides: Mapping[str, AuditClass] | None = None,  # bare-collections:allow（只读映射入参）
) -> ConcurrentStableDict[str, AuditClass]:
    """合并基座缺省与产品声明（同名覆盖）。

    Args:
        overrides: 产品声明的类别（`None` / 空表示不覆盖）。

    Returns:
        ConcurrentStableDict[str, AuditClass]: 合并视图（每次返回新字典）。
    """
    merged: ConcurrentStableDict[str, AuditClass] = ConcurrentStableDict(DEFAULT_AUDIT_CLASSES)
    if overrides:
        for key, value in overrides.items():
            merged.set(key, value)
    return merged


def audit_class_for(
    action: str,
    classes: Mapping[str, AuditClass] | None = None,  # bare-collections:allow（只读映射入参）
) -> AuditClass:
    """按动作取留痕类别（精确匹配动作 → 动词 → 类别键 → 缺省普通写）。

    Args:
        action: 动作标识（权限码 `msg:replay`，或回落的 `{module}:{verb}`）。
        classes: 合并后的类别视图（`None` 用基座缺省）。

    Returns:
        AuditClass: 命中的类别；未命中为 `write`。
    """
    view = DEFAULT_AUDIT_CLASSES if classes is None else classes
    if action in view:
        return view[action]
    _, _, verb = action.partition(":")
    if verb and verb in view:
        return view[verb]
    return _FALLBACK_CLASS
