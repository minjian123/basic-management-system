"""资源级 ACL 接入约束（07D 需求 02-5）：判定顺序、拒绝码与单点可替换。

覆盖详细设计 §6.5 用例 1~11（HTTP 依赖层，替换 RBAC / ACL / 作用域解析三个出口）：
- 顺序不可绕过：RBAC 拒绝时 ACL 零调用；
- ACL 拒绝（82013）与「不泄露存在性」（同码同文案）；
- ACL 放行但跨租户 / 跨模块 → 由作用域归属拒绝；
- 未声明 ACL → `check` 零调用；空实现 → `ConfigError`（不放行）；
- 形态非法 → `ParamError` 且 ACL 零调用；单点可替换。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from starlette.requests import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import (
    reset_current_tenant_id,
    reset_tenant_context,
    set_current_tenant_id,
    set_tenant_context,
)
from bms_core.core.exceptions import (
    BizError,
    ConfigError,
    ParamError,
    PermissionError,
    ResourceAccessDeniedError,
    ScopeResourceOutOfBoundsError,
)
from bms_core.db.tenant import TenantContext
from bms_core.extension import RESOURCE_ACL_KEY, ExtensionRequirement
from bms_core.resource_scope import acl as acl_module
from bms_core.resource_scope.acl import AclContext, BaseResourceAcl, require_resource_access
from bms_core.resource_scope.base import ResourceScopeKey
from bms_core.resource_scope.null import NullResourceAcl
from bms_core.resource_scope.resolver import ResolvedScope

_TENANT_ID = 1000000000000000001
_CALLS: ConcurrentStableList[str] = ConcurrentStableList()


pytestmark = pytest.mark.kiwi_id(2450)


class _RecordingAcl(BaseResourceAcl):
    """记录调用并按需拒绝的 ACL 桩。"""

    plugin_name: str = "acl_stub"

    def __init__(self, *, deny: bool = False) -> None:
        """初始化。

        Args:
            deny: 是否拒绝。
        """
        self._deny = deny

    def check(self, ctx: AclContext, *, action: str) -> None:
        """记录调用（必要时拒绝）。

        Args:
            ctx: 判定入参。
            action: 动作名。

        Raises:
            ResourceAccessDeniedError: 预置拒绝。
        """
        _CALLS.add(f"acl:{action}:{ctx.resource_key}")
        if self._deny:
            raise ResourceAccessDeniedError()


def _request(
    *,
    state: dict[str, Any] | None = None,  # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
    path_params: dict[str, str] | None = None,  # bare-collections:allow（同上）
) -> Request:
    """构造最小请求（带可选应用状态与路径参数）。

    Args:
        state: 应用 state（`extension_requirements` 等）。
        path_params: 路径参数。

    Returns:
        Request: Starlette 请求。
    """
    app = type("App", (), {"state": type("State", (), state or {})()})()
    scope: dict[str, Any] = {  # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
        "type": "http",
        "method": "POST",
        "path": "/api/v1/demo",
        "headers": [],
        "query_string": b"",
        "app": app,
    }
    if path_params:
        scope["path_params"] = path_params
    return Request(cast("Any", scope))


def _scope() -> ResolvedScope:
    """构造已通过判定作用域。

    Returns:
        ResolvedScope: 演示作用域。
    """
    return ResolvedScope(
        tenant=TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=_TENANT_ID),
        key=ResourceScopeKey(tenant_id=_TENANT_ID, module_key="demo", resource_key="orders"),
    )


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    acl: BaseResourceAcl,
    rbac_error: Exception | None = None,
    resolver_error: Exception | None = None,
) -> None:
    """替换 RBAC / ACL / 作用域解析三个出口。

    Args:
        monkeypatch: pytest 补丁器。
        acl: ACL 实现。
        rbac_error: RBAC 固定抛出的异常。
        resolver_error: 作用域解析固定抛出的异常。
    """

    def _rbac(code: str) -> Callable[[Request], Awaitable[None]]:
        """构造 RBAC 依赖桩。

        Args:
            code: 权限码。

        Returns:
            Callable[[Request], Awaitable[None]]: 依赖函数。
        """

        async def _dependency(request: Request) -> None:
            """记录并按需拒绝。

            Args:
                request: 请求对象。

            Raises:
                Exception: 预置异常。
            """
            del request
            _CALLS.add(f"rbac:{code}")
            if rbac_error is not None:
                raise rbac_error

        return _dependency

    class _Resolver:
        """作用域解析桩。"""

        async def require(self, **kwargs: object) -> ResolvedScope:
            """记录并按需拒绝。

            Args:
                **kwargs: 解析参数。

            Returns:
                ResolvedScope: 演示作用域。

            Raises:
                Exception: 预置异常。
            """
            _CALLS.add("scope")
            if resolver_error is not None:
                raise resolver_error
            return _scope()

    def _provide_acl(request: Request) -> BaseResourceAcl:
        """返回固定 ACL 实现。

        Args:
            request: 请求对象（忽略）。

        Returns:
            BaseResourceAcl: ACL 实现。
        """
        del request
        return acl

    def _provide_resolver(request: Request) -> _Resolver:
        """返回固定解析器桩。

        Args:
            request: 请求对象（忽略）。

        Returns:
            _Resolver: 解析器桩。
        """
        del request
        return _Resolver()

    monkeypatch.setattr(acl_module, "require_permission", _rbac)
    monkeypatch.setattr(acl_module, "get_resource_acl", _provide_acl)
    monkeypatch.setattr(acl_module, "get_scope_resolver", _provide_resolver)


@pytest.fixture(autouse=True)
def _reset_context() -> Iterator[None]:
    """设置请求租户上下文（资源级判定要求租户主键）。

    Yields:
        None: 用例运行期。
    """
    token = set_tenant_context(TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=_TENANT_ID))
    id_token = set_current_tenant_id(str(_TENANT_ID))
    _CALLS.clear()
    yield
    reset_current_tenant_id(id_token)
    reset_tenant_context(token)
    _CALLS.clear()


def _declared() -> dict[str, Any]:  # bare-collections:allow（应用 state 为原生 dict）
    """构造「已声明 resource_acl」的应用状态。

    Returns:
        dict[str, Any]: 应用 state。
    """
    return {
        "extension_requirements": ConcurrentStableList(
            (ExtensionRequirement(plugin_key=RESOURCE_ACL_KEY, plugin_name="demo"),)
        )
    }


async def test_rbac_rejection_skips_acl(monkeypatch: pytest.MonkeyPatch) -> None:
    """顺序不可绕过：RBAC 拒绝时 ACL 零调用。"""
    _patch(monkeypatch, acl=_RecordingAcl(), rbac_error=PermissionError())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    with pytest.raises(PermissionError):
        await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))
    assert list(_CALLS) == ["rbac:demo:manage"]


async def test_acl_rejection_returns_82013(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACL 拒绝 → 82013 / 403，且不走作用域归属。"""
    _patch(monkeypatch, acl=_RecordingAcl(deny=True))
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    with pytest.raises(ResourceAccessDeniedError) as excinfo:
        await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))
    assert excinfo.value.code == 82013
    assert excinfo.value.http_status == 403
    assert list(_CALLS) == ["rbac:demo:manage", "acl:manage:orders"]


