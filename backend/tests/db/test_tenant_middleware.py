"""租户全局中间件测试（Kiwi 1019）：链优先级 / 回落与拒绝 / 豁免 / 上下文复位。"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import register_exception_handlers
from app.api.middleware import TenantMiddleware
from app.core.config import Settings
from app.core.context import get_current_tenant
from app.core.exceptions import TenantNotFoundError, TenantSuspendedError
from app.db.tenant import TenantContext, get_tenant

API_PATH = "/api/v1/who"
EXEMPT_PATH = "/healthz"


class _Source:
    """内存租户源替身（按编码 / 域名命中；可选抛停用异常）。"""

    def __init__(self, tenants: list[TenantContext], *, suspended: set[str] | None = None) -> None:
        self.tenants = {tenant.tenant_code: tenant for tenant in tenants}
        self.suspended = suspended or set()
        self.calls: list[tuple[str, str]] = []

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户（记账）。"""
        self.calls.append(("code", code))
        tenant = self.tenants.get(code)
        if tenant is None:
            raise TenantNotFoundError(f"未知租户：{code}")
        if code in self.suspended:
            raise TenantSuspendedError(f"租户已停用：{code}")
        return tenant

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户（记账）。"""
        self.calls.append(("domain", domain))
        for tenant in self.tenants.values():
            if tenant.domain == domain:
                if tenant.tenant_code in self.suspended:
                    raise TenantSuspendedError(f"租户已停用：{tenant.tenant_code}")
                return tenant
        raise TenantNotFoundError(f"未知租户域名：{domain}")


def _app(source: _Source | None, *, allow_demo_fallback: bool = True) -> FastAPI:
    """构造带租户中间件的最小应用（含请求态 / 上下文 / 依赖三视图接口）。"""
    settings = Settings()
    settings.tenant.allow_demo_fallback = allow_demo_fallback
    app = FastAPI()
    register_exception_handlers(app)
    app.state.settings = settings
    app.state.tenant_source = source
    app.add_middleware(TenantMiddleware)

    @app.get(API_PATH)
    async def who(request: Request) -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        state = request.scope.get("state", {})
        tenant = state.get("tenant")
        return {
            "state": getattr(tenant, "tenant_code", None),
            "context": get_current_tenant(),
        }

    @app.get(EXEMPT_PATH)
    async def health() -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        return {"context": get_current_tenant()}

    return app


async def _get(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    """经 ASGI 内存客户端发起 GET，返回（状态码, JSON）。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path, headers=headers or {})
        return response.status_code, response.json()


@pytest.mark.kiwi_id(1019)
async def test_chain_priority_and_context() -> None:
    """链优先级（子域名 → 请求头 → token 位）与请求态 / 上下文注入、请求结束复位。"""
    demo = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户", domain="demo.bms.example.com")
    acme = TenantContext(tenant_code="acme", db_key="tenant_acme", name="示例租户", domain="acme.bms.example.com")
    source = _Source([demo, acme])
    app = _app(source)

    status, body = await _get(app, API_PATH)
    assert status == 200
    assert body == {"state": "demo", "context": "demo"}  # 无来源回落演示租户

    status, body = await _get(app, API_PATH, {"X-Tenant-ID": "acme"})
    assert (status, body) == (200, {"state": "acme", "context": "acme"})

    status, body = await _get(app, API_PATH, {"Host": "demo.bms.example.com", "X-Tenant-ID": "acme"})
    assert (status, body) == (200, {"state": "demo", "context": "demo"})
    assert source.calls[-1] == ("domain", "demo.bms.example.com")

    assert get_current_tenant() is None  # 请求结束已复位


@pytest.mark.kiwi_id(1019)
async def test_token_tenant_scope_state() -> None:
    """token 租户位读请求态（认证阶段写入即生效；配合外层中间件预置）。"""
    acme = TenantContext(tenant_code="acme", db_key="tenant_acme", name="示例租户")
    source = _Source([acme])

    class _AuthStub:
        """外层认证替身：写入请求态 token 租户位。"""

        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                scope.setdefault("state", {})["tenant_id"] = "acme"
            await self.app(scope, receive, send)

    app = _app(source)
    app.add_middleware(_AuthStub)
    status, body = await _get(app, API_PATH)
    assert (status, body) == (200, {"state": "acme", "context": "acme"})
    assert source.calls == [("code", "acme")]


