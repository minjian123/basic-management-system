"""限流基座契约测试（Kiwi 43）：继承 / 规则与维度 / key 口径 / 占位放行 / 拒绝语义 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_rate_limiter
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import RateLimitError
from app.main import ApplicationFactory, lifespan
from app.ratelimit.base import (
    DEFAULT_RATE_WINDOW,
    RATE_LIMIT_DIMENSIONS,
    BaseRateLimiter,
    RateLimitDecision,
    RateLimitRule,
    build_rate_limit_key,
)
from app.ratelimit.null import NullRateLimiter


class DenyRateLimiter(BaseRateLimiter):
    """测试用拒绝限流器：恒定超配额。"""

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """恒定拒绝（配额已耗尽）。

        Args:
            key: 限流 key（本实现不区分）。
            rule: 限流规则（回显上限与窗口）。

        Returns:
            RateLimitDecision: 拒绝决策。
        """
        return RateLimitDecision(allowed=False, limit=rule.limit, remaining=0, reset_after=rule.window)


@pytest.mark.kiwi_id(43)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseRateLimiter, BaseCapability)
    assert issubclass(NullRateLimiter, BaseRateLimiter)
    assert issubclass(NullRateLimiter, BaseNullObject)
    assert BaseRateLimiter.key == "rate_limiter"

    limiter = NullRateLimiter()
    assert limiter.placeholder is True
    assert "占位实现" in limiter.describe()


@pytest.mark.kiwi_id(43)
def test_rule_and_dimensions() -> None:
    """限流规则默认窗口与限流维度清单就位。"""
    assert RATE_LIMIT_DIMENSIONS == ("ip", "user", "client")
    assert DEFAULT_RATE_WINDOW == 60
    assert RateLimitRule(limit=5).window == DEFAULT_RATE_WINDOW
    assert RateLimitRule(limit=5, window=30).window == 30


@pytest.mark.kiwi_id(43)
def test_build_key() -> None:
    """限流 key 口径：租户维度与全局维度两种形态。"""
    assert build_rate_limit_key(dimension="user", target="1001", tenant="t1") == "bms:t1:rate:user:1001"
    assert build_rate_limit_key(dimension="client", target="app-1") == "bms:global:rate:client:app-1"


@pytest.mark.kiwi_id(43)
async def test_null_limiter_allows() -> None:
    """占位限流器恒定放行（不连 Redis、不计数）。"""
    limiter = NullRateLimiter()
    rule = RateLimitRule(limit=3, window=10)
    decision = await limiter.check("bms:global:rate:user:1", rule)
    assert decision.allowed is True
    assert (decision.limit, decision.remaining, decision.reset_after) == (3, 3, 0)
    assert (await limiter.require("bms:global:rate:user:1", rule)).allowed is True


@pytest.mark.kiwi_id(43)
async def test_require_raises_rate_limit() -> None:
    """拒绝限流器下强制放行抛 RateLimitError（10005 / 429）。"""
    with pytest.raises(RateLimitError) as excinfo:
        await DenyRateLimiter().require("bms:global:rate:user:1", RateLimitRule(limit=1))
    assert excinfo.value.code == 10005
    assert excinfo.value.http_status == 429


@pytest.mark.kiwi_id(43)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位限流器；路由经 get_rate_limiter 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.rate_limiter, NullRateLimiter)

        @app.get("/rate")
        async def rate_info(  # pyright: ignore[reportUnusedFunction]
            limiter: Annotated[BaseRateLimiter, Depends(get_rate_limiter)],
        ) -> dict[str, object]:
            key = build_rate_limit_key(dimension="user", target="1", tenant="t1")
            decision = await limiter.check(key, RateLimitRule(limit=5))
            return {
                "key": limiter.key,
                "type": type(limiter).__name__,
                "allowed": decision.allowed,
                "limit": decision.limit,
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/rate")

        assert resp.status_code == 200
        assert resp.json() == {"key": "rate_limiter", "type": "NullRateLimiter", "allowed": True, "limit": 5}
