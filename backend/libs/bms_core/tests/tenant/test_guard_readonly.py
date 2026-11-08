"""管理面只读放行口测试（任务 `04_03-01`；Kiwi 2457）。

覆盖：`readonly_route_allowed` 三条件矩阵（方法 / 白名单前缀 / 服务键，缺一即拒、脏配置 fail-closed）；
守卫 `require` / `per_round` / `batch` 的 `readonly` 透传（停用 / 注销照常返回上下文，缺省仍拒）；
`require_sync` 同口径。
"""

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import TenantSuspendedError
from bms_core.db.tenant import TenantContext
from bms_core.tenant.guard import SourceTenantGuard, TenantTarget, readonly_route_allowed

pytestmark = pytest.mark.kiwi_id(2457)

_ROUTES: ConcurrentStableList[str] = ConcurrentStableList(
    ("msg:/api/v1/msg/admin/", "platform:/api/v1/platform/tenants/")
)
"""测试用白名单（服务键 + 路径前缀）。"""

_DELETED = TenantContext(code="acme", db_key="tenant_acme", name="Acme", tenant_id=7, status="deleted")


class _SuspendedSource:
    """租户源替身：只有只读通道能取到「已注销」上下文，常规通道抛 80002。"""

    def __init__(self) -> None:
        """初始化调用记录。"""
        self.readonly_calls: ConcurrentStableList[bool] = ConcurrentStableList()

    async def by_code(self, code: str, *, readonly: bool = False) -> TenantContext:
        """按编码取上下文（只读通道放行，常规通道拒）。"""
        return self._hit(readonly)

    async def by_domain(self, domain: str, *, readonly: bool = False) -> TenantContext:
        """按子域名取上下文（同 `by_code`）。"""
        return self._hit(readonly)

    async def by_id(self, tenant_id: str, *, readonly: bool = False) -> TenantContext:
        """按主键取上下文（同 `by_code`）。"""
        return self._hit(readonly)

    def _hit(self, readonly: bool) -> TenantContext:
        """记录并返回结果。

        Args:
            readonly: 是否只读通道。

        Returns:
            TenantContext: 已注销上下文。

        Raises:
            TenantSuspendedError: 常规通道（80002 / 403）。
        """
        self.readonly_calls.add(readonly)
        if not readonly:
            raise TenantSuspendedError("租户已注销：acme")
        return _DELETED


def _guard(source: _SuspendedSource) -> SourceTenantGuard:
    """构造复用替身租户源的守卫。

    Args:
        source: 租户源替身。

    Returns:
        SourceTenantGuard: 守卫实例。
    """
    return SourceTenantGuard(source_provider=lambda: cast("object", source))  # pyright: ignore[reportArgumentType]


def test_readonly_route_allowed_three_conditions() -> None:
    """三条件同时成立才放行：方法、白名单前缀、服务键。"""
    assert readonly_route_allowed(service_key="msg", method="GET", path="/api/v1/msg/admin/topics", routes=_ROUTES)
    assert readonly_route_allowed(service_key="msg", method="head", path="/api/v1/msg/admin/topics", routes=_ROUTES)
    # 写方法永不进只读通道（即便路径与白名单一致）
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert not readonly_route_allowed(
            service_key="msg", method=method, path="/api/v1/msg/admin/topics", routes=_ROUTES
        )
    # 前缀不匹配
    assert not readonly_route_allowed(service_key="msg", method="GET", path="/api/v1/msg/data/topics", routes=_ROUTES)
    # 服务键不匹配（白名单按服务归属隔离，别的服务的路径不因前缀相似被放行）
    assert not readonly_route_allowed(service_key="mdm", method="GET", path="/api/v1/msg/admin/topics", routes=_ROUTES)


def test_readonly_route_allowed_fail_closed() -> None:
    """缺省空 / 脏条目一律不放行（配置写错只影响「读不到」，不会把写通道打开）。"""
    assert not readonly_route_allowed(
        service_key="msg", method="GET", path="/api/v1/msg/admin/", routes=ConcurrentStableList()
    )
    assert not readonly_route_allowed(
        service_key="msg", method="GET", path="/api/v1/msg/admin/", routes=ConcurrentStableList(("/api/v1/msg/admin/",))
    )
    assert not readonly_route_allowed(
        service_key="msg", method="GET", path="/api/v1/msg/admin/", routes=ConcurrentStableList(("msg:",))
    )
    assert not readonly_route_allowed(
        service_key=None, method="GET", path="/api/v1/msg/admin/", routes=ConcurrentStableList(("/api/v1/msg/admin/",))
    )


@pytest.mark.asyncio
async def test_require_readonly_returns_suspended_context() -> None:
    """只读通道：停用 / 注销不拒，返回带真实状态的上下文；缺省仍按 80002 拒。"""
    source = _SuspendedSource()
    guard = _guard(source)

    context = await guard.require(TenantTarget(code="acme"), readonly=True)
    assert context.status == "deleted" and context.code == "acme"

    with pytest.raises(TenantSuspendedError):
        await guard.require(TenantTarget(code="acme"))
    assert len(source.readonly_calls) == 2
    assert source.readonly_calls[0] is True and source.readonly_calls[1] is False


@pytest.mark.asyncio
async def test_per_round_and_batch_forward_readonly() -> None:
    """`per_round` 与 `batch` 与 `require` 同口径透传（三入口一套判定）。"""
    source = _SuspendedSource()
    guard = _guard(source)

    assert (await guard.per_round(TenantTarget(code="acme"), readonly=True)).status == "deleted"
    async with guard.batch(TenantTarget(code="acme"), readonly=True) as context:
        assert context.status == "deleted"
    assert len(source.readonly_calls) == 2
    assert all(source.readonly_calls[i] is True for i in (0, 1))


def test_require_sync_readonly() -> None:
    """同步入口同口径（作业 / 任务形态的只读取数）。"""
    source = _SuspendedSource()
    guard = _guard(source)

    assert guard.require_sync(TenantTarget(code="acme"), readonly=True).status == "deleted"
    with pytest.raises(TenantSuspendedError):
        guard.require_sync(TenantTarget(code="acme"))
