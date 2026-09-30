"""值对象体系 · 事件契约链层：可往返快照的事件契约对象。

**链结构（按公共段成层，本次 1 层）**：

- `BaseSnapshotRoundTripContract`（**公共段为成对方法** `to_snapshot()` / `from_snapshot()`）——事件契约
  与订阅共用「快照往返」能力（契约快照零漂移依赖此对方法）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from bms_core.core.objects.roots import BaseValueObject

if TYPE_CHECKING:  # `core.concurrent` 经 `core.holder` 反向依赖本包，运行期导入会成环
    from bms_core.core.concurrent import ConcurrentStableDict

__all__ = ["BaseSnapshotRoundTripContract"]


@dataclass(frozen=True)
class BaseSnapshotRoundTripContract(BaseValueObject, ABC):
    """快照往返契约（角色链层）：对象 ↔ 快照条目的**成对**转换。

    公共段为**成对方法**（抽象入口）：`to_snapshot()` 渲染为快照条目、`from_snapshot(entry)`
    由条目还原——事件契约快照（`events/snapshot.py`）与前端类型生成依赖该对方法保证零漂移。
    """

    @abstractmethod
    def to_snapshot(self) -> ConcurrentStableDict[str, object]:
        """渲染为快照条目。

        Returns:
            ConcurrentStableDict[str, object]: 快照条目（键为字段名；插入序）。
        """

    @classmethod
    @abstractmethod
    def from_snapshot(cls, entry: ConcurrentStableDict[str, object]) -> Self:
        """由快照条目构造对象。

        Args:
            entry: 快照条目（插入序映射）。

        Returns:
            Self: 还原后的对象。
        """
