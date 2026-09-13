"""core 层能力域中间层基类：占位实现、能力域契约与异步资源生命周期。

- `BasePlaceholder`：占位实现公共父（`placeholder` 标记 + `describe()`）。
  - `BaseNullObject`：空实现（Null Object，无副作用）。
  - `BaseStub`：未实现占位（统一 `_not_implemented()` 抛错）。
- `BaseCapability`：能力域契约中间层（统一 `key`）。
  - `BaseEventWorker`：事件发布 / 消费契约（共享 `event_type`）。
- `BaseAsyncResource`：异步资源生命周期（`aclose()` + `async with`），供引擎 / 客户端复用。
"""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.core.base import BaseObject


class BasePlaceholder(BaseObject):
    """占位实现公共父：标记"未接真实实现"，便于启动校验与测试断言。"""

    placeholder: bool = True

    def describe(self) -> str:
        """占位描述（子类可覆写）。

        Returns:
            str: 占位说明。
        """
        return f"{type(self).__name__}（占位实现，待回补真实实现）"


class BaseNullObject(BasePlaceholder):
    """空实现（Null Object）基类：实现全部契约但无副作用。"""


class BaseStub(BasePlaceholder, ABC):
    """未实现占位基类：统一抛出 `NotImplementedError`。"""

    def _not_implemented(self, feature: str = "") -> NotImplementedError:
        """构造统一的未实现异常。

        Args:
            feature: 未实现的功能点（可选）。

        Returns:
            NotImplementedError: 带类名与功能点的异常。
        """
        detail = f"：{feature}" if feature else ""
        return NotImplementedError(f"{type(self).__name__} 尚未实现{detail}")


class BaseCapability(BaseObject, ABC):
    """能力域契约中间层：统一能力域标识（供注册 / 依赖注入 / 文档对齐）。"""

    key: str = "capability"


class BaseEventWorker(BaseCapability, ABC):
    """事件工作单元契约：发布 / 消费共享的事件类型。"""

    key: str = "event"

    @property
    @abstractmethod
    def event_type(self) -> str:
        """事件类型（发布主题 / 订阅类型）。"""


class BaseAsyncResource(BaseObject, ABC):
    """异步资源生命周期基类：统一释放与 `async with`。"""

    @abstractmethod
    async def aclose(self) -> None:
        """释放资源（幂等，可重复调用）。"""

    async def __aenter__(self) -> Self:
        """进入异步上下文。

        Returns:
            BaseAsyncResource: 自身。
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出异步上下文并释放资源。"""
        await self.aclose()
