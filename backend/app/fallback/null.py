"""fallback 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.fallback.base.py 迁入）。"""

from app.core.capability import BaseNullObject
from app.fallback.base import BaseFallbackPolicy, FallbackAction

__all__ = [
    "NullFallbackPolicy",
]


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
