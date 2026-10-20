"""基座权限引擎用例（`04_01` 下沉后 + `04_02` 三层缓存）：聚合 / 快照 / 缓存 / 失效 / 层级。

引擎只依赖接缝（`permission/sources.py` 与 `permission/cache.py`）与缓存域（版本号）——本套用例以
**数据来源替身**驱动主流程，覆盖判定口径与接缝行为；服务侧取数的存储正确性由 platform / identity 各自
用例覆盖。`04_02` 后快照与基础数据在**进程内三层缓存**，共享缓存域只承载版本号。
"""

from collections.abc import Iterator

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.permission.cache import (
    PermissionCacheStore,
    current_permission_cache_store,
    reset_permission_cache_store,
)
from bms_core.permission.engine import (
    DEFAULT_SNAPSHOT_TTL,
    PermissionEngine,
    invalidate_permission_cache,
)
from bms_core.permission.field import FieldPermission
from bms_core.permission.snapshot import TIER_STANDARD, TIER_SYSTEM_ADMIN
from bms_core.permission.sources import (
    BasePermissionDataSource,
    DataScopeRule,
    PermissionGrant,
    PermissionMetadata,
    PermissionSubjectData,
)
from bms_core.permission.version import permission_user_cache_key, permission_version_key


class _StubSource(BasePermissionDataSource):
    """数据来源替身：按构造给定的数据返回（可配空角色 / 异常）。"""

    key: str = "stub_permission_source"

    def __init__(
        self,
        *,
        data: PermissionSubjectData | None = None,
        metadata: PermissionMetadata | None = None,
        error: Exception | None = None,
    ) -> None:
        """初始化。

        Args:
            data: 按用户返回的数据（None 表示空数据）。
            metadata: 元数据（None 表示空元数据）。
            error: 抛出的异常（模拟取数失败）。
        """
        self._data = data if data is not None else PermissionSubjectData()
        self._metadata = metadata if metadata is not None else PermissionMetadata()
        self._error = error
        self.subject_calls = 0
        self.metadata_calls = 0

    async def load_subject(self, *, user_id: int) -> PermissionSubjectData:
        """返回构造的数据。

        Args:
            user_id: 用户主键（忽略）。

        Returns:
            PermissionSubjectData: 数据。

        Raises:
            Exception: 配置的异常。
        """
        del user_id
        self.subject_calls += 1
        if self._error is not None:
            raise self._error
        return self._data

    async def load_metadata(self, *, locale: str = "zh-CN") -> PermissionMetadata:
        """返回构造的元数据。

        Args:
            locale: 语言标识（忽略）。

        Returns:
            PermissionMetadata: 元数据。
        """
        del locale
        self.metadata_calls += 1
        return self._metadata


def _data(
    *,
    role_ids: ConcurrentStableList[int] | None = None,
    role_types: ConcurrentStableList[tuple[int, str]] | None = None,
    grants: ConcurrentStableList[tuple[str, int]] | None = None,
    scopes: ConcurrentStableList[DataScopeRule] | None = None,
    fields: ConcurrentStableList[FieldPermission] | None = None,
) -> PermissionSubjectData:
    """构造聚合输入。

    Args:
        role_ids: 角色主键。
        role_types: 角色类型映射项。
        grants: 授权行（类型, 目标 id）。
        scopes: 数据范围规则。
        fields: 字段收窄项。

    Returns:
        PermissionSubjectData: 聚合输入。
    """
    data = PermissionSubjectData(role_ids=ConcurrentStableSet(role_ids if role_ids is not None else (1,)))
    for role_id, role_type in role_types if role_types is not None else ((1, "system"),):
        data.role_types.set(role_id, role_type)
    for perm_type, target_id in grants or ():
        data.grants.add(PermissionGrant(perm_type=perm_type, target_id=target_id))
    for rule in scopes or ():
        data.data_scope_rules.add(rule)
    for item in fields or ():
        data.field_perms.add(item)
    return data


