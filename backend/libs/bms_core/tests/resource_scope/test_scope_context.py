"""作用域上下文与三处注入（07D 需求 01-3）：纯逻辑用例。

覆盖详细设计 §3.5 用例 1~10：
- 上下文四件套（set / get / reset）与无上下文取用（fail-closed）；
- `scope_context()` 同步管理器的进出复位（含异常路径）；
- 三处注入：HTTP 依赖、`per_round`、`batch`（进出复位）、`frame`（进出复位、嵌套 LIFO）；
- 产品扩展位：只读映射、`with_extensions` 不可变、不参与相等。
"""

from collections.abc import Callable, Iterator
from types import MappingProxyType
from typing import Any, cast

import pytest
from starlette.requests import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import (
    get_scope_context,
    require_scope_context,
    reset_scope_context,
    reset_tenant_context,
    scope_context,
    set_scope_context,
    set_tenant_context,
)
from bms_core.core.exceptions import ConfigError
from bms_core.db.tenant import TenantContext
from bms_core.resource_scope import (
    ResolvedScope,
    SourceScopeResolver,
    require_scope,
)
from bms_core.resource_scope import resolver as resolver_module
from bms_core.resource_scope.base import (
    ResourceScopeKey,
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


def _context(tenant_id: int = _TENANT_ID) -> TenantContext:
    """演示租户上下文（含雪花主键）。

    Args:
        tenant_id: 租户主键。

    Returns:
        TenantContext: 租户上下文。
    """
    return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=tenant_id)


class _StubGuard(BaseTenantGuard):
    """占位守卫：固定返回上下文（不取数）。"""

    plugin_name: str = "stub_context"

    async def resolve(self, target: TenantTarget) -> TenantContext:
        """返回预置上下文。

        Args:
            target: 租户定位（占位忽略）。

        Returns:
            TenantContext: 预置上下文。
        """
        del target
        return _context()


def _resolver() -> SourceScopeResolver:
    """构造默认实现（守卫为占位）。

    Returns:
        SourceScopeResolver: 解析器。
    """
    guard = _StubGuard()
    return SourceScopeResolver(guard_provider=lambda: guard)


def _scope(resource_key: str = "news") -> ResolvedScope:
    """直接构造作用域（供扩展位用例，不经解析）。

    Args:
        resource_key: 资源标识。

    Returns:
        ResolvedScope: 作用域。
    """
    key = ResourceScopeKey(tenant_id=_TENANT_ID, module_key="demo", resource_key=resource_key)
    return ResolvedScope(tenant=_context(), key=key)


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


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """每例前后复位上下文与登记态，并装载最小登记集。

    Yields:
        None: 用例运行期。
    """
    token = set_scope_context(None)
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
        reset_scope_context(token)
        reset_scope_resource_types()
        reset_service_records()


def test_context_set_get_reset() -> None:
    """上下文四件套：写入后可读同一对象，复位后为空。"""
    scope = _scope()
    token = set_scope_context(scope)

    assert get_scope_context() is scope

    reset_scope_context(token)
    assert get_scope_context() is None


def test_require_scope_context_fails_closed() -> None:
    """无上下文取用：直接 `ConfigError`（不回落、不放行）。"""
    with pytest.raises(ConfigError):
        require_scope_context()


def test_require_scope_context_returns_current() -> None:
    """有上下文时取用：返回当前作用域（不复制、不包装）。"""
    scope = _scope()
    token = set_scope_context(scope)

    try:
        assert require_scope_context() is scope
    finally:
        reset_scope_context(token)


def test_scope_context_manager_restores_on_exit() -> None:
    """同步管理器：块内可读、块外为空。"""
    scope = _scope()

    with scope_context(scope) as current:
        assert current is scope
        assert get_scope_context() is scope

    assert get_scope_context() is None


def test_scope_context_manager_restores_on_error() -> None:
    """同步管理器：块内抛错同样复位。"""
    scope = _scope()

    with pytest.raises(RuntimeError), scope_context(scope):
        raise RuntimeError("boom")

    assert get_scope_context() is None


