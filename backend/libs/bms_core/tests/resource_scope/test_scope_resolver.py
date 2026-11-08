"""作用域解析与校验（07D 需求 01-2）：纯逻辑用例。

覆盖详细设计 §2.5 用例 1~15、17~19：
- 三段合法解析与模块级作用域；参数自洽（`resource_key` 无类型即 `ParamError`）；
- 模块键形态 / 未登记（82009）/ 未启用（82010）；
- 类型前缀不归属、未注册、已停用（82011）；
- 资源取值不匹配 / 超长 / 归属租户不符（82012）；
- 租户不存在（80001）/ 停用（80002）/ 源不可达（10007）原样冒泡；
- 三路径（require / per_round / batch）同结论；产品规则钩子；空实现 fail-closed；
- 管理面依赖工厂取参（path / query / 缺参 / 归属参数）与取参位置校验。
"""

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import reset_tenant_context, set_tenant_context
from bms_core.core.exceptions import (
    BizError,
    ConfigError,
    ParamError,
    PluginError,
    ScopeModuleDisabledError,
    ScopeModuleNotRegisteredError,
    ScopeResourceOutOfBoundsError,
    ScopeResourceTypeNotRegisteredError,
    ServiceUnavailableError,
    TenantNotFoundError,
    TenantSuspendedError,
)
from bms_core.db.tenant import TenantContext
from bms_core.resource_scope import (
    SCOPE_RESOURCE_DISABLED,
    BaseScopeResolver,
    NullScopeResolver,
    ResolvedScope,
    SourceScopeResolver,
    SourceScopeResolverFactory,
    get_scope_resolver,
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
    ModuleStatus,
    register_service_records,
    reset_service_records,
)
from bms_core.tenant.guard import BaseTenantGuard, TenantTarget

pytestmark = pytest.mark.kiwi_id(2447)

