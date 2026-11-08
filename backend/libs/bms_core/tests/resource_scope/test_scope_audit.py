"""作用域错误码与审计上下文（07D 需求 01-3）：文案键、同码、审计载荷。

覆盖详细设计 §3.5 用例 11~14：
- 六类错误码（`80001` / `80002` / `82009` ~ `82012`）中英文案键非空；
- 管理面与数据面同码（同一异常类、同一 `code` / `http_status`）；
- 审计载荷带作用域字段（有上下文）与不写空字段（无上下文）。
"""

from collections.abc import Callable, Iterator
from typing import Annotated, Any, cast

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from bms_core.api import audit_middleware as middleware_module
from bms_core.audit.events import build_operation_event
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import AuditLogSettings, get_settings
from bms_core.core.context import reset_tenant_context, set_tenant_context
from bms_core.core.exceptions import ScopeResourceOutOfBoundsError
from bms_core.db.tenant import TenantContext
from bms_core.events.base import EventEnvelope
from bms_core.i18n.error_seed import ERROR_MESSAGES
from bms_core.resource_scope import (
    BaseScopeResolver,
    ResolvedScope,
    SourceScopeResolver,
    require_scope,
)
from bms_core.resource_scope import resolver as resolver_module
from bms_core.resource_scope.base import (
    ScopeResourceTypeRecord,
    register_scope_resource_types,
    reset_scope_resource_types,
)
from bms_core.services.module_registry import (
    ModuleRecord,
    register_service_records,
    reset_service_records,
)
from bms_core.tenant.guard import BaseTenantGuard, TenantTarget

pytestmark = pytest.mark.kiwi_id(2448)

_TENANT_ID = 1000000000000000001
_TARGET = TenantTarget(tenant_id=str(_TENANT_ID))
_TOPIC_PATTERN = "^[a-z][a-z0-9_]{0,15}$"
_OVERLONG = "x" * 40
_EVENTS: list[EventEnvelope] = []  # bare-collections:allow（测试断言容器）


def _context() -> TenantContext:
    """演示租户上下文（含雪花主键）。

    Returns:
        TenantContext: 租户上下文。
    """
    return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=_TENANT_ID)


class _StubGuard(BaseTenantGuard):
    """占位守卫：固定返回上下文。"""

    plugin_name: str = "stub_audit"

    async def resolve(self, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
        """返回预置上下文。

        Args:
            target: 租户定位（占位忽略）。
            readonly: 只读通道（占位忽略）。

        Returns:
            TenantContext: 预置上下文。
        """
        del target, readonly
        return _context()


def _resolver() -> SourceScopeResolver:
    """构造默认实现（守卫为占位）。

    Returns:
        SourceScopeResolver: 解析器。
    """
    guard = _StubGuard()
    return SourceScopeResolver(guard_provider=lambda: guard)


def _provider(resolver: BaseScopeResolver) -> Callable[[Request], BaseScopeResolver]:
    """构造依赖注入提供者（固定返回给定解析器）。

    Args:
        resolver: 解析器实例。

    Returns:
        Callable[[Request], BaseScopeResolver]: 零副作用提供者。
    """

    def _provide(request: Request) -> BaseScopeResolver:
        """返回固定解析器。

        Args:
            request: 请求对象（未使用）。

        Returns:
            BaseScopeResolver: 解析器。
        """
        del request
        return resolver

    return _provide


class _FakeEmitter:
    """记录型发射器替身。"""

    def __init__(self, **kwargs: object) -> None:
        del kwargs

    async def emit(self, event: EventEnvelope) -> bool:
        """记录事件并返回成功。

        Args:
            event: 审计事件。

        Returns:
            bool: 恒 True。
        """
        _EVENTS.append(event)
        return True


def _audit_settings() -> AuditLogSettings:
    """构造审计日志参数（与基线一致，开启记录）。

    Returns:
        AuditLogSettings: 审计参数。
    """
    return AuditLogSettings.model_validate(
        {
            "enabled": True,
            "record_methods": ConcurrentStableList(["POST", "PUT", "PATCH", "DELETE"]),
            "exclude_paths": ConcurrentStableList(["/api/v1/auth/login"]),
            "max_param_bytes": 8192,
            "query_default_days": 30,
            "max_query_days": 366,
            "precreate_months_ahead": 1,
            "chain_verify_months": 2,
        }
    )


def _audit_app() -> FastAPI:
    """构造带作用域依赖与审计中间件的测试应用。

    Returns:
        FastAPI: 应用实例。
    """
    app = FastAPI()

    @app.get("/api/v1/demo/{resource_key}")
    async def read_demo(  # pyright: ignore[reportUnusedFunction]
        resource_key: str,
        scope: Annotated[ResolvedScope, Depends(require_scope("demo", "demo.topic"))],
        request: Request,
    ) -> JSONResponse:
        """回显作用域并声明读接口纳入审计。"""
        del resource_key
        request.state.audit_read = True
        return JSONResponse({"module_key": scope.module_key, "resource_key": scope.resource_key})

    app.add_middleware(
        middleware_module.OperationAuditMiddleware,
        settings=_audit_settings(),
        app_settings=get_settings(),
    )
    app.state.engine_registry = object()
    app.state.session_factory = object()
    return app


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """替换发射器、复位上下文与登记态，并装载最小登记集。

    Args:
        monkeypatch: 补丁器。

    Yields:
        None: 用例运行期。
    """
    _EVENTS.clear()
    monkeypatch.setattr(middleware_module, "AuditEventEmitter", _FakeEmitter)
    reset_scope_resource_types()
    reset_service_records()
    register_service_records(
        ConcurrentStableList(
            [
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    service_group="product",
                    product_key="demo",
                )
            ]
        )
    )
    register_scope_resource_types(
        ConcurrentStableList(
            [
                ScopeResourceTypeRecord(
                    resource_type_key="demo.topic",
                    name="主题",
                    name_pattern=_TOPIC_PATTERN,
                    max_length=16,
                    product_key="demo",
                )
            ]
        )
    )
    try:
        yield
    finally:
        reset_scope_resource_types()
        reset_service_records()


