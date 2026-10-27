"""种子实现与编排器之间的**契约类型**（07B `02_03`；详设 §3.5 / §3.10）。

**为什么单独一个模块**：`ExpectedRow` 由**编排器**（冲突预检）消费、由**种子实现模块**产出。
若把它定义在 `orchestrator`，各种子实现就要 `import orchestrator`——形成「种子实现 → 编排器」
的反向依赖（编排器本身按名字装载种子）。故契约类型下沉本模块，两侧都只依赖它，方向单一。

**口径**：`expected_rows()` 必须是**纯函数**（不连库、不写库），期望值来自代码常量。
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.objects import BaseValueObject

__all__ = ["ExpectedRow"]


@dataclass(frozen=True)
class ExpectedRow(BaseValueObject):
    """种子期望行（冲突预检比对用；详设 §3.5）。

    **契约**：种子实现模块**可选**暴露 `expected_rows() -> ConcurrentStableList[ExpectedRow]`；
    未暴露时跳过该种子的数据预检（仅靠唯一约束兜底），不报错。
    """

    table: str
    """真实表名（如 `sys_business`）。"""

    key: ConcurrentStableFrozenDict[str, object]
    """自然键（列名 → 值）。"""

    values: ConcurrentStableFrozenDict[str, object] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenDict()
    )
    """期望字段值（列名 → 值；空表示只校验存在性）。"""
