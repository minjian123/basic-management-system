"""基座权限接缝用例（`04_01`）：数据来源注册表 + 内建校验器判定 + 数据来源缺失拒启。

覆盖「判定在基座、数据访问经接缝」的下沉边界：注册表按 key 覆盖与清空、请求级工厂优先于实例、
`aprepare` 的请求级幂等与无用户上下文分支、`check` 的从严拒绝 / 豁免 / 码集命中，以及
**provider=rbac 但未登记数据来源即拒启**（fail-closed）。
"""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.exceptions import PluginError
from bms_core.permission.cache import (
    OPTION_IDLE_SWEEP_INTERVAL,
    OPTION_IDLE_TIMEOUT,
    current_permission_cache_store,
    reset_permission_cache_store,
)
from bms_core.permission.guard import (
    BasePermissionGuard,
    PermissionGuardContext,
    register_permission_guard,
    reset_permission_guards,
)
from bms_core.permission.rbac import (
    RBAC_PROVIDER_NAME,
    RbacPermissionChecker,
    RbacPermissionCheckerFactory,
)
from bms_core.permission.snapshot import (
    TIER_PLATFORM_ADMIN,
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    get_current_permission_snapshot,
    set_current_permission_snapshot,
)
from bms_core.permission.sources import (
    BasePermissionDataSource,
    PermissionMetadata,
    PermissionSubjectData,
    current_permission_data_source,
    current_permission_data_source_factory,
    has_permission_data_source,
    register_permission_data_source,
    register_permission_data_source_factory,
    reset_permission_data_sources,
)


class _Source(BasePermissionDataSource):
    """数据来源替身（空数据）。"""

    key: str = "stub_source"

    async def load_subject(self, *, user_id: int) -> PermissionSubjectData:
        """返回空数据。

        Args:
            user_id: 用户主键（忽略）。

        Returns:
            PermissionSubjectData: 空数据。
        """
        del user_id
        return PermissionSubjectData()

    async def load_metadata(self, *, locale: str = "zh-CN") -> PermissionMetadata:
        """返回空元数据。

        Args:
            locale: 语言标识（忽略）。

        Returns:
            PermissionMetadata: 空元数据。
        """
        del locale
        return PermissionMetadata()


class _OtherSource(_Source):
    """另一实现（同 key 覆盖用）。"""

    key: str = "other_source"


class _DenyGuard(BasePermissionGuard):
    """恒拒校验链环节（测接缝 3：码命中后仍可被条件环节拦下）。"""

    key: str = "deny_all"

    def allow(self, context: PermissionGuardContext) -> bool:
        """恒拒。

        Args:
            context: 校验上下文（忽略）。

        Returns:
            bool: False。
        """
        del context
        return False


class _Clock:
    """可控时钟（替身 `bms_core.permission.cache.monotonic`）。"""

    def __init__(self) -> None:
        """初始化（从 1000 秒起）。"""
        self.now = 1000.0

    def __call__(self) -> float:
        """取当前时刻。

        Returns:
            float: 当前时刻。
        """
        return self.now


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    """每例前后清空数据来源注册表 / 快照 / 校验链 / 上下文 / 三层缓存仓。

    Yields:
        None: 用例运行期。
    """
    reset_permission_data_sources()
    set_current_permission_snapshot(None)
    reset_permission_guards()
    reset_permission_cache_store()
    yield
    reset_permission_data_sources()
    set_current_permission_snapshot(None)
    reset_permission_guards()
    reset_permission_cache_store()
    current_user_id.set(None)
    current_tenant_id.set(None)


def _request(*, cache: object | None = None) -> Request:
    """构造最小请求（带应用状态与缓存）。

    Args:
        cache: 应用状态上的缓存域（缺省内存实现）。

    Returns:
        Request: 请求对象。
    """
    app = FastAPI()
    app.state.cache = cache if cache is not None else MemoryCacheRegion()
    return Request(scope={"type": "http", "method": "GET", "path": "/x", "headers": [], "app": app})


@pytest.mark.kiwi_id(2320)
def test_data_source_registry_register_override_and_reset() -> None:
    """注册表：登记即取到；同 key 覆盖；清空后为空；未登记即「无来源」。"""
    assert has_permission_data_source() is False
    assert current_permission_data_source() is None

    first = _Source()
    register_permission_data_source(first)
    assert current_permission_data_source() is first
    assert has_permission_data_source() is True

    override = _Source()
    register_permission_data_source(override)
    assert current_permission_data_source() is override

    reset_permission_data_sources()
    assert current_permission_data_source() is None
    assert has_permission_data_source() is False