def _metadata(
    *,
    version: int = 7,
    menu_forms: ConcurrentStableList[tuple[int, ConcurrentStableFrozenList[int]]] | None = None,
    codes: ConcurrentStableList[tuple[int, str]] | None = None,
) -> PermissionMetadata:
    """构造元数据索引。

    Args:
        version: 元数据版本。
        menu_forms: 菜单 → 表单项。
        codes: 权限码 id → 权限码项。

    Returns:
        PermissionMetadata: 元数据。
    """
    metadata = PermissionMetadata(version=version)
    for menu_id, form_ids in menu_forms or ():
        metadata.menu_forms.set(menu_id, ConcurrentStableList(form_ids))
    for permission_id, code in codes or ():
        metadata.permission_codes.set(permission_id, code)
    return metadata


class _Clock:
    """可控时钟（替身 `bms_core.permission.cache.monotonic`，用于闲置注销断言）。"""

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
def clean_context() -> Iterator[None]:
    """每例前后清空上下文（请求态隔离）并复位进程级三层缓存仓。

    Yields:
        None: 用例运行期。
    """
    current_user_id.set(None)
    current_tenant_id.set(None)
    reset_permission_cache_store()
    yield
    current_user_id.set(None)
    current_tenant_id.set(None)
    reset_permission_cache_store()


@pytest.mark.kiwi_id(2320)
async def test_aggregate_two_stage_resolution() -> None:
    """聚合两段解析：菜单连带其表单、表单独立计入、权限码经索引解析、未入索引的码不计入。"""
    source = _StubSource(
        data=_data(
            grants=ConcurrentStableList(
                (("menu", 1), ("form", 12), ("permission", 21), ("permission", 22), ("permission", 99), ("ghost", 5))
            ),
            role_types=ConcurrentStableList(()),
        ),
        metadata=_metadata(
            menu_forms=ConcurrentStableList(ConcurrentStableList(((1, (11,)),))),  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定
            codes=ConcurrentStableList(((21, "role:grant"), (22, "data:export"))),
        ),
    )
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion(), exempt_role_types=ConcurrentStableList(()))
    snapshot = await engine.compute(user_id=5, version=1)
    assert sorted(snapshot.permission_codes) == ["data:export", "role:grant"]
    assert sorted(snapshot.granted_menu_ids) == [1]
    assert sorted(snapshot.granted_form_ids) == [11, 12]
    assert snapshot.tier == TIER_STANDARD


@pytest.mark.kiwi_id(2320)
async def test_aggregate_skips_metadata_when_no_roles() -> None:
    """无角色：聚合直接返回空（不取元数据），码集 / 入口集 / 规则 / 字段均为空。"""
    source = _StubSource(data=_data(role_ids=ConcurrentStableList(()), role_types=ConcurrentStableList(())))
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion())
    snapshot = await engine.compute(user_id=5, version=1)
    assert list(snapshot.permission_codes) == []
    assert list(snapshot.granted_menu_ids) == []
    assert list(snapshot.granted_form_ids) == []
    assert list(snapshot.data_scopes) == []
    assert list(snapshot.field_perms) == []
    assert source.metadata_calls == 0


@pytest.mark.kiwi_id(2320)
async def test_exempt_tier_from_role_types() -> None:
    """层级判定：命中豁免角色类型即系统管理员；不在豁免集合即普通。"""
    exempt_source = _StubSource(data=_data(role_types=ConcurrentStableList(((1, "system"),))))
    exempt = PermissionEngine(source=exempt_source, cache=MemoryCacheRegion())
    assert (await exempt.compute(user_id=5, version=1)).tier == TIER_SYSTEM_ADMIN

    plain_source = _StubSource(data=_data(role_types=ConcurrentStableList(((1, "custom"),))))
    plain = PermissionEngine(
        source=plain_source, cache=MemoryCacheRegion(), exempt_role_types=ConcurrentStableList(("system",))
    )
    assert (await plain.compute(user_id=5, version=1)).tier == TIER_STANDARD