_TENANT_ID = 1000000000000000001
_OTHER_TENANT_ID = 1000000000000000002
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
    """占位守卫：固定返回上下文或固定抛错（不取数）。"""

    plugin_name: str = "stub"

    def __init__(self, *, context: TenantContext | None = None, error: Exception | None = None) -> None:
        """初始化。

        Args:
            context: 固定返回的上下文。
            error: 固定抛出的异常（优先于上下文）。
        """
        self._context = context or _context()
        self._error = error

    async def resolve(self, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
        """按预置结果返回或抛错。

        Args:
            target: 租户定位（占位忽略）。
            readonly: 只读通道（占位忽略）。

        Returns:
            TenantContext: 预置上下文。

        Raises:
            Exception: 预置异常。
        """
        del target, readonly
        if self._error is not None:
            raise self._error
        return self._context


def _resolver(*, context: TenantContext | None = None, error: Exception | None = None) -> SourceScopeResolver:
    """构造默认实现（守卫为占位）。

    Args:
        context: 守卫返回的上下文。
        error: 守卫固定抛出的异常。

    Returns:
        SourceScopeResolver: 解析器。
    """
    guard = _StubGuard(context=context, error=error)
    return SourceScopeResolver(guard_provider=lambda: guard)


def _request(
    app: object | None = None,
    *,
    path_params: dict[str, str] | None = None,  # bare-collections:allow（ASGI 路径参数为 Starlette 原生 dict）
    query: str = "",
) -> Request:
    """构造最小 HTTP 请求（path_params / query_string / 可选 app）。

    Args:
        app: 应用实例（依赖出口用例需要读 `app.state.settings`）。
        path_params: 路径参数。
        query: 查询串。

    Returns:
        Request: Starlette 请求对象。
    """
    scope: dict[str, Any] = {  # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
        "type": "http",
        "method": "GET",
        "path": "/api/v1/demo",
        "headers": [],
        "query_string": query.encode(),
    }
    if app is not None:
        scope["app"] = app
    if path_params:
        scope["path_params"] = path_params
    return Request(cast("Any", scope))


def _provider(resolver: BaseScopeResolver) -> Callable[[Request], BaseScopeResolver]:
    """构造依赖注入提供者（固定返回给定解析器，供依赖工厂用例替换装配入口）。

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


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """每例前后复位作用域视图与服务目录注入，并装载本用例的最小登记集。

    Yields:
        None: 用例运行期。
    """
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
                ),
                ModuleRecord(
                    module_key="demox",
                    name="演示停用服务",
                    table_prefix="demox_",
                    event_domain="demox",
                    service_group="product",
                    product_key="demo",
                    status=ModuleStatus.DISABLED,
                ),
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
                ),
                ScopeResourceTypeRecord(
                    resource_type_key="demo.offtopic",
                    name="停用主题",
                    status=SCOPE_RESOURCE_DISABLED,
                    product_key="demo",
                ),
            ]
        )
    )
    yield
    reset_service_records()
    reset_scope_resource_types()


async def test_resolve_returns_three_level_scope() -> None:
    """三段合法解析：返回 ResolvedScope，三级标识与命中记录正确。"""
    scope = await _resolver().resolve(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news")

    assert scope.tenant_id == _TENANT_ID
    assert scope.module_key == "demo"
    assert scope.resource_key == "news"
    assert scope.resource_type is not None
    assert scope.resource_type.resource_type_key == "demo.topic"
    assert scope.effective_status == "enabled"
    assert scope.as_text() == f"{_TENANT_ID}/demo/news"


async def test_resolve_module_scope_without_resource() -> None:
    """模块级作用域：resource_key 为 None 时类型记录为空，有效状态恒启用。"""
    scope = await _resolver().resolve(_TARGET, module_key="demo")

    assert scope.resource_key is None
    assert scope.resource_type is None
    assert scope.effective_status == "enabled"


async def test_resource_key_without_type_is_param_error() -> None:
    """参数自洽：给 resource_key 却不给 resource_type 即 ParamError（不猜类型）。"""
    with pytest.raises(ParamError):
        await _resolver().resolve(_TARGET, module_key="demo", resource_key="news")


async def test_invalid_module_key_shape() -> None:
    """模块键形态非法：ParamError。"""
    with pytest.raises(ParamError):
        await _resolver().resolve(_TARGET, module_key="Demo")


async def test_module_not_registered() -> None:
    """模块键未登记：82009。"""
    with pytest.raises(ScopeModuleNotRegisteredError) as excinfo:
        await _resolver().resolve(_TARGET, module_key="nosuch")

    assert excinfo.value.code == 82009


async def test_module_registered_but_disabled() -> None:
    """模块键已登记未启用：82010。"""
    with pytest.raises(ScopeModuleDisabledError) as excinfo:
        await _resolver().resolve(_TARGET, module_key="demox")

    assert excinfo.value.code == 82010


async def test_resource_type_cross_module_is_rejected() -> None:
    """类型标识前缀不等于模块键：82011（跨 module_key 越权）。"""
    with pytest.raises(ScopeResourceTypeNotRegisteredError) as excinfo:
        await _resolver().resolve(_TARGET, module_key="demo", resource_type="other.topic", resource_key="news")

    assert excinfo.value.code == 82011


async def test_resource_type_not_registered() -> None:
    """类型未注册：82011。"""
    with pytest.raises(ScopeResourceTypeNotRegisteredError) as excinfo:
        await _resolver().resolve(_TARGET, module_key="demo", resource_type="demo.unknown", resource_key="news")

    assert excinfo.value.code == 82011


async def test_resource_type_inactive_is_rejected() -> None:
    """类型已停用：与未注册同码（82011），不泄露存在性。"""
    with pytest.raises(ScopeResourceTypeNotRegisteredError) as excinfo:
        await _resolver().resolve(_TARGET, module_key="demo", resource_type="demo.offtopic", resource_key="news")

    assert excinfo.value.code == 82011


@pytest.mark.parametrize("resource_key", ["News-1", "a" * 17])
async def test_resource_key_out_of_bounds(resource_key: str) -> None:
    """资源取值不匹配命名规则或超长：82012。"""
    with pytest.raises(ScopeResourceOutOfBoundsError) as excinfo:
        await _resolver().resolve(_TARGET, module_key="demo", resource_type="demo.topic", resource_key=resource_key)

    assert excinfo.value.code == 82012


async def test_resource_owner_mismatch_is_rejected() -> None:
    """归属租户与当前租户不一致：82012（跨租户拒绝）。"""
    with pytest.raises(ScopeResourceOutOfBoundsError) as excinfo:
        await _resolver().resolve(
            _TARGET,
            module_key="demo",
            resource_type="demo.topic",
            resource_key="news",
            owner_tenant_id=_OTHER_TENANT_ID,
        )

    assert excinfo.value.code == 82012


async def test_resource_owner_match_passes() -> None:
    """归属租户一致：正常通过。"""
    scope = await _resolver().resolve(
        _TARGET,
        module_key="demo",
        resource_type="demo.topic",
        resource_key="news",
        owner_tenant_id=_TENANT_ID,
    )

    assert scope.resource_key == "news"


@pytest.mark.parametrize("error", [TenantNotFoundError("未知租户"), TenantSuspendedError("租户已停用")])
async def test_tenant_failures_propagate(error: BizError) -> None:
    """租户不存在 / 停用：原样冒泡（80001 / 80002），不由 82 段改写。"""
    with pytest.raises(type(error)) as excinfo:
        await _resolver(error=error).resolve(_TARGET, module_key="demo")

    assert excinfo.value.code == error.code


async def test_tenant_source_unavailable_fails_closed() -> None:
    """租户源不可达：10007 / 503，不返回作用域。"""
    with pytest.raises(ServiceUnavailableError) as excinfo:
        await _resolver(error=ServiceUnavailableError("租户源不可达")).resolve(_TARGET, module_key="demo")

    assert excinfo.value.code == 10007
    assert excinfo.value.http_status == 503


async def test_three_paths_share_one_conclusion() -> None:
    """三路径同结论：require / per_round / batch 解析出同一组三级标识。"""
    resolver = _resolver()
    first = await resolver.require(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news")
    second = await resolver.per_round(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news")
    async with resolver.batch(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news") as third:
        assert third.key == first.key == second.key
        assert third.tenant_id == first.tenant_id


class _RejectingResolver(SourceScopeResolver):
    """产品规则拒绝实现（覆写 verify 钩子）。"""

    plugin_name: str = "rejecting"

    def verify(self, scope: ResolvedScope) -> None:
        """固定拒绝（验证钩子在四步校验之后执行且异常原样冒泡）。

        Args:
            scope: 已通过前四步校验的作用域。

        Raises:
            ScopeResourceOutOfBoundsError: 恒定。
        """
        del scope
        raise ScopeResourceOutOfBoundsError("产品规则拒绝")


async def test_product_rule_hook_rejects() -> None:
    """产品规则钩子：异常原样冒泡，且执行时机在四步校验之后。"""
    guard = _StubGuard()
    resolver = _RejectingResolver(guard_provider=lambda: guard)

    with pytest.raises(ScopeResourceOutOfBoundsError):
        await resolver.resolve(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news")


async def test_null_resolver_fails_closed() -> None:
    """空实现：调用即 ConfigError（占位不放行）。"""
    with pytest.raises(ConfigError):
        await NullScopeResolver().resolve(_TARGET, module_key="demo")


def test_require_scope_rejects_unsupported_source() -> None:
    """依赖工厂：取参位置仅支持 path / query，其余在装配期即错。"""
    with pytest.raises(ConfigError):
        require_scope("demo", "demo.topic", resource_from="body")


async def test_require_scope_reads_path_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖工厂：从路径参数取资源标识并解析成功（租户取中间件注入的上下文）。"""
    resolver = _resolver()
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(resolver))
    dependency = require_scope("demo", "demo.topic")
    token = set_tenant_context(_context())

    try:
        scope = await dependency(_request(path_params={"resource_key": "news"}))
    finally:
        reset_tenant_context(token)

    assert scope.resource_key == "news"