async def test_acl_allow_cross_tenant_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACL 放行但跨租户 → 作用域归属拒绝（不因 ACL 放行）。"""
    _patch(monkeypatch, acl=_RecordingAcl(), resolver_error=ScopeResourceOutOfBoundsError())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    with pytest.raises(ScopeResourceOutOfBoundsError):
        await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))
    assert list(_CALLS) == ["rbac:demo:manage", "acl:manage:orders", "scope"]


async def test_undeclared_acl_skips_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """未声明 `resource_acl` → 依赖可用且 `check` 零调用（不是「放行」，是无该扩展点）。"""
    _patch(monkeypatch, acl=_RecordingAcl())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    state = {"extension_requirements": ConcurrentStableList()}
    scope = await dependency(_request(state=state, path_params={"resource_key": "orders"}))
    assert scope.key.resource_key == "orders"
    assert list(_CALLS) == ["rbac:demo:manage", "scope"]


async def test_null_acl_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """空实现（占位）调用即 `ConfigError`（不放行）。"""
    _patch(monkeypatch, acl=NullResourceAcl())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    with pytest.raises(ConfigError):
        await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))


async def test_invalid_shape_skips_acl(monkeypatch: pytest.MonkeyPatch) -> None:
    """形态非法 → `ParamError` 且 ACL 零调用（第 2 步先于 ACL）。"""
    _patch(monkeypatch, acl=_RecordingAcl())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    with pytest.raises(ParamError):
        await dependency(_request(state=_declared(), path_params={"resource_key": "Orders/1"}))
    assert list(_CALLS) == ["rbac:demo:manage"]


async def test_missing_resource_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺参 → `ParamError`（10001）。"""
    _patch(monkeypatch, acl=_RecordingAcl())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    with pytest.raises(ParamError):
        await dependency(_request(state=_declared()))