@pytest.mark.kiwi_id(1019)
async def test_unknown_and_suspended_rejected() -> None:
    """未知租户就地 404 / 80001；停用租户就地 403 / 80002（不进入下游）。"""
    acme = TenantContext(tenant_code="acme", db_key="tenant_acme", name="示例租户")
    source = _Source([acme], suspended={"acme"})
    app = _app(source)

    status, body = await _get(app, API_PATH, {"X-Tenant-ID": "nope"})
    assert status == 404
    assert body["code"] == 80001

    status, body = await _get(app, API_PATH, {"X-Tenant-ID": "acme"})
    assert status == 403
    assert body["code"] == 80002
    assert get_current_tenant() is None


@pytest.mark.kiwi_id(1019)
async def test_exempt_path_skips_resolution() -> None:
    """豁免路径不解析、不设置上下文。"""
    source = _Source([])
    app = _app(source)
    status, body = await _get(app, EXEMPT_PATH)
    assert (status, body) == (200, {"context": None})
    assert source.calls == []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 200  # 文档路径亦豁免（不进租户解析）
    assert source.calls == []


@pytest.mark.kiwi_id(1019)
async def test_no_fallback_and_no_source() -> None:
    """prod 口径（关闭回落）无来源拒绝；租户源未装配时未知租户拒绝、demo 兜底。"""
    app = _app(_Source([]), allow_demo_fallback=False)
    status, body = await _get(app, API_PATH)
    assert status == 404
    assert body["code"] == 80001

    bare = _app(None)
    status, body = await _get(bare, API_PATH, {"X-Tenant-ID": "demo"})
    assert (status, body) == (200, {"state": "demo", "context": "demo"})
    status, _ = await _get(bare, API_PATH, {"X-Tenant-ID": "nope"})
    assert status == 404


@pytest.mark.kiwi_id(1019)
async def test_tenant_dependency_reads_state() -> None:
    """`get_tenant` 依赖读请求态（中间件解析结果），豁免路径返回 None。"""
    demo = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")
    app = _app(_Source([demo]))

    @app.get("/dep")
    async def dep(tenant: Annotated[TenantContext | None, Depends(get_tenant)]) -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        return {"code": tenant.tenant_code if tenant else None}

    status, body = await _get(app, "/dep")
    assert (status, body) == (200, {"code": "demo"})


@pytest.mark.kiwi_id(1019)
async def test_tenant_dependency_without_middleware() -> None:
    """未经租户中间件的装配（请求态无 tenant 键）：依赖就地解析（源装配 / 源缺失兜底）。"""
    demo = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")
    app = FastAPI()
    register_exception_handlers(app)
    app.state.settings = Settings()
    app.state.tenant_source = _Source([demo])

    @app.get("/dep")
    async def dep(tenant: Annotated[TenantContext | None, Depends(get_tenant)]) -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        return {"code": tenant.tenant_code if tenant else None}

    status, body = await _get(app, "/dep")
    assert (status, body) == (200, {"code": "demo"})

    bare = FastAPI()
    register_exception_handlers(bare)

    @bare.get("/dep")
    async def bare_dep(tenant: Annotated[TenantContext | None, Depends(get_tenant)]) -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        return {"code": tenant.tenant_code if tenant else None}

    status, body = await _get(bare, "/dep")
    assert (status, body) == (200, {"code": "demo"})  # 无源：内置演示租户兜底


@pytest.mark.kiwi_id(1019)
async def test_non_http_passthrough() -> None:
    """非 HTTP 作用域直通（lifespan 等不解析租户）。"""
    calls: list[str] = []

    async def _downstream(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(str(scope["type"]))

    middleware = TenantMiddleware(_downstream)
    scope: Scope = {"type": "lifespan"}
    await middleware(scope, None, None)  # type: ignore[arg-type]
    assert calls == ["lifespan"]
