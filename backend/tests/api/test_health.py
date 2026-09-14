"""健康检查路由测试：/healthz 存活 + /readyz 就绪契约与启动完成态（Kiwi 2 / 64 / 65）。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.health.base import BaseHealthCheck, HealthCheckResult
from app.health.registry import HealthCheckRegistry
from app.main import create_app


class _PassingCheck(BaseHealthCheck):
    """测试用通过检查项。"""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self._name, ok=True)


class _FailingCheck(BaseHealthCheck):
    """测试用不可达检查项：抛出的异常信息含敏感串（验证响应不泄露）。"""

    def __init__(self, name: str = "redis") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def check(self) -> HealthCheckResult:
        raise ConnectionError("redis://bms:secret@127.0.0.1:6379/0 连接失败")


def _registry(*checks: BaseHealthCheck) -> HealthCheckRegistry:
    """构造测试用注册表（按传入顺序注册检查项）。

    Args:
        *checks: 检查项。

    Returns:
        HealthCheckRegistry: 注册表实例。
    """
    registry = HealthCheckRegistry()
    for check in checks:
        registry.register(check)
    return registry


@asynccontextmanager
async def _lifespan_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """运行 lifespan（startup_complete 置 True）并返回测试客户端。

    Args:
        app: 应用实例。

    Yields:
        AsyncClient: 测试客户端（应用运行期）。
    """
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


@pytest.mark.kiwi_id(2)
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz 返回 {"status":"ok"}（不依赖启动完成态）。"""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.kiwi_id(64)
async def test_readyz_all_ok() -> None:
    """全部检查项就绪：200 + status ok + checks 动态键结构（注册顺序）。"""
    app = create_app()
    app.state.health_check_registry = _registry(_PassingCheck("redis"), _PassingCheck("database"))

    async with _lifespan_client(app) as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "status": "ok",
        "checks": {"redis": {"ok": True, "error": None}, "database": {"ok": True, "error": None}},
    }
    assert list(body["checks"]) == ["redis", "database"]


@pytest.mark.kiwi_id(64)
async def test_readyz_failure_returns_503_without_leak() -> None:
    """检查项不可达：503 + status down + error 为异常类名且不泄露敏感串。"""
    app = create_app()
    app.state.health_check_registry = _registry(_PassingCheck("database"), _FailingCheck("redis"))

    async with _lifespan_client(app) as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "down"
    assert body["checks"]["redis"] == {"ok": False, "error": "ConnectionError"}
    assert body["checks"]["database"] == {"ok": True, "error": None}
    assert "secret" not in resp.text
    assert "redis://" not in resp.text
    assert "127.0.0.1" not in resp.text


@pytest.mark.kiwi_id(64)
async def test_readyz_omits_unregistered_checks() -> None:
    """未注册检查项（如阶段八前的 minio）从 checks 省略，不做「未接入即失败」判定。"""
    app = create_app()
    app.state.health_check_registry = _registry(_PassingCheck("redis"))

    async with _lifespan_client(app) as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 200
    checks = resp.json()["checks"]
    assert list(checks) == ["redis"]
    assert "minio" not in checks


@pytest.mark.kiwi_id(65)
async def test_readyz_startup_incomplete_returns_503() -> None:
    """lifespan 未启动（startup_complete=False）：503 + 空 checks，不执行依赖探测。"""
    app = create_app()
    app.state.health_check_registry = _registry(_FailingCheck("redis"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 503
    assert resp.json() == {"status": "down", "checks": {}}


@pytest.mark.kiwi_id(65)
async def test_readyz_after_lifespan_startup_returns_200() -> None:
    """lifespan 启动完成后（startup_complete=True）就绪检查正常聚合。"""
    app = create_app()
    app.state.health_check_registry = _registry(_PassingCheck("redis"))

    async with _lifespan_client(app) as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
