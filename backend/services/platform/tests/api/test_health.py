"""健康检查路由测试：/healthz 存活 + /readyz 就绪契约与启动完成态（Kiwi 2 / 64 / 65）。"""

import importlib
import pkgutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import bms_core as app_pkg
from bms_core.core import plugin as plugin_module
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.plugin import BasePluggable, PluginRegistry
from bms_core.health.base import BaseHealthCheck, HealthCheckResult
from bms_core.health.registry import HealthCheckRegistry
from bms_platform.main import ApplicationFactory


class _PassingCheck(BaseHealthCheck):
    """测试用通过检查项。"""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"通过检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self._name, ok=True)


class _FailingCheck(BaseHealthCheck):
    """测试用不可达检查项：抛出的异常信息含敏感串（验证响应不泄露）。"""

    def __init__(self, name: str = "redis") -> None:
        self._name = name

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"不可达检查项 {self._name}"

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


def _use_fake_registry(monkeypatch: pytest.MonkeyPatch, fake: HealthCheckRegistry) -> None:
    """以隔离注册表 + 自定义配置注入测试注册表（provider=test，替换进程级默认注册表）。

    Args:
        monkeypatch: pytest 补丁夹具。
        fake: 测试注册表实例。
    """
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="bms_core."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)
    registry = PluginRegistry()
    pending = list(BasePluggable.__subclasses__())
    while pending:
        cls = pending.pop()
        if cls.__module__.startswith("bms_core."):
            registry.collect(cls)
        pending.extend(cls.__subclasses__())
    registry.register("health_check_registry", "test", lambda: fake)
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    monkeypatch.setattr(
        "bms_platform.main.get_settings",
        lambda: Settings(health_check_registry=PluginSelection(provider="test")),
    )


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
async def test_readyz_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """全部检查项就绪：200 + status ok + checks 动态键结构（注册顺序）。"""
    _use_fake_registry(monkeypatch, _registry(_PassingCheck("redis"), _PassingCheck("database")))
    app = ApplicationFactory().create(None)

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
async def test_readyz_failure_returns_503_without_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    """检查项不可达：503 + status down + error 为异常类名且不泄露敏感串。"""
    _use_fake_registry(monkeypatch, _registry(_PassingCheck("database"), _FailingCheck("redis")))
    app = ApplicationFactory().create(None)

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
async def test_readyz_omits_unregistered_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注册检查项（如阶段八前的 minio）从 checks 省略，不做「未接入即失败」判定。"""
    _use_fake_registry(monkeypatch, _registry(_PassingCheck("redis")))
    app = ApplicationFactory().create(None)

    async with _lifespan_client(app) as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 200
    checks = resp.json()["checks"]
    assert list(checks) == ["redis"]
    assert "minio" not in checks


@pytest.mark.kiwi_id(65)
async def test_readyz_startup_incomplete_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """lifespan 未启动（startup_complete=False）：503 + 空 checks，不执行依赖探测。"""
    _use_fake_registry(monkeypatch, _registry(_FailingCheck("redis")))
    app = ApplicationFactory().create(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 503
    assert resp.json() == {"status": "down", "checks": {}}


@pytest.mark.kiwi_id(65)
async def test_readyz_after_lifespan_startup_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """lifespan 启动完成后（startup_complete=True）就绪检查正常聚合。"""
    _use_fake_registry(monkeypatch, _registry(_PassingCheck("redis")))
    app = ApplicationFactory().create(None)

    async with _lifespan_client(app) as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
