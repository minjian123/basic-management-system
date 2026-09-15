"""降级基座契约测试（Kiwi 42）：继承 / 依赖清单与动作枚举 / 占位不降级 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_fallback_policy
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.fallback.base import DEPENDENCIES, BaseFallbackPolicy, FallbackAction
from app.fallback.null import NullFallbackPolicy
from app.main import create_app


@pytest.mark.kiwi_id(42)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseFallbackPolicy, BaseCapability)
    assert issubclass(NullFallbackPolicy, BaseFallbackPolicy)
    assert issubclass(NullFallbackPolicy, BaseNullObject)
    assert BaseFallbackPolicy.key == "fallback"

    policy = NullFallbackPolicy()
    assert policy.placeholder is True
    assert "占位实现" in policy.describe()


@pytest.mark.kiwi_id(42)
def test_dependencies_and_actions() -> None:
    """依赖清单七项无重复；降级动作四成员就位。"""
    assert DEPENDENCIES == (
        "redis",
        "database",
        "rocketmq",
        "elasticsearch",
        "minio",
        "mail_sms",
        "external_api",
    )
    assert len(set(DEPENDENCIES)) == len(DEPENDENCIES)
    assert [action.value for action in FallbackAction] == ["raise", "default", "skip", "degrade"]


@pytest.mark.kiwi_id(42)
async def test_null_policy_never_degrades() -> None:
    """占位策略恒定不降级：清单内各依赖、未知依赖与带异常场景均返回 raise。"""
    policy = NullFallbackPolicy()
    for dependency in DEPENDENCIES:
        assert await policy.resolve(dependency) is FallbackAction.RAISE
    assert await policy.resolve("unknown-dependency") is FallbackAction.RAISE
    assert await policy.resolve("redis", exc=TimeoutError("boom")) is FallbackAction.RAISE


@pytest.mark.kiwi_id(42)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位降级策略；路由经 get_fallback_policy 取到同一实例。"""
    app = create_app()
    assert isinstance(app.state.fallback_policy, NullFallbackPolicy)

    @app.get("/fallback")
    async def fallback_info(  # pyright: ignore[reportUnusedFunction]
        policy: Annotated[BaseFallbackPolicy, Depends(get_fallback_policy)],
    ) -> dict[str, str]:
        action = await policy.resolve("redis")
        return {"key": policy.key, "type": type(policy).__name__, "action": action.value}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/fallback")

    assert resp.status_code == 200
    assert resp.json() == {"key": "fallback", "type": "NullFallbackPolicy", "action": "raise"}