@pytest.mark.kiwi_id(2320)
def test_data_source_factory_takes_precedence_over_instance() -> None:
    """请求级工厂优先于实例型来源（会话随请求开启的实现走工厂）。"""
    instance = _Source()
    register_permission_data_source(instance)
    assert current_permission_data_source_factory() is None

    async def _factory(request: Request) -> BasePermissionDataSource:
        """构造请求级来源。

        Args:
            request: 当前请求（忽略）。

        Returns:
            BasePermissionDataSource: 来源。
        """
        del request
        return _OtherSource()

    register_permission_data_source_factory("other", _factory)
    assert current_permission_data_source_factory() is _factory
    assert has_permission_data_source() is True


@pytest.mark.kiwi_id(2320)
def test_factory_rejects_when_no_data_source_registered() -> None:
    """fail-closed：`provider = rbac` 但未登记任何数据来源 → 构造校验器即拒（PluginError）。"""
    factory = RbacPermissionCheckerFactory(Settings())
    with pytest.raises(PluginError):
        factory.create()


@pytest.mark.kiwi_id(2320)
def test_factory_builds_checker_with_options() -> None:
    """工厂：登记来源后按 `[permission].options` 构造校验器。"""
    register_permission_data_source(_Source())
    factory = RbacPermissionCheckerFactory(Settings())
    checker = factory.create()
    assert isinstance(checker, RbacPermissionChecker)
    assert RBAC_PROVIDER_NAME == "rbac"


@pytest.mark.kiwi_id(2320)
def test_check_denies_without_preloaded_snapshot() -> None:
    """未预加载（依赖漏挂）时**从严拒绝**，而非放行。"""
    checker = RbacPermissionChecker()
    assert checker.check("menu") is False


@pytest.mark.kiwi_id(2320)
def test_check_uses_snapshot_codes() -> None:
    """码级判定：命中即通过；未命中即拒。"""
    checker = RbacPermissionChecker()
    codes: ConcurrentStableSet[str] = ConcurrentStableSet()
    codes.add("role:grant")
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_STANDARD, permission_codes=codes))
    assert checker.check("role:grant") is True
    assert checker.check("role:delete") is False


@pytest.mark.kiwi_id(2320)
def test_exempt_tiers_allow_all() -> None:
    """豁免层级（系统管理员 / 平台层）恒通过，且不校验码集。"""
    checker = RbacPermissionChecker()
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_SYSTEM_ADMIN))
    assert checker.check("anything:at-all") is True
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_PLATFORM_ADMIN))
    assert checker.check("anything:at-all") is True


@pytest.mark.kiwi_id(2320)
def test_guard_chain_can_deny_after_code_hit() -> None:
    """校验链（接缝 3）：码命中后仍可被条件环节拦下；移出环节即恢复。"""
    checker = RbacPermissionChecker()
    codes: ConcurrentStableSet[str] = ConcurrentStableSet()
    codes.add("role:grant")
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_STANDARD, permission_codes=codes))
    assert checker.check("role:grant") is True
    register_permission_guard(_DenyGuard())
    assert checker.check("role:grant") is False
    reset_permission_guards()
    assert checker.check("role:grant") is True


@pytest.mark.kiwi_id(2320)
async def test_aprepare_without_user_yields_platform_tier_and_is_idempotent() -> None:
    """预加载：无当前用户 → 平台层快照（豁免）；重复调用直接返回（单请求只算一次）。"""
    checker = RbacPermissionChecker()
    request = _request()
    current_user_id.set(None)
    await checker.aprepare(request=request)
    snapshot = get_current_permission_snapshot()
    assert snapshot is not None and snapshot.tier == TIER_PLATFORM_ADMIN
    assert getattr(request.state, "permission_prepared", False) is True
    await checker.aprepare(request=request)


@pytest.mark.kiwi_id(2320)
async def test_aprepare_with_user_uses_registered_source() -> None:
    """预加载：有当前用户 → 经登记的数据来源计算快照并落 contextvar。"""
    register_permission_data_source(_Source())
    checker = RbacPermissionChecker()
    request = _request()
    current_user_id.set(5)
    current_tenant_id.set("1001")
    await checker.aprepare(request=request)
    snapshot = get_current_permission_snapshot()
    assert snapshot is not None
    assert snapshot.tier == TIER_STANDARD
    assert list(snapshot.permission_codes) == []


