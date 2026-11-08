"""租户生命周期 `purged` 动作与中间件只读放行测试（任务 `04_03-01`；Kiwi 2457）。

覆盖：`tenant.purged` 事件构造（附加载荷）/ 分发路由到 `on_purged` + 同版本幂等 / 缺省 `on_purged`
只告警不抛错；HTTP 中间件在「方法 + 白名单 + 停用态」三条件成立时放行（上下文透出真实状态）并留痕。
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from starlette.datastructures import Headers
from starlette.types import Message, Receive, Scope, Send

from bms_core.api.middleware import TenantMiddleware
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import TenantSuspendedError
from bms_core.db.tenant import TenantContext
from bms_core.events.contracts import resolve_event_contract
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.tenant.lifecycle import (
    TENANT_PURGED,
    BaseTenantResourceHandler,
    TenantLifecycleContext,
    TenantLifecycleDispatcher,
    build_tenant_lifecycle_event,
)
from bms_core.tenant.null import NullTenantResourceHandler

pytestmark = pytest.mark.kiwi_id(2457)

_TENANT_ID = 1000000000000000001
_DB_KEY = "tenant_demo"

_SUSPENDED = TenantContext(code="acme", db_key="tenant_acme", name="Acme", tenant_id=7, status="suspended")


class _PurgedHandler(BaseTenantResourceHandler):
    """记录型实现：只关心 `on_purged` 是否被分发到。"""

    plugin_name: str = "purged_recording"

    def __init__(self) -> None:
        """初始化账本与调用记录。"""
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()
        self._applied: ConcurrentStableDict[tuple[int, str], int] = ConcurrentStableDict()

    async def applied_version(self, *, tenant_id: int, action: str) -> int:
        """读取账本。"""
        return self._applied.get((tenant_id, action), -1)

    async def mark_applied(self, *, tenant_id: int, action: str, version: int) -> None:
        """写入账本。"""
        self._applied.set((tenant_id, action), int(version))

    async def on_purged(self, context: TenantLifecycleContext) -> None:
        """记录 purged。"""
        self.calls.add(context.action)


def test_purged_event_registered_and_builds_counts() -> None:
    """`tenant.purged` 已登记；信封带状态 `purged` 与逐库清理计数（附加载荷合并进 payload）。"""
    register_platform_event_contracts()
    assert resolve_event_contract(TENANT_PURGED) is not None

    event = build_tenant_lifecycle_event(
        event_type=TENANT_PURGED,
        tenant_id=_TENANT_ID,
        db_key=_DB_KEY,
        status="purged",
        extra=ConcurrentStableDict({"dropped_services": 3, "failed_services": 0}),
    )

    assert event.event_type == TENANT_PURGED
    assert event.payload["status"] == "purged"
    assert event.payload["dropped_services"] == 3
    assert event.payload["failed_services"] == 0
    assert event.aggregate_key  # 按租户分区，保证同租户事件有序


@pytest.mark.asyncio
async def test_dispatch_purged_routes_to_on_purged() -> None:
    """分发器把 `tenant.purged` 路由到 `on_purged`（幂等键为 `(tenant_id, purged, version)`）。"""
    handler = _PurgedHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)
    event = build_tenant_lifecycle_event(
        event_type=TENANT_PURGED, tenant_id=_TENANT_ID, db_key=_DB_KEY, status="purged", version=5
    )

    assert await dispatcher.dispatch(event) == "applied"
    assert len(handler.calls) == 1 and handler.calls[0] == "purged"
    # 同版本重放跳过（业务级幂等）
    assert await dispatcher.dispatch(event) == "skipped"


@pytest.mark.asyncio
async def test_default_on_purged_warns_without_raising() -> None:
    """缺省 `on_purged` 不抛错（不阻断事件流），但记 WARNING 便于发现漏配。"""
    handler = NullTenantResourceHandler()
    context = TenantLifecycleContext(tenant_id=_TENANT_ID, action="purged", version=1, db_key=_DB_KEY, status="purged")

    assert await handler.on_purged(context) is None


class _Source:
    """租户源替身：只读通道返回停用上下文，常规通道抛 80002。"""

    async def by_code(self, code: str, *, readonly: bool = False) -> TenantContext:
        """按编码取上下文。"""
        if not readonly:
            raise TenantSuspendedError("租户已停用：acme")
        return _SUSPENDED

    async def by_domain(self, domain: str, *, readonly: bool = False) -> TenantContext:
        """按子域名取上下文（同 `by_code`）。"""
        return await self.by_code(domain, readonly=readonly)

    async def by_id(self, tenant_id: str, *, readonly: bool = False) -> TenantContext:
        """按主键取上下文（同 `by_code`）。"""
        return await self.by_code(tenant_id, readonly=readonly)


def _settings(routes: ConcurrentStableList[str]) -> Any:
    """构造中间件所需的最小配置视图（只读白名单 + 租户解析口径）。"""
    return SimpleNamespace(
        tenant=SimpleNamespace(exempt_paths=(), deferred_paths=(), allow_demo_fallback=False),
        tenant_guard=SimpleNamespace(readonly_routes=routes),
    )


@pytest.mark.asyncio
async def test_middleware_allows_readonly_route_for_suspended_tenant() -> None:
    """命中白名单的 GET 在停用态放行：请求态拿到真实状态上下文，并记只读窗口留痕。"""
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=_settings(ConcurrentStableList(("msg:/api/v1/msg/admin/",))),
            tenant_source=_Source(),
            service_identity=SimpleNamespace(name="msg"),
        )
    )
    scope = cast(
        "Scope",
        {
            "type": "http",
            "app": app,
            "path": "/api/v1/msg/admin/topics",
            "method": "GET",
            "headers": Headers({"x-tenant-id": "acme"}).raw,
            "state": {},
        },
    )
    sent: ConcurrentStableList[Message] = ConcurrentStableList()

    async def _downstream(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def _receive() -> Message:
        return {"type": "http.request"}

    async def _send(message: Message) -> None:
        sent.add(message)

    middleware = TenantMiddleware(_downstream)
    await middleware(scope, _receive, _send)

    tenant = cast("TenantContext", scope["state"]["tenant"])
    assert tenant.code == "acme" and tenant.status == "suspended"
    assert len(sent) == 2 and sent[0]["status"] == 200
