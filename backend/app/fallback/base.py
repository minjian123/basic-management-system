"""降级能力域：依赖故障降级动作契约（真实降级矩阵随性能与安全 / 分布式与监控阶段回补）。

- `DEPENDENCIES`：依赖标识清单（对应《架构设计 · 性能与安全》「限流与降级」节降级矩阵行）；
  `app/circuit/base.py` **单向复用**本常量（circuit → fallback，不反向）。
- `FallbackAction`：降级动作枚举（`raise` 不降级 / `default` 默认值 / `skip` 跳过 / `degrade` 降级通道）。
- `BaseFallbackPolicy`：能力域中间层契约（`key = "fallback"`）——`resolve` 按依赖返回应采取的降级动作。
- `NullFallbackPolicy`：占位实现，**不降级**（恒定 `raise`，保持现状调用链语义）。
- `get_fallback_policy`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：基座只返回**动作**、不接管调用链（不执行降级路径、不捕获异常）；调用方按动作处理
（`default` 取默认值、`skip` 跳过步骤、`degrade` 走降级通道、`raise` 原样上抛）。
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import cast

from fastapi import Request

from app.core.capability import BaseCapability, BaseNullObject

DEPENDENCIES: tuple[str, ...] = (
    "redis",
    "database",
    "rocketmq",
    "elasticsearch",
    "minio",
    "mail_sms",
    "external_api",
)
"""依赖标识清单（降级矩阵行）；新增依赖类型在此追加，并同步架构降级矩阵表。"""


class FallbackAction(StrEnum):
    """降级动作（按依赖由 `BaseFallbackPolicy.resolve` 给出）。"""

    RAISE = "raise"
    """不降级：保持原调用链语义，向上抛。"""

    DEFAULT = "default"
    """返回默认值。"""

    SKIP = "skip"
    """跳过该步骤（不返回结果，继续后续流程）。"""

    DEGRADE = "degrade"
    """走降级通道（具体降级路径由调用方实现，如直连 DB、同步直写）。"""


class BaseFallbackPolicy(BaseCapability, ABC):
    """降级契约：按依赖返回当前应采取的降级动作。"""

    key: str = "fallback"

    @abstractmethod
    async def resolve(self, dependency: str, *, exc: BaseException | None = None) -> FallbackAction:
        """按依赖返回降级动作。

        Args:
            dependency: 依赖标识（建议取 `DEPENDENCIES` 之一）。
            exc: 触发降级的异常（可选，供实现按异常类型细分）。

        Returns:
            FallbackAction: 应采取的降级动作。
        """


class NullFallbackPolicy(BaseFallbackPolicy, BaseNullObject):
    """占位降级策略：**不降级**（恒定返回 `raise`，未接入真实降级矩阵时使用）。"""

    async def resolve(self, dependency: str, *, exc: BaseException | None = None) -> FallbackAction:
        """恒定不降级。

        Args:
            dependency: 依赖标识（占位不区分）。
            exc: 触发异常（占位不区分）。

        Returns:
            FallbackAction: `FallbackAction.RAISE`。
        """
        return FallbackAction.RAISE


def get_fallback_policy(request: Request) -> BaseFallbackPolicy:
    """取应用级降级策略（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseFallbackPolicy: 应用装配的降级策略实例。
    """
    return cast("BaseFallbackPolicy", request.app.state.fallback_policy)