@pytest.mark.kiwi_id(2320)
async def test_data_scope_rules_and_field_perms_flow_into_snapshot() -> None:
    """数据范围规则与字段收窄项原样进入快照（读注入 / 写拒绝的输入）。"""
    config: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("field", "area_code")
    config.add(row)
    source = _StubSource(
        data=_data(
            scopes=ConcurrentStableList((DataScopeRule(data_source_key="1", policy_type="select", config=config),)),
            fields=ConcurrentStableList(
                (FieldPermission(form_id=11, field_key="salary", visible=False, editable=False),)
            ),
        )
    )
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion())
    snapshot = await engine.compute(user_id=5, version=1)
    assert len(snapshot.data_scopes) == 1
    rule = snapshot.data_scopes[0]
    assert rule.get("data_source_key") == "1"
    assert rule.get("policy_type") == "select"
    assert rule.get("config") == [{"field": "area_code"}]
    assert snapshot.field_state(11, "salary") == (False, False)
    assert snapshot.field_state(11, "name") is None


@pytest.mark.kiwi_id(2321)
async def test_snapshot_for_caches_and_reuses() -> None:
    """缓存：首次计算后写进程内缓存，第二次命中不再取数。"""
    source = _StubSource(
        data=_data(grants=ConcurrentStableList((("permission", 21),))),
        metadata=_metadata(codes=ConcurrentStableList(((21, "role:grant"),))),
    )
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion())
    first = await engine.snapshot_for(user_id=5, tenant_id="1001")
    second = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert sorted(first.permission_codes) == ["role:grant"]
    assert sorted(second.permission_codes) == ["role:grant"]
    assert first is second
    assert source.subject_calls == 1


@pytest.mark.kiwi_id(2321)
async def test_snapshot_stays_in_process_not_shared_cache() -> None:
    """快照不落共享缓存：`CacheRegion` 里只出现版本号键，用户快照键不产生。"""
    cache = MemoryCacheRegion()
    engine = PermissionEngine(source=_StubSource(data=_data()), cache=cache)
    await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert await cache.aget(permission_version_key("1001")) is None  # 未失效时连版本键都不写
    assert cache.get(permission_user_cache_key("1001", 5, 0)) is None
    assert current_permission_cache_store().stats()["snapshot_items"] == 1


@pytest.mark.kiwi_id(2321)
async def test_layer1_serves_subject_and_metadata_without_source_calls() -> None:
    """层1：快照被清后重建时不再回源（subject / metadata 各只取一次）——identity 跨服务往返同收益。"""
    source = _StubSource(
        data=_data(grants=ConcurrentStableList((("permission", 21),))),
        metadata=_metadata(codes=ConcurrentStableList(((21, "role:grant"),))),
    )
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion())
    await engine.snapshot_for(user_id=5, tenant_id="1001")
    current_permission_cache_store().clear_snapshots()
    snapshot = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert sorted(snapshot.permission_codes) == ["role:grant"]
    assert source.subject_calls == 1
    assert source.metadata_calls == 1


@pytest.mark.kiwi_id(2321)
async def test_snapshot_for_recomputes_after_version_bump() -> None:
    """版本换键：`invalidate` 后版本 +1，旧版本快照不可见 → 重算并回填新版本。"""
    cache = MemoryCacheRegion()
    source = _StubSource(data=_data())
    engine = PermissionEngine(source=source, cache=cache)
    first = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert first.version == 0

    assert await engine.invalidate(tenant_id="1001") == 1
    second = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert second.version == 1
    assert source.subject_calls == 2