@pytest.mark.kiwi_id(2320)
async def test_aprepare_uses_request_level_factory() -> None:
    """预加载：请求级工厂存在时优先走工厂（会话随请求开启的实现）。"""
    seen: ConcurrentStableList[int] = ConcurrentStableList()

    async def _factory(request: Request) -> BasePermissionDataSource:
        """记录被调用并返回来源。

        Args:
            request: 当前请求（忽略）。

        Returns:
            BasePermissionDataSource: 来源。
        """
        del request
        seen.add(1)
        return _Source()

    register_permission_data_source_factory("req", _factory)
    checker = RbacPermissionChecker()
    current_user_id.set(5)
    current_tenant_id.set("1001")
    await checker.aprepare(request=_request())
    assert list(seen) == [1]


@pytest.mark.kiwi_id(2320)
async def test_aprepare_rejects_when_source_missing() -> None:
    """预加载：有用户但无数据来源 → 抛 PluginError（不静默放行 / 不静默全拒）。"""
    checker = RbacPermissionChecker()
    current_user_id.set(5)
    current_tenant_id.set("1001")
    with pytest.raises(PluginError):
        await checker.aprepare(request=_request())


@pytest.mark.kiwi_id(2321)
def test_factory_configures_process_store_with_options() -> None:
    """装配：工厂按 `[permission].options` 建三层缓存仓，并把闲置阈值注入校验器。"""
    register_permission_data_source(_Source())
    settings = Settings()
    settings.permission.options.set(OPTION_IDLE_TIMEOUT, 90)
    settings.permission.options.set(OPTION_IDLE_SWEEP_INTERVAL, 15)
    checker = RbacPermissionCheckerFactory(settings).create()
    assert checker.store is current_permission_cache_store()
    assert checker.idle_timeout == 90
    assert checker.sweep_interval == 15


@pytest.mark.kiwi_id(2321)
async def test_setup_starts_idle_sweep_and_aclose_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """生命周期：`setup` 起巡检任务、按闲置阈值注销快照；`aclose` 停任务（幂等）。"""
    clock = _Clock()
    monkeypatch.setattr("bms_core.permission.cache.monotonic", clock)
    checker = RbacPermissionChecker(idle_timeout=1800, sweep_interval=0.01)
    checker.store.set_snapshot(source=_Source.key, tenant_id="1001", user_id=5, version=0, value=PermissionSnapshot())
    clock.now += 1801

    await checker.setup()
    await checker.setup()  # 幂等：重复装配不重复起任务
    await asyncio.sleep(0.05)
    assert checker.store.stats()["snapshot_items"] == 0
    await checker.aclose()
    assert checker.sweep_task is None
    await checker.aclose()  # 无任务时复用不报错


@pytest.mark.kiwi_id(2321)
async def test_setup_skipped_when_idle_disabled() -> None:
    """巡检可关闭：阈值或周期非正即不起后台任务（仅保留 TTL 与容量淘汰）。"""
    disabled = RbacPermissionChecker(idle_timeout=0)
    await disabled.setup()
    assert disabled.sweep_task is None

    no_interval = RbacPermissionChecker(sweep_interval=0)
    await no_interval.setup()
    assert no_interval.sweep_task is None


@pytest.mark.kiwi_id(2321)
async def test_sweep_loop_survives_single_round_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """巡检健壮性：单轮异常只记日志，不终止循环。"""
    checker = RbacPermissionChecker(sweep_interval=0.01)
    calls: ConcurrentStableList[int] = ConcurrentStableList()

    def _boom(idle_seconds: int, *, now: float | None = None) -> int:
        """抛错替身。

        Args:
            idle_seconds: 闲置阈值（忽略）。
            now: 当前时刻（忽略）。

        Returns:
            int: 不会返回。

        Raises:
            RuntimeError: 恒定抛出。
        """
        del idle_seconds, now
        calls.add(1)
        raise RuntimeError("sweep boom")

    monkeypatch.setattr(checker.store, "sweep_idle", _boom)
    await checker.setup()
    await asyncio.sleep(0.05)
    assert len(calls) >= 1
    assert checker.sweep_task is not None
    assert checker.sweep_task.done() is False
    await checker.aclose()