def test_six_scope_error_codes_have_bilingual_seeds() -> None:
    """六类作用域失败码均有中英两行文案（不裸奔、不空串）。"""
    seeded = {code: (zh, en) for code, zh, en in ERROR_MESSAGES}

    for code in (80001, 80002, 82009, 82010, 82011, 82012):
        assert code in seeded, f"缺少文案：{code}"
        zh, en = seeded[code]
        assert zh.strip() and en.strip(), f"文案为空：{code}"


async def test_same_code_on_management_and_data_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一失败在 `require` 与 HTTP 依赖上抛同类异常，码与状态一致。"""
    resolver = _resolver()
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(resolver))

    with pytest.raises(ScopeResourceOutOfBoundsError) as data_error:
        await resolver.require(_TARGET, module_key="demo", resource_type="demo.topic", resource_key=_OVERLONG)

    token = set_tenant_context(_context())
    try:
        dependency = require_scope("demo", "demo.topic")
        with pytest.raises(ScopeResourceOutOfBoundsError) as http_error:
            await dependency(_request(path_params={"resource_key": _OVERLONG}))
    finally:
        reset_tenant_context(token)

    assert data_error.value.code == http_error.value.code == 82012
    assert data_error.value.http_status == http_error.value.http_status == 403


def test_operation_event_writes_scope_fields() -> None:
    """载荷：传入作用域字段即写入，值为原样。"""
    event = build_operation_event(
        tenant_id=str(_TENANT_ID),
        user_id=1,
        username="alice",
        module="demo",
        action="demo:read",
        method="GET",
        path="/api/v1/demo/news",
        query=None,
        params=None,
        ip=None,
        user_agent=None,
        cost_time=1,
        status=200,
        error_msg=None,
        module_key="demo",
        resource_key="news",
    )

    assert event.payload["module_key"] == "demo"
    assert event.payload["resource_key"] == "news"


def test_operation_event_omits_absent_scope_fields() -> None:
    """载荷：不传作用域字段即不写键（不是空串、不是 null）。"""
    event = build_operation_event(
        tenant_id=None,
        user_id=None,
        username=None,
        module="core",
        action="core:read",
        method="GET",
        path="/healthz",
        query=None,
        params=None,
        ip=None,
        user_agent=None,
        cost_time=0,
        status=200,
        error_msg=None,
    )

    assert "module_key" not in event.payload
    assert "resource_key" not in event.payload


async def test_audit_middleware_carries_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """集成：走过 `require_scope` 的请求，审计载荷带模块键与资源标识。"""
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(_resolver()))
    app = _audit_app()
    token = set_tenant_context(_context())

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/demo/news")
    finally:
        reset_tenant_context(token)

    assert response.status_code == 200
    assert len(_EVENTS) == 1
    payload = _EVENTS[0].payload
    assert payload["module_key"] == "demo"
    assert payload["resource_key"] == "news"


def _request(
    *,
    path_params: dict[str, str] | None = None,  # bare-collections:allow（ASGI 原生 dict）
) -> Request:
    """构造最小 HTTP 请求。

    Args:
        path_params: 路径参数。

    Returns:
        Request: Starlette 请求对象。
    """
    scope: dict[str, Any] = {  # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
        "type": "http",
        "method": "GET",
        "path": "/api/v1/demo/news",
        "headers": [],
        "query_string": b"",
    }
    if path_params:
        scope["path_params"] = path_params
    return Request(cast("Any", scope))
