"""健康检查项（redis / database）测试（Kiwi 65）。"""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db.registry import EngineRegistry
from app.fallback.base import DEPENDENCIES
from app.health.checks import DatabaseHealthCheck, RedisHealthCheck
from app.health.registry import HealthCheckRegistry


class _FakeRedisClient:
    """测试用 Redis 客户端桩：`ping` 可配置成功 / 抛错，记录关闭状态。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.closed = False

    async def ping(self) -> bool:
        if self._error is not None:
            raise self._error
        return True

    async def aclose(self) -> None:
        self.closed = True


class _StubEngineRegistry:
    """测试用引擎注册表桩：返回注入的引擎 / 抛错。"""

    def __init__(self, *, engine: AsyncEngine | None = None, error: Exception | None = None) -> None:
        self._engine = engine
        self._error = error

    async def get(self, db_key: str = "platform") -> AsyncEngine:
        if self._error is not None:
            raise self._error
        assert self._engine is not None
        return self._engine


def _as_registry(stub: _StubEngineRegistry) -> EngineRegistry:
    """桩注册表类型转换（测试注入用）。

    Args:
        stub: 引擎注册表桩。

    Returns:
        EngineRegistry: 桩（仅类型断言）。
    """
    return cast("EngineRegistry", stub)


def _patch_redis(monkeypatch: pytest.MonkeyPatch, client: _FakeRedisClient) -> None:
    """替换 `Redis.from_url` 为返回指定客户端的桩。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        client: 假客户端。
    """
    monkeypatch.setattr("app.health.checks.Redis.from_url", lambda url: client)  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]


@pytest.mark.kiwi_id(65)
def test_check_names_from_dependencies() -> None:
    """检查项名称取 `DEPENDENCIES`（与降级 / 熔断 / 指标同源）。"""
    redis_check = RedisHealthCheck("redis://localhost:6379/0")
    database_check = DatabaseHealthCheck(_as_registry(_StubEngineRegistry()))
    assert redis_check.name == "redis"
    assert database_check.name == "database"
    assert redis_check.name in DEPENDENCIES
    assert database_check.name in DEPENDENCIES


@pytest.mark.kiwi_id(65)
async def test_redis_check_success_and_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """redis 检查项：`PING` 通过返回就绪；`aclose` 关闭客户端（幂等）。"""
    fake = _FakeRedisClient()
    _patch_redis(monkeypatch, fake)
    check = RedisHealthCheck("redis://localhost:6379/0")

    result = await check.check()
    assert result.ok is True
    assert result.error is None

    await check.aclose()
    assert fake.closed is True


@pytest.mark.kiwi_id(65)
async def test_redis_check_failure_maps_to_class_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """redis 检查项：连接失败异常经聚合兜底为异常类名（不泄露连接串）。"""
    fake = _FakeRedisClient(error=ConnectionError("redis://bms:secret@127.0.0.1:6379/0"))
    _patch_redis(monkeypatch, fake)
    check = RedisHealthCheck("redis://bms:secret@127.0.0.1:6379/0")

    with pytest.raises(ConnectionError):
        await check.check()

    registry = HealthCheckRegistry()
    registry.register(check)
    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0].error == "ConnectionError"
    assert "secret" not in report.to_json()


@pytest.mark.kiwi_id(65)
async def test_database_check_success_with_memory_sqlite() -> None:
    """database 检查项：平台引擎 `SELECT 1` 通过返回就绪（内存 SQLite）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        check = DatabaseHealthCheck(_as_registry(_StubEngineRegistry(engine=engine)))
        result = await check.check()
    finally:
        await engine.dispose()

    assert result.ok is True
    assert result.error is None


@pytest.mark.kiwi_id(65)
async def test_database_check_failure_maps_to_class_name() -> None:
    """database 检查项：取引擎失败经聚合兜底为异常类名。"""
    check = DatabaseHealthCheck(_as_registry(_StubEngineRegistry(error=ConnectionError("platform 库不可达"))))

    with pytest.raises(ConnectionError):
        await check.check()

    registry = HealthCheckRegistry()
    registry.register(check)
    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0].error == "ConnectionError"
