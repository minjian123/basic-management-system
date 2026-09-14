"""限流能力域：请求配额判定契约（真实 slowapi / Redis 后端随性能与安全阶段回补）。

- `RATE_LIMIT_DIMENSIONS`：限流维度清单（IP / 用户 / 开放接口 client，对应《架构设计 · 性能与安全》
  「限流与降级」节与《API接口规范》「幂等 / 限流 / 审计」节）。
- `RateLimitRule`：限流规则（frozen：`limit` 次数 / `window` 窗口秒）。
- `RateLimitDecision`：判定结果（`allowed` / `limit` / `remaining` / `reset_after`，供 `X-RateLimit-*` 响应头）。
- `BaseRateLimiter`：能力域中间层契约（`key = "rate_limiter"`）——`check` 判定配额、
  `require` 强制放行（失败抛 `RateLimitError`，10005 / 429）。
- `NullRateLimiter`：占位实现，**恒定放行**（不连 Redis、不计数）。
- `build_rate_limit_key`：限流 key 统一拼接（`bms:{租户|global}:rate:{维度}:{目标}`，
  见《架构设计 · 数据架构》「key 空间规划」节）。
- `get_rate_limiter`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：基座只返回**配额判定结果**、不接管调用链；`require` 仅供接口层一行接入（失败即抛异常）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import RateLimitError

RATE_KEY_PREFIX = "bms"
"""限流 key 前缀（与缓存 / 锁 key 同前缀）。"""

GLOBAL_RATE_SCOPE = "global"
"""全局限流作用域位（无租户维度的限流）。"""

DEFAULT_RATE_WINDOW = 60
"""默认限流窗口（秒）；真实实现按窗口滑窗计数。"""

RATE_LIMIT_DIMENSIONS: tuple[str, ...] = ("ip", "user", "client")
"""限流维度清单：内部接口按 IP / 用户、开放接口按 client（AppId）。"""


def build_rate_limit_key(*, dimension: str, target: str, tenant: str | None = None) -> str:
    """构建限流 key（规范 `bms:{租户|global}:rate:{维度}:{目标}`）。

    Args:
        dimension: 限流维度（建议取 `RATE_LIMIT_DIMENSIONS` 之一）。
        target: 维度目标（IP / 用户 id / client_id）。
        tenant: 租户标识；None 表示全局维度。

    Returns:
        str: 限流 key。
    """
    return f"{RATE_KEY_PREFIX}:{tenant or GLOBAL_RATE_SCOPE}:rate:{dimension}:{target}"


@dataclass(frozen=True)
class RateLimitRule(BaseObject):
    """限流规则：窗口内允许的最大次数。"""

    limit: int
    """窗口内允许的最大请求次数（必填，由调用方按接口档位给出）。"""

    window: int = DEFAULT_RATE_WINDOW
    """窗口长度（秒）。"""


@dataclass(frozen=True)
class RateLimitDecision(BaseObject):
    """限流判定结果（供放行判断与 `X-RateLimit-*` 响应头）。"""

    allowed: bool
    """是否放行。"""

    limit: int
    """规则上限（回显 `X-RateLimit-Limit`）。"""

    remaining: int
    """窗口内剩余配额（回显 `X-RateLimit-Remaining`）。"""

    reset_after: int
    """窗口重置剩余秒数（回显 `X-RateLimit-Reset`）。"""


class BaseRateLimiter(BaseCapability, ABC):
    """限流契约：按 key + 规则判定配额。"""

    key: str = "rate_limiter"

    @abstractmethod
    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """判定配额（不抛错，返回决策）。

        Args:
            key: 限流 key（经 `build_rate_limit_key` 构建）。
            rule: 限流规则（次数 / 窗口）。

        Returns:
            RateLimitDecision: 判定结果。
        """

    async def require(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """强制放行校验（接口层一行接入）。

        Args:
            key: 限流 key（经 `build_rate_limit_key` 构建）。
            rule: 限流规则（次数 / 窗口）。

        Returns:
            RateLimitDecision: 判定结果（放行）。

        Raises:
            RateLimitError: 超出配额（10005 / 429，全局处理器统一转响应）。
        """
        decision = await self.check(key, rule)
        if not decision.allowed:
            raise RateLimitError(f"超出限流配额：{key}")
        return decision


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


def get_rate_limiter(request: Request) -> BaseRateLimiter:
    """取应用级限流器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseRateLimiter: 应用装配的限流器实例。
    """
    return cast("BaseRateLimiter", request.app.state.rate_limiter)