@pytest.mark.kiwi_id(2321)
async def test_idle_sweep_forces_recompute_and_refill(monkeypatch: pytest.MonkeyPatch) -> None:
    """闲置注销：30 分钟不活动后快照与层1 条目被注销，再次访问即时重算并回填。"""
    clock = _Clock()
    monkeypatch.setattr("bms_core.permission.cache.monotonic", clock)
    store = PermissionCacheStore()
    source = _StubSource(data=_data())
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion(), store=store)
    await engine.snapshot_for(user_id=5, tenant_id="1001")

    clock.now += 1801
    assert store.sweep_idle(1800) == 1
    assert store.stats()["snapshot_items"] == 0

    snapshot = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert snapshot.version == 0
    assert store.stats()["snapshot_items"] == 1
    assert source.subject_calls == 2


@pytest.mark.kiwi_id(2321)
async def test_invalidate_clears_process_entries() -> None:
    """失效清理：给定用户清该用户层1 + 层3；全租户失效只释放快照（层1 留待重建免回源）。"""
    store = PermissionCacheStore()
    engine = PermissionEngine(source=_StubSource(data=_data()), cache=MemoryCacheRegion(), store=store)
    await engine.snapshot_for(user_id=7, tenant_id="1001")
    await engine.invalidate(tenant_id="1001", user_ids=ConcurrentStableList((7,)))
    assert store.stats()["snapshot_items"] == 0
    assert store.stats()["subject_items"] == 0

    await engine.snapshot_for(user_id=7, tenant_id="1001")
    await engine.invalidate(tenant_id="1001")
    assert store.stats()["snapshot_items"] == 0
    assert store.stats()["subject_items"] == 1


@pytest.mark.kiwi_id(2320)
async def test_current_version_defaults_to_zero_and_reads_counter() -> None:
    """权限版本：未命中按 0；计数器递增后取到新值。"""
    cache = MemoryCacheRegion()
    engine = PermissionEngine(source=_StubSource(), cache=cache)
    assert await engine.current_version("1001") == 0
    await cache.aincrease(permission_version_key("1001"))
    await cache.aincrease(permission_version_key("1001"))
    assert await engine.current_version("1001") == 2


@pytest.mark.kiwi_id(2320)
async def test_invalidate_bumps_version_and_evicts_previous_user_key() -> None:
    """失效链路：租户权限版本 +1，并删除受影响用户的旧版本键。"""
    cache = MemoryCacheRegion()
    version_key = permission_version_key("1001")
    await cache.aincrease(version_key)
    await cache.aincrease(version_key)
    old_key = permission_user_cache_key("1001", 7, 2)
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    await cache.aset(old_key, dict(payload), ttl=60)
    version = await invalidate_permission_cache(cache, tenant_id="1001", user_ids=ConcurrentStableList((7,)))
    assert version == 3
    assert await cache.aget(old_key) is None
    assert await invalidate_permission_cache(cache, tenant_id="1001") == 4


@pytest.mark.kiwi_id(2320)
async def test_engine_invalidate_delegates_to_cache() -> None:
    """引擎失效：委托缓存域递增版本（服务侧内部端点与变更钩子共用同一入口）。"""
    cache = MemoryCacheRegion()
    engine = PermissionEngine(source=_StubSource(), cache=cache)
    assert await engine.invalidate(tenant_id="1001") == 1
    assert await engine.invalidate(tenant_id="1001", user_ids=ConcurrentStableList((9,))) == 2


@pytest.mark.kiwi_id(2320)
async def test_source_failure_propagates() -> None:
    """取数失败：异常上抛（不静默返回空集——空集是「无权限」、失败是故障，语义不同）。"""
    engine = PermissionEngine(source=_StubSource(error=RuntimeError("db down")), cache=MemoryCacheRegion())
    with pytest.raises(RuntimeError):
        await engine.compute(user_id=5, version=1)


@pytest.mark.kiwi_id(2320)
def test_default_snapshot_ttl_is_documented_value() -> None:
    """缺省快照 TTL 与配置口径一致（300 秒）。"""
    assert DEFAULT_SNAPSHOT_TTL == 300
