"""熔断基座契约测试（Kiwi 42）：继承 / 三态与清单复用 / 占位恒定闭合 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_circuit_breaker
from bms_core.circuit.base import (
    DEPENDENCIES as CIRCUIT_DEPENDENCIES,
)
from bms_core.circuit.base import BaseCircuitBreaker, CircuitState
from bms_core.circuit.null import NullCircuitBreaker
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.fallback.base import (
    DEPENDENCIES as FALLBACK_DEPENDENCIES,
)
from bms_platform.main import ApplicationFactory, lifespan


@pytest.mark.kiwi_id(42)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseCircuitBreaker, BaseCapability)
    assert issubclass(NullCircuitBreaker, BaseCircuitBreaker)
    assert issubclass(NullCircuitBreaker, BaseNullObject)
    assert BaseCircuitBreaker.key == "circuit_breaker"

    breaker = NullCircuitBreaker()
    assert breaker.placeholder is True
    assert "占位实现" in breaker.describe()


@pytest.mark.kiwi_id(42)
def test_state_enum_and_shared_dependencies() -> None:
    """熔断三态枚举就位；依赖清单与降级域为同一对象（单向复用，不另立清单）。"""
    assert [state.value for state in CircuitState] == ["closed", "open", "half_open"]
    assert CIRCUIT_DEPENDENCIES is FALLBACK_DEPENDENCIES


@pytest.mark.kiwi_id(42)
async def test_null_breaker_always_closed() -> None:
    """占位熔断器恒定闭合：清单内各依赖均放行、状态恒 closed、记录调用不改变状态。"""
    breaker = NullCircuitBreaker()
    for dependency in FALLBACK_DEPENDENCIES:
        assert await breaker.allow(dependency) is True
        assert await breaker.state(dependency) is CircuitState.CLOSED

    await breaker.record_failure("redis")
    assert await breaker.state("redis") is CircuitState.CLOSED
    await breaker.record_success("redis")
    assert await breaker.state("redis") is CircuitState.CLOSED
    assert await breaker.allow("redis") is True


@pytest.mark.kiwi_id(42)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位熔断器；路由经 get_circuit_breaker 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.circuit_breaker, NullCircuitBreaker)

        @app.get("/circuit")
        async def circuit_info(  # pyright: ignore[reportUnusedFunction]
            breaker: Annotated[BaseCircuitBreaker, Depends(get_circuit_breaker)],
        ) -> dict[str, str]:
            return {
                "key": breaker.key,
                "type": type(breaker).__name__,
                "state": (await breaker.state("redis")).value,
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/circuit")

        assert resp.status_code == 200
        assert resp.json() == {"key": "circuit_breaker", "type": "NullCircuitBreaker", "state": "closed"}