async def test_require_scope_reads_query_param_and_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖工厂：从查询参数取资源标识与归属租户，归属一致即通过。"""
    resolver = _resolver()
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(resolver))
    dependency = require_scope("demo", "demo.topic", resource_from="query", owner=True)
    token = set_tenant_context(_context())

    try:
        scope = await dependency(_request(query=f"resource_key=news&owner_tenant_id={_TENANT_ID}"))
    finally:
        reset_tenant_context(token)

    assert scope.resource_key == "news"


@pytest.mark.parametrize("query", ["", "resource_key=news&owner_tenant_id=not-a-number"])
async def test_require_scope_rejects_missing_or_bad_params(monkeypatch: pytest.MonkeyPatch, query: str) -> None:
    """依赖工厂：资源标识缺失 / 归属租户非整数即 ParamError。"""
    resolver = _resolver()
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(resolver))
    dependency = require_scope("demo", "demo.topic", resource_from="query", owner=True)

    with pytest.raises(ParamError):
        await dependency(_request(query=query))


async def test_require_scope_owner_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖工厂：owner=True 但未传归属参数时按「不校验归属」放行。"""
    resolver = _resolver()
    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provider(resolver))
    dependency = require_scope("demo", "demo.topic", resource_from="query", owner=True)
    token = set_tenant_context(_context())

    try:
        scope = await dependency(_request(query="resource_key=news"))
    finally:
        reset_tenant_context(token)

    assert scope.resource_key == "news"


