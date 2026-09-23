"""服务应用装配基座测试（Kiwi 1206）：身份 / 路由与探针挂载 / 钩子 / 生命周期。"""

from collections.abc import Sequence

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api.base import BaseRouter, mount_service_routers
from bms_core.application import BaseServiceApplicationFactory, service_lifespan
from bms_core.core.config import Settings

_probe_router = BaseRouter(key="probe", prefix="/probe")


@_probe_router.get("/ping")
async def _ping() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
    """测试用探针路由。

    Returns:
        dict[str, bool]: 固定响应。
    """
    return {"ok": True}


_calls: list[str] = []


class _Factory(BaseServiceApplicationFactory):
    """测试用服务应用工厂（声明身份 + 探针路由 + 钩子）。"""

    key: str = "application_factory"
    service_name: str = "appbase_test"
    service_title: str = "BMS 装配基座测试服务"
    version: str = "9.9.9"
    contract_version: str = "9.9.9"

    def prepare_settings(self, settings: Settings) -> None:
        """记录创建前配置钩子（不调整配置）。

        Args:
            settings: 应用配置。
        """
        del settings
        _calls.append("prepare")

    def configure_service(self, app: FastAPI, settings: Settings) -> None:
        """记录服务 state 注入钩子（写入测试标记）。

        Args:
            app: 应用实例。
            settings: 应用配置。
        """
        del settings
        _calls.append("configure")
        app.state.custom = True

    def service_routers(self) -> Sequence[APIRouter]:
        """业务路由（测试探针，经服务级登记表挂 `/api/v1`）。

        Returns:
            Sequence[APIRouter]: 路由清单。
        """
        return (mount_service_routers((_probe_router,)),)


@pytest.mark.kiwi_id(1206)
async def test_factory_identity_routes_and_probes() -> None:
    """身份就位、业务路由与统一探针挂载、钩子被调用、根路由回显身份。"""
    _calls.clear()
    app = _Factory().create(None)
    assert app.title == "BMS 装配基座测试服务"
    assert app.version == "9.9.9"
    assert app.state.service_identity.name == "appbase_test"
    assert app.state.custom is True
    assert _calls == ["prepare", "configure"]

    paths = set(app.openapi()["paths"])
    assert "/healthz" in paths
    assert "/readyz" in paths
    assert "/api/v1/probe/ping" in paths

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/healthz")
        probe = await client.get("/api/v1/probe/ping")
        root = await client.get("/")
    assert health.status_code == 200
    assert health.json()["service"] == "appbase_test"
    assert probe.json() == {"ok": True}
    assert root.json()["data"] == {"name": "BMS 装配基座测试服务", "version": "9.9.9"}


@pytest.mark.kiwi_id(1206)
async def test_service_lifespan_toggles_readiness() -> None:
    """共享 lifespan：进入置就绪、退出取消就绪并释放资源。"""
    app = _Factory().create(None)
    assert app.state.startup_complete is False
    async with service_lifespan(app):
        assert app.state.startup_complete is True
    assert app.state.startup_complete is False
