"""健康检查路由测试：/healthz 存活 + /readyz 就绪（占位固定通过 / 未就绪 503）。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.health.base import BaseHealthCheck, BaseHealthCheckRegistry, HealthCheckResult
from app.main import create_app


class _UnhealthyCheck(BaseHealthCheck):
    """测试用未就绪检查项。"""

    @property
    def name(self) -> str:
        return "redis"

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self.name, healthy=False, detail="连接失败")


class _UnhealthyRegistry(BaseHealthCheckRegistry):
    """测试用未就绪注册表（验证 /readyz → 503 映射）。"""

    def register(self, check: BaseHealthCheck) -> None:
        return None

    def checks(self) -> tuple[BaseHealthCheck, ...]:
        return (_UnhealthyCheck(),)


@pytest.mark.kiwi_id(2)
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz 返回 {"status":"ok"}。"""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.kiwi_id(45)
async def test_readyz_placeholder_is_ready(client: AsyncClient) -> None:
    """占位注册表下 GET /readyz 返回 200 与空检查项。"""
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": []}


@pytest.mark.kiwi_id(45)
async def test_readyz_unhealthy_returns_503() -> None:
    """存在未就绪检查项时 GET /readyz 返回 503 与明细。"""
    app = create_app()
    app.state.health_check_registry = _UnhealthyRegistry()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")

    assert resp.status_code == 503
    assert resp.json() == {
        "status": "degraded",
        "checks": [{"name": "redis", "healthy": False, "detail": "连接失败"}],
    }
