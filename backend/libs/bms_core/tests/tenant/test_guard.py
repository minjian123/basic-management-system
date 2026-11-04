"""租户可用性守卫能力域测试（任务 `04_02`；Kiwi 2408）。

覆盖：`TenantTarget` 三选一与形态校验 / `from_context` / `label`；三入口（`require` / `per_round` /
`batch`）判定一致且批内不重复回源；同步入口 `require_sync` 两分支；三分支错误码与 HTTP 入口一致
（80001 / 80002 / 10007）；上下文缺省与拒绝；扩展钩子 `verify`（缺省 / 覆写 / 调用顺序）；空实现
fail-closed；装配接线与依赖出口解析。
"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, Request

from bms_core.api.deps import get_tenant_guard as exported_get_tenant_guard
from bms_core.core.assembly import PLUGIN_WIRINGS, register_platform_plugins
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import reset_tenant_context, set_tenant_context
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import (
    BizError,
    ConfigError,
    ParamError,
    PluginError,
    ServiceUnavailableError,
    TenantNotFoundError,
    TenantSuspendedError,
)
from bms_core.core.plugin import register_plugin
from bms_core.core.resources import ResourceManager
from bms_core.db.tenant import TenantContext
from bms_core.tenant.guard import (
    SOURCE_TENANT_GUARD,
    BaseTenantGuard,
    SourceTenantGuard,
    SourceTenantGuardFactory,
    TenantTarget,
    get_tenant_guard,
)
from bms_core.tenant.null import NullTenantGuard

pytestmark = pytest.mark.kiwi_id(2408)

_CONTEXT = TenantContext(code="acme", db_key="tenant_acme", name="Acme", tenant_id=7)
"""测试用租户上下文（含雪花主键）。"""


class _StubSource:
    """租户源替身：记录调用并返回固定上下文 / 固定异常。"""

    def __init__(self, *, error: BizError | None = None) -> None:
        """初始化。

        Args:
            error: 命中时抛出的异常（None 表示正常返回）。
        """
        self.error = error
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def by_code(self, code: str) -> TenantContext:
        """按编码取上下文。"""
        return self._hit(f"code:{code}")

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取上下文。"""
        return self._hit(f"domain:{domain}")

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按主键取上下文。"""
        return self._hit(f"id:{tenant_id}")

    async def single_active(self) -> TenantContext | None:
        """唯一启用租户（本替身不使用）。"""
        return None

    def _hit(self, label: str) -> TenantContext:
        """记一次调用并按配置返回。

        Args:
            label: 调用标识。

        Returns:
            TenantContext: 固定上下文。

        Raises:
            BizError: 配置的异常（原样抛出）。
        """
        self.calls.add(label)
        if self.error is not None:
            raise self.error
        return _CONTEXT


class _RecordingGuard(SourceTenantGuard):
    """记录 `verify` 调用的守卫（验证钩子顺序与上下文）。"""

    def __init__(self, source: _StubSource) -> None:
        """初始化。

        Args:
            source: 租户源替身。
        """
        super().__init__(source_provider=lambda: source)
        self.verified: ConcurrentStableList[str] = ConcurrentStableList()

    def verify(self, context: TenantContext, scope: str | None = None) -> None:
        """记录校验上下文编码与业务范围标识。"""
        self.verified.add(f"{context.code}:{scope}")


class _RejectingGuard(SourceTenantGuard):
    """`verify` 拒绝的守卫（验证产品自定义错误原样冒泡）。"""

    def __init__(self, source: _StubSource) -> None:
        """初始化。

        Args:
            source: 租户源替身。
        """
        super().__init__(source_provider=lambda: source)

    def verify(self, context: TenantContext, scope: str | None = None) -> None:
        """恒定拒绝（模拟产品的命名空间校验失败）。

        Args:
            context: 已通过租户可用性判定的上下文。
            scope: 业务范围标识（产品自定义；本替身不使用）。

        Raises:
            TenantSuspendedError: 代表产品拒绝（仅为断言冒泡，不改变基类语义）。
        """
        del scope
        raise TenantSuspendedError(f"产品校验拒绝：{context.code}")


def _guard(source: _StubSource) -> SourceTenantGuard:
    """构造默认实现守卫。

    Args:
        source: 租户源替身。

    Returns:
        SourceTenantGuard: 守卫实例。
    """
    return SourceTenantGuard(source_provider=lambda: source)


def _request(app: FastAPI) -> Request:
    """构造仅含 `app` 的请求替身（依赖出口只读 `app.state`）。

    Args:
        app: 应用实例。

    Returns:
        Request: 请求替身（按 `Request` 使用）。
    """
    return cast("Request", SimpleNamespace(app=app))


def test_target_requires_exactly_one_identifier() -> None:
    """三选一：零个 / 多个标识一律参数错误。"""
    with pytest.raises(ParamError) as none_provided:
        TenantTarget()
    assert none_provided.value.code == int(ErrorCode.PARAM)
    with pytest.raises(ParamError) as both_provided:
        TenantTarget(tenant_id="7", code="acme")
    assert both_provided.value.code == int(ErrorCode.PARAM)


def test_target_rejects_malformed_identifiers() -> None:
    """形态先于取数：主键 / 编码 / 域名形态非法即参数错误。"""
    with pytest.raises(ParamError) as bad_id:
        TenantTarget(tenant_id="acme")
    assert bad_id.value.code == int(ErrorCode.PARAM)
    with pytest.raises(ParamError) as bad_code:
        TenantTarget(code="acme-demo")
    assert bad_code.value.code == int(ErrorCode.PARAM)
    with pytest.raises(ParamError) as bad_domain:
        TenantTarget(domain="localhost")
    assert bad_domain.value.code == int(ErrorCode.PARAM)


def test_target_label_and_from_context() -> None:
    """标识文本按主键 / 编码 / 域名优先；上下文派生主键优先、缺失回落编码。"""
    assert TenantTarget(tenant_id="7").label == "7"
    assert TenantTarget(code="acme").label == "acme"
    assert TenantTarget(domain="acme.bms.example.com").label == "acme.bms.example.com"
    assert TenantTarget.from_context(_CONTEXT) == TenantTarget(tenant_id="7")
    context = TenantContext(code="acme", db_key="tenant_acme", name="Acme")
    assert TenantTarget.from_context(context) == TenantTarget(code="acme")


def test_target_from_context_without_identifier_rejected() -> None:
    """上下文既无主键也无编码：参数错误（不构造空定位）。"""
    with pytest.raises(ParamError) as rejected:
        TenantTarget.from_context(TenantContext(code="", db_key="tenant_demo", name="演示"))
    assert rejected.value.code == int(ErrorCode.PARAM)


async def test_require_dispatches_by_identifier() -> None:
    """`require` 按定位分派到租户源对应方法。"""
    source = _StubSource()
    guard = _guard(source)
    assert await guard.require(TenantTarget(tenant_id="7")) is _CONTEXT
    assert await guard.require(TenantTarget(code="acme")) is _CONTEXT
    assert await guard.require(TenantTarget(domain="acme.bms.example.com")) is _CONTEXT
    assert list(source.calls) == ["id:7", "code:acme", "domain:acme.bms.example.com"]


async def test_per_round_matches_require() -> None:
    """循环守卫每轮判定与单次入口结论一致（每轮各回源一次）。"""
    source = _StubSource()
    guard = _guard(source)
    first = await guard.per_round(TenantTarget(tenant_id="7"))
    second = await guard.per_round(TenantTarget(tenant_id="7"))
    assert first is _CONTEXT
    assert second is _CONTEXT
    assert list(source.calls) == ["id:7", "id:7"]


async def test_batch_checks_once_and_reuses_context() -> None:
    """批处理前置：进入校验一次，批内多次取用不再回源。"""
    source = _StubSource()
    guard = _guard(source)
    async with guard.batch(TenantTarget(code="acme")) as tenant:
        assert tenant is _CONTEXT
        assert tenant.tenant_id == 7
    assert list(source.calls) == ["code:acme"]


async def test_batch_propagates_rejection() -> None:
    """批处理进入阶段被拒：异常向外冒泡，批体不执行。"""
    source = _StubSource(error=TenantSuspendedError("租户已停用"))
    guard = _guard(source)
    executed = False
    with pytest.raises(TenantSuspendedError):
        async with guard.batch(TenantTarget(code="acme")):
            executed = True
    assert executed is False


def test_require_sync_runs_without_running_loop() -> None:
    """同步执行体（无运行循环）：正常返回上下文，范围标识同样转交 `verify`。"""
    hook = _RecordingGuard(_StubSource())
    assert hook.require_sync(TenantTarget(tenant_id="7"), scope="audit") is _CONTEXT
    assert list(hook.verified) == ["acme:audit"]


async def test_require_sync_rejects_running_loop() -> None:
    """运行中事件循环内调用同步入口：配置错误（不降级、不放行）。"""
    source = _StubSource()
    guard = _guard(source)
    with pytest.raises(ConfigError):
        guard.require_sync(TenantTarget(tenant_id="7"))
    assert source.calls == []


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_status"),
    (
        (TenantNotFoundError("未知租户"), ErrorCode.TENANT_NOT_FOUND, 404),
        (TenantSuspendedError("租户已停用"), ErrorCode.TENANT_SUSPENDED, 403),
        (ServiceUnavailableError("租户源不可达"), ErrorCode.SERVICE_UNAVAILABLE, 503),
    ),
)
async def test_branches_match_http_entry(error: BizError, expected_code: ErrorCode, expected_status: int) -> None:
    """三分支错误码 / HTTP 状态与 HTTP 入口一致（不出现异步静默继续）。"""
    guard = _guard(_StubSource(error=error))
    with pytest.raises(type(error)) as raised:
        await guard.require(TenantTarget(code="acme"))
    biz = raised.value
    assert biz.code == int(expected_code)
    assert biz.http_status == expected_status


async def test_require_defaults_to_request_context() -> None:
    """未给定位：取完整请求上下文的主键校验。"""
    source = _StubSource()
    guard = _guard(source)
    token = set_tenant_context(_CONTEXT)
    try:
        assert await guard.require() is _CONTEXT
    finally:
        reset_tenant_context(token)
    assert list(source.calls) == ["id:7"]


@pytest.mark.parametrize("context", (None, TenantContext(code="demo", db_key="tenant_demo", name="演示")))
async def test_require_without_complete_context_rejected(context: TenantContext | None) -> None:
    """无上下文 / 演示兜底（无主键）：配置错误，不拿演示租户冒充校验通过。"""
    source = _StubSource()
    guard = _guard(source)
    token = set_tenant_context(context)
    try:
        with pytest.raises(ConfigError):
            await guard.require()
    finally:
        reset_tenant_context(token)
    assert source.calls == []


async def test_verify_hook_default_and_override() -> None:
    """扩展钩子：缺省不拦；覆写后拿到已校验上下文；调用在取数之后。"""
    source = _StubSource()
    await _guard(source).require(TenantTarget(code="acme"))
    hook = _RecordingGuard(source)
    await hook.require(TenantTarget(code="acme"))
    assert list(hook.verified) == ["acme:None"]
    assert list(source.calls) == ["code:acme", "code:acme"]


async def test_scope_flows_to_verify_from_all_entries() -> None:
    """业务范围标识经三个异步入口原样转交 `verify`（基座不解释其语义）。"""
    hook = _RecordingGuard(_StubSource())
    await hook.require(TenantTarget(code="acme"), scope="audit")
    await hook.per_round(TenantTarget(code="acme"), scope="notify")
    async with hook.batch(TenantTarget(code="acme"), scope="file"):
        pass
    assert list(hook.verified) == ["acme:audit", "acme:notify", "acme:file"]


async def test_verify_rejection_propagates() -> None:
    """产品拒绝原样冒泡（基类不吞、不转换）。"""
    guard = _RejectingGuard(_StubSource())
    with pytest.raises(TenantSuspendedError):
        await guard.require(TenantTarget(code="acme"))


async def test_null_guard_fails_closed() -> None:
    """空实现：调用即配置错误（不放行）。"""
    guard = NullTenantGuard()
    assert guard.plugin_name == "null"
    with pytest.raises(ConfigError):
        await guard.require(TenantTarget(code="acme"))
    with pytest.raises(ConfigError):
        await guard.require(TenantTarget(tenant_id="7"))


def test_wiring_registered() -> None:
    """装配接线：能力域键 / 端口 / 配置分区 / 应用状态属性一致。"""
    wirings = {wiring.plugin_key: wiring for wiring in PLUGIN_WIRINGS}
    wiring = wirings["tenant_guard"]
    assert wiring.port is BaseTenantGuard
    assert wiring.settings_section == "tenant_guard"
    assert wiring.state_attr == "tenant_guard"


def test_get_tenant_guard_resolves_null() -> None:
    """依赖出口：provider 为空 → 占位实现（fail-closed）。"""
    settings = Settings()
    settings.tenant_guard.provider = ""
    app = FastAPI()
    app.state.settings = settings
    assert isinstance(get_tenant_guard(_request(app)), NullTenantGuard)


def test_get_tenant_guard_resolves_source_and_unknown() -> None:
    """依赖出口：登记 `source` 后按 provider 解析；未登记实现名报错。"""
    settings = Settings()
    settings.tenant_guard.provider = SOURCE_TENANT_GUARD
    source = _StubSource()
    app = FastAPI()
    app.state.settings = settings
    app.state.tenant_source = source
    register_plugin("tenant_guard", SOURCE_TENANT_GUARD, SourceTenantGuardFactory(app))
    guard = get_tenant_guard(_request(app))
    assert isinstance(guard, SourceTenantGuard)
    settings.tenant_guard.provider = "unknown"
    with pytest.raises(PluginError):
        get_tenant_guard(_request(app))


async def test_source_factory_rejects_missing_tenant_source() -> None:
    """装配缺失租户源：判定时报配置错误（不静默放行）。"""
    app = FastAPI()
    guard = SourceTenantGuardFactory(app).create()
    with pytest.raises(ConfigError):
        await guard.require(TenantTarget(code="acme"))


async def test_platform_plugins_register_source_guard() -> None:
    """平台插件登记后 `source` 可用：守卫经 `app.state.tenant_source` 判定。"""
    settings = Settings()
    settings.tenant_guard.provider = SOURCE_TENANT_GUARD
    app = FastAPI()
    app.state.settings = settings
    app.state.tenant_source = _StubSource()
    register_platform_plugins(settings, app, ResourceManager())
    guard = get_tenant_guard(_request(app))
    assert isinstance(guard, SourceTenantGuard)
    assert await guard.require(TenantTarget(code="acme")) is _CONTEXT


def test_public_dependency_surface_exports_guard() -> None:
    """公共依赖出口（`api/deps.py`）与能力域同源（同一函数对象，不是副本）。"""
    assert exported_get_tenant_guard is get_tenant_guard