def test_require_sync_returns_scope() -> None:
    """同步入口：无运行中事件循环时正常返回作用域。"""
    scope = _resolver().require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="news")

    assert scope.resource_key == "news"


async def test_require_sync_rejects_running_loop() -> None:
    """同步入口：在运行中的事件循环内调用即 ConfigError（不降级、不放行）。"""
    with pytest.raises(ConfigError):
        _resolver().require_sync(_TARGET, module_key="demo")


async def test_tenant_context_without_primary_key_is_config_error() -> None:
    """租户上下文缺主键：无法构成三级作用域，ConfigError。"""
    context = TenantContext(code="demo", db_key="tenant_demo", name="演示租户")

    with pytest.raises(ConfigError):
        await _resolver(context=context).resolve(_TARGET, module_key="demo")


async def test_invalid_resource_type_shape() -> None:
    """资源类型标识形态非法（缺段）：ParamError。"""
    with pytest.raises(ParamError):
        await _resolver().resolve(_TARGET, module_key="demo", resource_type="demo", resource_key="news")


async def test_factory_without_settings_fails_closed() -> None:
    """工厂出口：应用未装配 settings 时解析即 ConfigError（fail-closed）。"""
    factory = SourceScopeResolverFactory(SimpleNamespace(state=SimpleNamespace()))

    with pytest.raises(ConfigError):
        await factory.create().resolve(_TARGET, module_key="demo")


def test_get_scope_resolver_resolves_null_and_unknown() -> None:
    """依赖出口：provider 为空 → 占位实现（fail-closed）；未登记实现名 → PluginError。"""
    settings = Settings()
    settings.scope_resolver.provider = ""
    app = FastAPI()
    app.state.settings = settings

    assert isinstance(get_scope_resolver(_request(app)), NullScopeResolver)

    settings.scope_resolver.provider = "unknown"
    with pytest.raises(PluginError):
        get_scope_resolver(_request(app))


async def test_factory_resolves_guard_from_settings() -> None:
    """工厂出口：装配了 settings 时按 `[tenant_guard]` 解析守卫（占位实现调用即错，仍 fail-closed）。"""
    settings = Settings()
    settings.tenant_guard.provider = ""
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))

    with pytest.raises(ConfigError):
        await SourceScopeResolverFactory(app).create().resolve(_TARGET, module_key="demo")