async def test_action_defaults_to_permission_verb(monkeypatch: pytest.MonkeyPatch) -> None:
    """未显式给动作时取权限码动词。"""
    _patch(monkeypatch, acl=_RecordingAcl())
    dependency = require_resource_access("demo:consume", module_key="demo")
    await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))
    assert "acl:consume:orders" in list(_CALLS)


async def test_acl_implementation_is_swappable(monkeypatch: pytest.MonkeyPatch) -> None:
    """单点可替换：换实现即换行为，业务代码零改动（只依赖端口）。"""

    class _AllowAll(BaseResourceAcl):
        plugin_name: str = "allow_all"

        def check(self, ctx: AclContext, *, action: str) -> None:
            _CALLS.add("allow_all")

    _patch(monkeypatch, acl=_AllowAll())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))
    assert "allow_all" in list(_CALLS)


async def test_acl_context_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACL 入参含租户 / 模块 / 资源 / 动作（角色本期恒空）。"""
    captured: ConcurrentStableList[AclContext] = ConcurrentStableList()

    class _Capture(BaseResourceAcl):
        plugin_name: str = "capture"

        def check(self, ctx: AclContext, *, action: str) -> None:
            captured.add(ctx)

    _patch(monkeypatch, acl=_Capture())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage")
    await dependency(_request(state=_declared(), path_params={"resource_key": "orders"}))
    ctx = captured[0]
    assert ctx.tenant_id == _TENANT_ID
    assert ctx.module_key == "demo"
    assert ctx.resource_key == "orders"
    assert list(ctx.roles) == []


def test_denied_error_message_does_not_leak_existence() -> None:
    """拒绝错误文案不区分「不存在 / 无权」（同码同文案）。"""
    first = ResourceAccessDeniedError()
    second = ResourceAccessDeniedError()
    assert first.code == second.code == 82013
    assert str(first) == str(second)


def test_biz_error_is_base_class() -> None:
    """`ResourceAccessDeniedError` 属业务异常族（渲染走统一单点）。"""
    assert isinstance(ResourceAccessDeniedError(), BizError)


def test_get_resource_acl_resolves_null_impl() -> None:
    """按配置解析实现：缺省 `null` → `NullResourceAcl`（覆盖提供者）。"""
    settings = SimpleNamespace(resource_acl=SimpleNamespace(provider="null"))
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
    scope: Any = {"type": "http", "method": "GET", "path": "/", "headers": [], "app": app}
    resolved = acl_module.get_resource_acl(Request(scope))
    assert isinstance(resolved, NullResourceAcl)


def test_missing_tenant_context_rejected() -> None:
    """无租户上下文 → `ParamError`（资源级判定必须有租户）。"""
    token = set_current_tenant_id(None)
    try:
        with pytest.raises(ParamError, match="缺少租户上下文"):
            acl_module._tenant_id_required()  # pyright: ignore[reportPrivateUsage]
    finally:
        reset_current_tenant_id(token)


def test_invalid_tenant_context_rejected() -> None:
    """租户主键非数字 → `ParamError`。"""
    token = set_current_tenant_id("not-a-number")
    try:
        with pytest.raises(ParamError, match="租户上下文主键非法"):
            acl_module._tenant_id_required()  # pyright: ignore[reportPrivateUsage]
    finally:
        reset_current_tenant_id(token)


async def test_owner_flag_reads_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """`owner=True` 时读取查询参数（覆盖取参与透传分支）。"""
    _patch(monkeypatch, acl=_RecordingAcl())
    dependency = require_resource_access("demo:manage", module_key="demo", action="manage", owner=True)
    request = _request(state=_declared(), path_params={"resource_key": "orders"})
    await dependency(request)
    assert "scope" in list(_CALLS)
