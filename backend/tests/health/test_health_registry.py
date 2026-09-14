"""健康检查项注册表基座契约测试（Kiwi 45）：继承 / 常量复用 / 结果契约 / 聚合模板 / 占位固定通过 / 依赖解析。"""

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
    NullHealthCheckRegistry,
)
from app.main import create_app


class _PassingCheck(BaseHealthCheck):
    """测试用通过检查项。"""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self._name, healthy=True)


class _FailingCheck(BaseHealthCheck):
    """测试用未通过检查项。"""

    @property
    def name(self) -> str:
        return "redis"

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self.name, healthy=False, detail="连接失败")


class _RaisingCheck(BaseHealthCheck):
    """测试用抛错检查项。"""

    @property
    def name(self) -> str:
        return "database"

    async def check(self) -> HealthCheckResult:
        raise RuntimeError("探针异常")


class _InMemoryRegistry(BaseHealthCheckRegistry):
    """测试用内存注册表：验证聚合模板（真实注册表随 03_03 回补）。"""

    def __init__(self) -> None:
        self._checks: list[BaseHealthCheck] = []

    def register(self, check: BaseHealthCheck) -> None:
        self._checks.append(check)

    def checks(self) -> tuple[BaseHealthCheck, ...]:
        return tuple(self._checks)


@pytest.mark.kiwi_id(45)
def test_inheritance_and_key() -> None:
    """注册表契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseHealthCheck, BaseObject)
    assert issubclass(BaseHealthCheckRegistry, BaseCapability)
    assert issubclass(NullHealthCheckRegistry, BaseHealthCheckRegistry)
    assert issubclass(NullHealthCheckRegistry, BaseNullObject)
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
    assert result == HealthCheckResult(name="minio", healthy=True)


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
    """结果 / 报告数据契约：默认值与不可变（frozen）。"""
    result = HealthCheckResult(name="database", healthy=True)
    assert result.detail is None
    assert HealthCheckReport(healthy=True).items == ()

    field = "healthy"
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, False)


@pytest.mark.kiwi_id(45)
async def test_aggregate_all_healthy() -> None:
    """聚合模板（全通过）：顺序＝注册顺序、总体就绪。"""
    registry = _InMemoryRegistry()
    registry.register(_PassingCheck("database"))
    registry.register(_PassingCheck("redis"))

    report = await registry.aggregate()
    assert report.healthy is True
    assert [item.name for item in report.items] == ["database", "redis"]
    assert all(item.healthy for item in report.items)


@pytest.mark.kiwi_id(45)
async def test_aggregate_with_failure() -> None:
    """聚合模板（含失败项）：总体未就绪、其余项仍在。"""
    registry = _InMemoryRegistry()
    registry.register(_PassingCheck("database"))
    registry.register(_FailingCheck())

    report = await registry.aggregate()
    assert report.healthy is False
    assert [item.name for item in report.items] == ["database", "redis"]
    assert report.items[1].detail == "连接失败"


@pytest.mark.kiwi_id(45)
async def test_aggregate_handles_exception() -> None:
    """聚合模板（单项抛异常）：该项未就绪且不泄露异常、不中断其他项。"""
    registry = _InMemoryRegistry()
    registry.register(_RaisingCheck())
    registry.register(_PassingCheck("redis"))

    report = await registry.aggregate()
    assert report.healthy is False
    assert report.items[0] == HealthCheckResult(name="database", healthy=False, detail="检查执行异常")
    assert report.items[1].healthy is True


@pytest.mark.kiwi_id(45)
async def test_null_registry_fixed_pass() -> None:
    """占位注册表固定通过：注册被忽略、无检查项、不探依赖。"""
    registry = NullHealthCheckRegistry()
    registry.register(_FailingCheck())
    registry.register(_RaisingCheck())

    assert registry.checks() == ()
    report = await registry.aggregate()
    assert report.healthy is True
    assert report.items == ()


@pytest.mark.kiwi_id(45)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位注册表；路由经 get_health_check_registry 取到同一实例。"""
    app = create_app()
    assert isinstance(app.state.health_check_registry, NullHealthCheckRegistry)

    @app.get("/health-registry-probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        registry: Annotated[BaseHealthCheckRegistry, Depends(get_health_check_registry)],
    ) -> dict[str, object]:
        return {"key": registry.key, "type": type(registry).__name__}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health-registry-probe")

    assert resp.status_code == 200
    assert resp.json() == {"key": "health_check_registry", "type": "NullHealthCheckRegistry"}
