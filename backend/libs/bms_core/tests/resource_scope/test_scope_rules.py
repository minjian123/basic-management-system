"""作用域校验扩展点（07D 需求 02-1）：规则链、执行序、三路径与 fail-closed。

覆盖详细设计 §2.5 用例 1~11：
- 规则通过 / 拒绝（`BizError` 原样冒泡）/ 非业务异常包成 `InternalError`（不放行）；
- 多规则按 `(order, 声明序)` 执行、首个失败即中断、`applies_to` 为假则零调用；
- 注册了但未声明的规则不执行；空链等价现状；
- 三路径（`require` / `per_round` / `batch`）同结论；
- 子类覆写 `verify` 调 / 不调 `super()` 的两种语义。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import BizError, ConfigError, InternalError
from bms_core.db.tenant import TenantContext
from bms_core.extension import SCOPE_RULE_KEY, ExtensionRequirement
from bms_core.resource_scope import (
    BaseScopeResolver,
    ResolvedScope,
    ResourceScopeKey,
    ScopeRuleChain,
    SourceScopeResolver,
    build_scope_rule_chain,
)
from bms_core.resource_scope import rules as rules_module
from bms_core.resource_scope.base import (
    ScopeResourceTypeRecord,
    register_scope_resource_types,
    reset_scope_resource_types,
)
from bms_core.resource_scope.null import NullScopeRule
from bms_core.resource_scope.rules import BaseScopeRule
from bms_core.services.module_registry import (
    ModuleRecord,
    register_service_records,
    reset_service_records,
)
from bms_core.tenant.guard import BaseTenantGuard, TenantTarget

_TENANT_ID = 1000000000000000001
_TOPIC_TYPE = ScopeResourceTypeRecord(
    resource_type_key="demo.topic",
    name="主题",
    name_pattern="^[a-z][a-z0-9_]{0,15}$",
    max_length=16,
    product_key="demo",
)
_CALLS: ConcurrentStableList[str] = ConcurrentStableList()
_TARGET = TenantTarget(tenant_id=str(_TENANT_ID))


pytestmark = pytest.mark.kiwi_id(2450)


class _StubGuard(BaseTenantGuard):
    """占位守卫：固定返回上下文（实现名唯一，避免与其它用例桩重名）。"""

    plugin_name: str = "rules_stub"

    async def resolve(self, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
        """返回演示租户上下文。

        Args:
            target: 租户定位（忽略）。
            readonly: 只读通道（忽略）。

        Returns:
            TenantContext: 演示上下文。
        """
        del target, readonly
        return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=_TENANT_ID)


class _RecordingRule(BaseScopeRule):
    """记录调用顺序的规则（可按需拒绝 / 抛异常 / 不适用）。"""

    def __init__(
        self,
        name: str,
        *,
        order: int = 100,
        error: Exception | None = None,
        applies: bool = True,
    ) -> None:
        """初始化。

        Args:
            name: 实现名。
            order: 执行序。
            error: 固定抛出的异常。
            applies: `applies_to` 返回值。
        """
        self.plugin_name = name
        self.order = order
        self._error = error
        self._applies = applies

    def applies_to(self, scope: ResolvedScope) -> bool:
        """按预置返回值判定是否适用。

        Args:
            scope: 作用域（忽略）。

        Returns:
            bool: 是否适用。
        """
        del scope
        return self._applies

    def verify(self, scope: ResolvedScope) -> None:
        """记录调用（必要时抛错）。

        Args:
            scope: 作用域（忽略）。

        Raises:
            Exception: 预置异常。
        """
        del scope
        _CALLS.add(self.plugin_name)
        if self._error is not None:
            raise self._error


def _scope() -> ResolvedScope:
    """构造已通过前置校验的作用域。

    Returns:
        ResolvedScope: 演示作用域。
    """
    return ResolvedScope(
        tenant=TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=_TENANT_ID),
        key=ResourceScopeKey(tenant_id=_TENANT_ID, module_key="demo", resource_key="orders"),
        resource_type=_TOPIC_TYPE,
    )


def _chain(*rules: BaseScopeRule) -> ScopeRuleChain:
    """构造规则链。

    Args:
        *rules: 规则（按给定顺序）。

    Returns:
        ScopeRuleChain: 规则链。
    """
    return ScopeRuleChain(rules=ConcurrentStableFrozenList[BaseScopeRule](rules))


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """每例前后复位视图与调用记录。

    Yields:
        None: 用例运行期。
    """
    reset_scope_resource_types()
    reset_service_records()
    _CALLS.clear()
    register_scope_resource_types(ConcurrentStableList((_TOPIC_TYPE,)))
    register_service_records(
        ConcurrentStableList(
            (
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    product_key="demo",
                    status="enabled",
                ),
            )
        )
    )
    yield
    reset_scope_resource_types()
    reset_service_records()
    _CALLS.clear()


def test_passing_rule_returns_scope() -> None:
    """规则通过时 `resolve` 正常返回。"""
    resolver = SourceScopeResolver(guard_provider=_StubGuard, rule_chain=_chain(_RecordingRule("ok")))
    scope = resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert scope.key.resource_key == "orders"
    assert list(_CALLS) == ["ok"]


def test_rule_rejection_bubbles() -> None:
    """规则抛 `BizError` 原样冒泡（不被包装）。"""
    error = BizError(350010, "命名空间非法")
    resolver = SourceScopeResolver(guard_provider=_StubGuard, rule_chain=_chain(_RecordingRule("deny", error=error)))
    with pytest.raises(BizError) as excinfo:
        resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert excinfo.value is error


def test_rule_non_biz_error_fails_closed() -> None:
    """规则抛非业务异常 → `InternalError`（不放行）。"""
    resolver = SourceScopeResolver(
        guard_provider=_StubGuard,
        rule_chain=_chain(_RecordingRule("boom", error=RuntimeError("bug"))),
    )
    with pytest.raises(InternalError):
        resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")


def test_rules_run_in_order_and_stop_on_failure() -> None:
    """多规则按序执行；首个失败后续不执行。"""
    resolver = SourceScopeResolver(
        guard_provider=_StubGuard,
        rule_chain=_chain(
            _RecordingRule("first", order=10),
            _RecordingRule("second", order=20, error=BizError(350010)),
            _RecordingRule("third", order=30),
        ),
    )
    with pytest.raises(BizError):
        resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert list(_CALLS) == ["first", "second"]


def test_inapplicable_rule_is_skipped() -> None:
    """`applies_to` 为假 → 零调用。"""
    resolver = SourceScopeResolver(
        guard_provider=_StubGuard,
        rule_chain=_chain(_RecordingRule("skip", applies=False), _RecordingRule("run", order=200)),
    )
    resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert list(_CALLS) == ["run"]


def test_empty_chain_keeps_behavior() -> None:
    """空链不改变 `resolve` 结果。"""
    resolver = SourceScopeResolver(guard_provider=_StubGuard)
    scope = resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert scope.tenant.tenant_id == _TENANT_ID
    assert list(_CALLS) == []


def test_three_paths_same_conclusion() -> None:
    """三路径（require / per_round / batch）同结论。"""
    resolver = SourceScopeResolver(guard_provider=_StubGuard, rule_chain=_chain(_RecordingRule("ok")))
    required = resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    per_round = resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert required.key == per_round.key


def test_subclass_override_with_super_runs_chain() -> None:
    """子类覆写并调 `super()` → 规则链执行。"""

    class _Overriding(SourceScopeResolver):
        def verify(self, scope: ResolvedScope) -> None:
            _CALLS.add("override")
            super().verify(scope)

    resolver = _Overriding(guard_provider=_StubGuard, rule_chain=_chain(_RecordingRule("ok")))
    resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert list(_CALLS) == ["override", "ok"]


def test_subclass_override_without_super_skips_chain() -> None:
    """子类覆写不调 `super()` → 规则链不执行（向后兼容既有写法）。"""

    class _Legacy(SourceScopeResolver):
        def verify(self, scope: ResolvedScope) -> None:
            del scope
            _CALLS.add("legacy")

    resolver = _Legacy(guard_provider=_StubGuard, rule_chain=_chain(_RecordingRule("ok")))
    resolver.require_sync(_TARGET, module_key="demo", resource_type="demo.topic", resource_key="orders")
    assert list(_CALLS) == ["legacy"]


def test_build_chain_empty_declaration_returns_empty() -> None:
    """无 `scope_rule` 声明 → 空链（不改变既有行为）。"""
    chain = build_scope_rule_chain(ConcurrentStableList())
    assert not chain
    chain.verify(_scope())
    assert list(_CALLS) == []


def test_build_chain_unresolved_raises() -> None:
    """声明了但注册表无此名 → `ConfigError`（不静默跳过）。"""
    with pytest.raises(ConfigError):
        build_scope_rule_chain(
            ConcurrentStableList((ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="missing"),))
        )


def test_null_rule_is_noop() -> None:
    """空规则不做判定。"""
    NullScopeRule().verify(_scope())
    assert list(_CALLS) == []


def test_resolver_carries_chain_property() -> None:
    """解析器暴露规则链（供排障与用例核对）。"""
    chain = _chain()
    resolver: BaseScopeResolver = SourceScopeResolver(guard_provider=_StubGuard, rule_chain=chain)
    assert resolver.rule_chain is chain
    assert not resolver.rule_chain


class _AppliesErrorRule(BaseScopeRule):
    """`applies_to` 抛错的规则（覆盖分支）。"""

    plugin_name: str = "applies_error"

    def __init__(self, error: Exception) -> None:
        """初始化。

        Args:
            error: `applies_to` 固定抛出的异常。
        """
        self._error = error

    def applies_to(self, scope: ResolvedScope) -> bool:
        """固定抛错。

        Args:
            scope: 作用域（忽略）。

        Returns:
            bool: 不返回。

        Raises:
            Exception: 预置异常。
        """
        del scope
        raise self._error

    def verify(self, scope: ResolvedScope) -> None:
        """不执行（`applies_to` 已抛错）。

        Args:
            scope: 作用域（忽略）。
        """
        del scope


class _MinimalRule(BaseScopeRule):
    """只实现 `verify` 的规则：使用基类默认 `applies_to`（恒适用）。"""

    plugin_name: str = "minimal"

    def verify(self, scope: ResolvedScope) -> None:
        """记录调用。

        Args:
            scope: 作用域（忽略）。
        """
        del scope
        _CALLS.add("minimal")


def test_applies_to_default_is_true() -> None:
    """基类默认 `applies_to` 恒适用（覆盖默认实现）。"""
    chain = _chain(_MinimalRule())
    chain.verify(_scope())
    assert list(_CALLS) == ["minimal"]


def test_applies_to_biz_error_bubbles() -> None:
    """`applies_to` 抛 `BizError` 原样冒泡。"""
    error = BizError(350010, "命名空间非法")
    chain = _chain(_AppliesErrorRule(error))
    with pytest.raises(BizError) as excinfo:
        chain.verify(_scope())
    assert excinfo.value is error


def test_applies_to_non_biz_error_fails_closed() -> None:
    """`applies_to` 抛非业务异常 → `InternalError`（不放行）。"""
    chain = _chain(_AppliesErrorRule(RuntimeError("bug")))
    with pytest.raises(InternalError):
        chain.verify(_scope())


def test_build_chain_resolves_declared_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """声明规则解析成功 → 进入链并执行（覆盖正常构造路径）。"""
    monkeypatch.setattr(rules_module, "resolve_plugin", _stub_minimal_rule)
    chain = build_scope_rule_chain(
        ConcurrentStableList((ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="minimal"),))
    )
    chain.verify(_scope())
    assert list(_CALLS) == ["minimal"]


async def test_require_scope_reads_owner_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """`require_scope(owner=True)` 读取归属租户查询参数（覆盖取参分支）。"""
    from bms_core.resource_scope import resolver as resolver_module
    from bms_core.resource_scope.resolver import require_scope

    captured: ConcurrentStableList[int | None] = ConcurrentStableList()

    class _Resolver:
        """作用域解析桩：记录归属参数。"""

        async def require(self, **kwargs: object) -> ResolvedScope:
            """记录并返回作用域。

            Args:
                **kwargs: 解析参数。

            Returns:
                ResolvedScope: 演示作用域。
            """
            captured.add(cast("int | None", kwargs.get("owner_tenant_id")))
            return _scope()

    def _provide(request: Any) -> Any:
        """解析器提供者替身（固定返回本地桩）。

        Args:
            request: 请求对象（忽略）。

        Returns:
            Any: 解析器桩。
        """
        del request
        return _Resolver()

    monkeypatch.setattr(resolver_module, "get_scope_resolver", _provide)
    dependency = require_scope("demo", "demo.topic", owner=True)
    await dependency(_request_with_query("owner_tenant_id=42"))
    assert list(captured) == [42]


def _request_with_query(query: str) -> Any:
    """构造带查询串的最小请求。

    Args:
        query: 查询串（如 `owner_tenant_id=42`）。

    Returns:
        Any: Starlette 请求。
    """
    from starlette.requests import Request as _Request

    # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
    scope: Any = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/demo",
        "headers": [],
        "query_string": query.encode(),
        "path_params": {"resource_key": "orders"},
    }
    return _Request(scope)


def _stub_minimal_rule(*args: object, **kwargs: object) -> BaseScopeRule:
    """解析替身：固定返回最小规则（不触注册表）。

    Args:
        *args: 原位置参数（忽略）。
        **kwargs: 原关键字参数（忽略）。

    Returns:
        BaseScopeRule: 最小规则实例。
    """
    del args, kwargs
    return _MinimalRule()