async def test_require_scope_dependency_writes_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """管理面注入：依赖返回后上下文即该作用域。"""
    resolver = _resolver()
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(resolver))
    dependency = require_scope("demo", "demo.topic")
    token = set_tenant_context(_context())

    try:
        scope = await dependency(_request(path_params={"resource_key": "news"}))
    finally:
        reset_tenant_context(token)

    assert get_scope_context() is scope


async def test_per_round_writes_and_overwrites() -> None:
    """异步单轮注入：每轮写入自己的作用域，后一轮覆盖前一轮。"""
    resolver = _resolver()

    first = await resolver.per_round(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news")
    assert get_scope_context() is first

    second = await resolver.per_round(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="later")
    assert get_scope_context() is second


async def test_batch_writes_and_restores() -> None:
    """批次注入：块内可读、块外为空。"""
    resolver = _resolver()

    async with resolver.batch(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news") as scope:
        assert get_scope_context() is scope

    assert get_scope_context() is None


async def test_batch_restores_on_error() -> None:
    """批次注入：块内抛错同样复位。"""
    resolver = _resolver()

    with pytest.raises(RuntimeError):
        async with resolver.batch(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news") as scope:
            assert get_scope_context() is scope
            raise RuntimeError("boom")

    assert get_scope_context() is None


async def test_frame_writes_and_restores() -> None:
    """帧入口：块内可读、块外为空（逐帧不残留）。"""
    resolver = _resolver()

    async with resolver.frame(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news") as scope:
        assert get_scope_context() is scope

    assert get_scope_context() is None


async def test_frame_restores_on_error() -> None:
    """帧入口：帧内抛错同样复位（不把本帧作用域留给下一帧）。"""
    resolver = _resolver()

    with pytest.raises(RuntimeError):
        async with resolver.frame(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news") as scope:
            assert get_scope_context() is scope
            raise RuntimeError("boom")

    assert get_scope_context() is None


async def test_frame_nested_restores_lifo() -> None:
    """帧入口嵌套：内层退出恢复到外层作用域，外层退出复位为空。"""
    resolver = _resolver()

    async with resolver.frame(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="outer") as outer:
        async with resolver.frame(
            _TARGET, module_key="demo", resource_type="demo.topic", resource_key="inner"
        ) as inner:
            assert get_scope_context() is inner
        assert get_scope_context() is outer

    assert get_scope_context() is None


def test_extensions_are_frozen() -> None:
    """扩展位：构造后为只读映射，赋值即 `TypeError`。"""
    scope = _scope().with_extensions(org_id="42")

    assert scope.extensions["org_id"] == "42"
    with pytest.raises(TypeError):
        scope.extensions["org_id"] = "43"  # pyright: ignore[reportIndexIssue]


def test_extensions_accepts_readonly_mapping() -> None:
    """扩展位：已是只读映射时原样保留（不重复包装）。"""
    readonly = MappingProxyType({"org_id": "42"})
    scope = ResolvedScope(tenant=_context(), key=_scope().key, extensions=readonly)

    assert scope.extensions is readonly


def test_with_extensions_returns_new_instance() -> None:
    """`with_extensions`：返回新实例，原实例扩展位与三级标识不变。"""
    scope = _scope()
    extended = scope.with_extensions(org_id="42")

    assert extended is not scope
    assert dict(scope.extensions) == {}
    assert extended.extensions["org_id"] == "42"
    assert extended.key == scope.key


def test_extensions_excluded_from_equality() -> None:
    """扩展位不参与相等：同三级 + 不同扩展仍相等。"""
    left = _scope().with_extensions(org_id="42")
    right = _scope().with_extensions(org_id="43")

    assert left == right


def _provider(resolver: SourceScopeResolver) -> Callable[[Request], SourceScopeResolver]:
    """构造依赖注入提供者（固定返回给定解析器）。

    Args:
        resolver: 解析器实例。

    Returns:
        Callable[[Request], SourceScopeResolver]: 零副作用提供者。
    """

    def _provide(request: Request) -> SourceScopeResolver:
        """返回固定解析器。

        Args:
            request: 请求对象（未使用）。

        Returns:
            SourceScopeResolver: 解析器。
        """
        del request
        return resolver

    return _provide
