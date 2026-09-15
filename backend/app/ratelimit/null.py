"""ratelimit 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.ratelimit.base.py 迁入）。"""

from app.core.capability import BaseNullObject
from app.ratelimit.base import BaseRateLimiter, RateLimitDecision, RateLimitRule

__all__ = [
    "NullRateLimiter",
]


class NullRateLimiter(BaseRateLimiter, BaseNullObject):
    """占位限流：**恒定放行**（不连 Redis、不计数，未接入真实限流时使用）。"""

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """恒定放行。

        Args:
            key: 限流 key（占位不区分）。
            rule: 限流规则（`limit` / `window` 回显，不计数）。

        Returns:
            RateLimitDecision: 放行决策（剩余配额等于上限、无重置等待）。
        """
        return RateLimitDecision(allowed=True, limit=rule.limit, remaining=rule.limit, reset_after=0)
