"""基座权限引擎用例（`04_01` 下沉后）：聚合 / 快照 / 缓存 / 失效 / 层级。

引擎只依赖接缝（`permission/sources.py` 的数据来源与元数据）与缓存域——本套用例以**数据来源替身**
驱动主流程，覆盖判定口径与接缝行为；服务侧取数的存储正确性由 platform / identity 各自用例覆盖。
"""

from collections.abc import Iterator

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import current_tenant_id, current_user_id
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
    role_ids: tuple[int, ...] = (1,),
    role_types: tuple[tuple[int, str], ...] = ((1, "system"),),
    grants: tuple[tuple[str, int], ...] = (),
    scopes: tuple[DataScopeRule, ...] = (),
    fields: tuple[FieldPermission, ...] = (),
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
    data = PermissionSubjectData(role_ids=ConcurrentStableSet(role_ids))
    for role_id, role_type in role_types:
        data.role_types.set(role_id, role_type)
    for perm_type, target_id in grants:
        data.grants.add(PermissionGrant(perm_type=perm_type, target_id=target_id))
    for rule in scopes:
        data.data_scope_rules.add(rule)
    for item in fields:
        data.field_perms.add(item)
    return data


def _metadata(
    *,
    version: int = 7,
    menu_forms: tuple[tuple[int, tuple[int, ...]], ...] = (),
    codes: tuple[tuple[int, str], ...] = (),
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
    for menu_id, form_ids in menu_forms:
        metadata.menu_forms.set(menu_id, ConcurrentStableList(form_ids))
    for permission_id, code in codes:
        metadata.permission_codes.set(permission_id, code)
    return metadata


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    """每例前后清空上下文（请求态隔离）。

    Yields:
        None: 用例运行期。
    """
    current_user_id.set(None)
    current_tenant_id.set(None)
    yield
    current_user_id.set(None)
    current_tenant_id.set(None)


@pytest.mark.kiwi_id(2320)
async def test_aggregate_two_stage_resolution() -> None:
    """聚合两段解析：菜单连带其表单、表单独立计入、权限码经索引解析、未入索引的码不计入。"""
    source = _StubSource(
        data=_data(
            grants=(
                ("menu", 1),
                ("form", 12),
                ("permission", 21),
                ("permission", 22),
                ("permission", 99),
                ("ghost", 5),
            ),
            role_types=(),
        ),
        metadata=_metadata(
            menu_forms=((1, (11,)),),
            codes=((21, "role:grant"), (22, "data:export")),
        ),
    )
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion(), exempt_role_types=())
    snapshot = await engine.compute(user_id=5, version=1)
    assert sorted(snapshot.permission_codes) == ["data:export", "role:grant"]
    assert sorted(snapshot.granted_menu_ids) == [1]
    assert sorted(snapshot.granted_form_ids) == [11, 12]
    assert snapshot.tier == TIER_STANDARD


@pytest.mark.kiwi_id(2320)
async def test_aggregate_skips_metadata_when_no_roles() -> None:
    """无角色：聚合直接返回空（不取元数据），码集 / 入口集 / 规则 / 字段均为空。"""
    source = _StubSource(data=_data(role_ids=(), role_types=()))
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
    exempt_source = _StubSource(data=_data(role_types=((1, "system"),)))
    exempt = PermissionEngine(source=exempt_source, cache=MemoryCacheRegion())
    assert (await exempt.compute(user_id=5, version=1)).tier == TIER_SYSTEM_ADMIN

    plain_source = _StubSource(data=_data(role_types=((1, "custom"),)))
    plain = PermissionEngine(source=plain_source, cache=MemoryCacheRegion(), exempt_role_types=("system",))
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
            scopes=(DataScopeRule(data_source_key="1", policy_type="select", config=config),),
            fields=(FieldPermission(form_id=11, field_key="salary", visible=False, editable=False),),
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


@pytest.mark.kiwi_id(2320)
async def test_snapshot_for_caches_and_reuses() -> None:
    """缓存：首次计算后写缓存，第二次命中不再取数。"""
    source = _StubSource(data=_data(grants=(("permission", 21),)), metadata=_metadata(codes=((21, "role:grant"),)))
    engine = PermissionEngine(source=source, cache=MemoryCacheRegion())
    first = await engine.snapshot_for(user_id=5, tenant_id="1001")
    second = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert sorted(first.permission_codes) == ["role:grant"]
    assert sorted(second.permission_codes) == ["role:grant"]
    assert source.subject_calls == 1


@pytest.mark.kiwi_id(2320)
async def test_snapshot_for_recomputes_on_stale_cached_version() -> None:
    """`snapshot_for`：缓存快照版本与当前权限版本不一致时重算并回写。"""
    cache = MemoryCacheRegion()
    engine = PermissionEngine(source=_StubSource(data=_data()), cache=cache)
    key = permission_user_cache_key("1001", 5, 0)
    from bms_core.permission.snapshot import PermissionSnapshot

    await cache.aset(key, PermissionSnapshot(version=99, tier=TIER_STANDARD).to_payload(), ttl=60)

    snapshot = await engine.snapshot_for(user_id=5, tenant_id="1001")
    assert snapshot.version == 0
    assert cache.get(key) is not None


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
    version = await invalidate_permission_cache(cache, tenant_id="1001", user_ids=(7,))
    assert version == 3
    assert await cache.aget(old_key) is None
    assert await invalidate_permission_cache(cache, tenant_id="1001") == 4


@pytest.mark.kiwi_id(2320)
async def test_engine_invalidate_delegates_to_cache() -> None:
    """引擎失效：委托缓存域递增版本（服务侧内部端点与变更钩子共用同一入口）。"""
    cache = MemoryCacheRegion()
    engine = PermissionEngine(source=_StubSource(), cache=cache)
    assert await engine.invalidate(tenant_id="1001") == 1
    assert await engine.invalidate(tenant_id="1001", user_ids=(9,)) == 2


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
