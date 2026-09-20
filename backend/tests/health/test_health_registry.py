"""健康检查项注册表基座契约与聚合模板测试（Kiwi 45 / 65）。"""

import asyncio
import time
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_health_check_registry
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.fallback.base import DEPENDENCIES as FALLBACK_DEPENDENCIES
from app.health.base import (
    DEPENDENCIES,
    BaseHealthCheck,
    BaseHealthCheckRegistry,
    HealthCheckReport,
    HealthCheckResult,
)
from app.health.null import NullHealthCheckRegistry
from app.health.registry import HealthCheckRegistry
from app.main import ApplicationFactory, lifespan


class _PassingCheck(BaseHealthCheck):
    """测试用通过检查项（可配延迟与起止时刻，供并发 / 超时用例）。"""

    def __init__(self, name: str, *, delay: float = 0.0) -> None:
        self._name = name
        self._delay = delay
        self.started_at: float | None = None
        self.finished_at: float | None = None

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"通过检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        self.started_at = time.monotonic()
        if self._delay:
            await asyncio.sleep(self._delay)
        self.finished_at = time.monotonic()
        return HealthCheckResult(name=self._name, ok=True)


class _FailingCheck(BaseHealthCheck):
    """测试用未通过检查项。"""

    @property
    def key(self) -> str:
        return "redis"

    def describe(self) -> str:
        return "未通过检查项 redis"

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self.key, ok=False, error="ConnectionError")


class _RaisingCheck(BaseHealthCheck):
    """测试用抛错检查项。"""

    def __init__(self, name: str = "database") -> None:
        self._name = name

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"抛错检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        raise RuntimeError("探针异常")


@pytest.mark.kiwi_id(45)
def test_inheritance_and_key() -> None:
    """注册表契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseHealthCheck, BaseObject)
    assert issubclass(BaseHealthCheckRegistry, BaseCapability)
    assert issubclass(NullHealthCheckRegistry, BaseHealthCheckRegistry)
    assert issubclass(NullHealthCheckRegistry, BaseNullObject)
    assert issubclass(HealthCheckRegistry, BaseHealthCheckRegistry)
    assert BaseHealthCheckRegistry.key == "health_check_registry"

    registry = NullHealthCheckRegistry()
    assert registry.placeholder is True
    assert "占位实现" in registry.describe()


@pytest.mark.kiwi_id(45)
async def test_base_health_check_contract() -> None:
    """检查项契约可引用：实现 name + 异步 check。"""
    check = _PassingCheck("minio")
    assert check.name == "minio"
    result = await check.check()
    assert result == HealthCheckResult(name="minio", ok=True)


@pytest.mark.kiwi_id(45)
def test_dependencies_reuse() -> None:
    """依赖标识清单单向复用降级域（同一对象，命名口径统一）。"""
    assert DEPENDENCIES is FALLBACK_DEPENDENCIES
    assert DEPENDENCIES == (
        "redis",
        "database",
        "rocketmq",
        "elasticsearch",
        "minio",
        "mail_sms",
        "external_api",
    )


@pytest.mark.kiwi_id(45)
def test_result_and_report_contract() -> None:
    """结果 / 报告数据契约：响应形态字段与不可变（frozen）。"""
    result = HealthCheckResult(name="database", ok=True)
    assert result.error is None
    assert HealthCheckReport(ok=True).checks == ()

    field = "ok"
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, False)


@pytest.mark.kiwi_id(45)
async def test_aggregate_all_healthy() -> None:
    """聚合模板（全通过）：顺序＝注册顺序、总体就绪。"""
    registry = HealthCheckRegistry()
    registry.register(_PassingCheck("database"))
    registry.register(_PassingCheck("redis"))

    report = await registry.aggregate()
    assert report.ok is True
    assert [item.name for item in report.checks] == ["database", "redis"]
    assert all(item.ok for item in report.checks)


@pytest.mark.kiwi_id(45)
async def test_aggregate_with_failure() -> None:
    """聚合模板（含失败项）：总体未就绪、其余项仍在。"""
    registry = HealthCheckRegistry()
    registry.register(_PassingCheck("database"))
    registry.register(_FailingCheck())

    report = await registry.aggregate()
    assert report.ok is False
    assert [item.name for item in report.checks] == ["database", "redis"]
    assert report.checks[1].error == "ConnectionError"


@pytest.mark.kiwi_id(45)
async def test_aggregate_handles_exception() -> None:
    """聚合模板（单项抛异常）：该项未就绪且 error 为异常类名、不中断其他项。"""
    registry = HealthCheckRegistry()
    registry.register(_RaisingCheck())
    registry.register(_PassingCheck("redis"))

    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0] == HealthCheckResult(name="database", ok=False, error="RuntimeError")
    assert report.checks[1].ok is True


@pytest.mark.kiwi_id(65)
async def test_aggregate_is_concurrent() -> None:
    """聚合模板并发执行：两项慢检查执行区间重叠（非串行）。"""
    first = _PassingCheck("database", delay=0.05)
    second = _PassingCheck("redis", delay=0.05)
    registry = HealthCheckRegistry()
    registry.register(first)
    registry.register(second)

    report = await registry.aggregate()

    assert report.ok is True
    assert first.started_at is not None and first.finished_at is not None
    assert second.started_at is not None and second.finished_at is not None
    assert first.started_at < second.finished_at
    assert second.started_at < first.finished_at


@pytest.mark.kiwi_id(65)
async def test_aggregate_item_timeout() -> None:
    """单项超时：超时检查项记 TimeoutError，其他项不受影响。"""
    registry = HealthCheckRegistry(check_timeout_ms=30, total_timeout_ms=1000)
    registry.register(_PassingCheck("database", delay=0.2))
    registry.register(_PassingCheck("redis"))

    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0] == HealthCheckResult(name="database", ok=False, error="TimeoutError")
    assert report.checks[1].ok is True


@pytest.mark.kiwi_id(65)
async def test_aggregate_total_timeout() -> None:
    """整体超时：未完成项统一记 TimeoutError（单项超时未触发）。"""
    registry = HealthCheckRegistry(check_timeout_ms=1000, total_timeout_ms=30)
    registry.register(_PassingCheck("database", delay=0.2))
    registry.register(_PassingCheck("redis", delay=0.2))

    report = await registry.aggregate()
    assert report.ok is False
    assert [item.error for item in report.checks] == ["TimeoutError", "TimeoutError"]


@pytest.mark.kiwi_id(45)
async def test_null_registry_fixed_pass() -> None:
    """占位注册表固定通过：注册被忽略、无检查项、不探依赖。"""
    registry = NullHealthCheckRegistry()
    registry.register(_FailingCheck())
    registry.register(_RaisingCheck())

    assert registry.checks() == ()
    report = await registry.aggregate()
    assert report.ok is True
    assert report.checks == ()


@pytest.mark.kiwi_id(45)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配真实注册表；路由经 get_health_check_registry 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.health_check_registry, HealthCheckRegistry)

        @app.get("/health-registry-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            registry: Annotated[BaseHealthCheckRegistry, Depends(get_health_check_registry)],
        ) -> dict[str, object]:
            return {"key": registry.key, "type": type(registry).__name__}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health-registry-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "health_check_registry", "type": "HealthCheckRegistry"}
