"""三层进程内缓存仓用例（`04_02` / `04_03`，Kiwi 2321 / 2323）。

口径见详细设计 §5.1：三层各自 LRU + TTL，层2 另设元素总量预算；活动用户按最近一次快照读写判定，
闲置超阈值即注销其快照与层1 用户条目；进程级单份，经 `reset_permission_cache_store` 隔离。
`04_03` 追加：规则引用计数（快照侧登记 / 五条移除路径释放）、零引用优先淘汰、值元素与估算字节账目、
TTL 过期回冲与超阈计数。
"""

from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.permission.cache import (
    DEFAULT_METADATA_CACHE_MAX_ITEMS,
    DEFAULT_RULE_CACHE_MAX_ELEMENTS,
    DEFAULT_SNAPSHOT_CACHE_MAX_ITEMS,
    DEFAULT_SUBJECT_CACHE_MAX_ITEMS,
    OPTION_METADATA_CACHE_MAX_ITEMS,
    OPTION_RULE_CACHE_MAX_ELEMENTS,
    OPTION_SNAPSHOT_CACHE_MAX_ITEMS,
    OPTION_SUBJECT_CACHE_MAX_ITEMS,
    RULE_ELEMENT_BYTES,
    RULE_ENTRY_OVERHEAD_BYTES,
    PermissionCacheStore,
    configure_permission_cache_store,
    current_permission_cache_store,
    int_option,
    reset_permission_cache_store,
)
from bms_core.permission.snapshot import PermissionSnapshot
from bms_core.permission.sources import PermissionMetadata, PermissionSubjectData
from bms_core.permission.version import permission_rule_key
from bms_core.scope.base import ScopeCondition

_SOURCE = "test_source"
_OTHER_SOURCE = "other_source"


class _Clock:
    """可控时钟（替身 `bms_core.permission.cache.monotonic`）。"""

    def __init__(self) -> None:
        """初始化（从 1000 秒起，便于断言）。"""
        self.now = 1000.0

    def __call__(self) -> float:
        """取当前时刻。

        Returns:
            float: 当前时刻。
        """
        return self.now


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Clock]:
    """每例替换时钟并复位进程级缓存仓。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        _Clock: 可控时钟。
    """
    fake = _Clock()
    monkeypatch.setattr("bms_core.permission.cache.monotonic", fake)
    reset_permission_cache_store()
    yield fake
    reset_permission_cache_store()


def _subject(marker: str = "") -> PermissionSubjectData:
    """构造聚合输入（可带标记，便于断言命中同一对象）。

    Args:
        marker: 角色类型标记（区分不同实例）。

    Returns:
        PermissionSubjectData: 聚合输入。
    """
    data = PermissionSubjectData()
    if marker:
        data.role_types.set(1, marker)
    return data


def _metadata(version: int = 1) -> PermissionMetadata:
    """构造元数据索引。

    Args:
        version: 元数据版本。

    Returns:
        PermissionMetadata: 元数据索引。
    """
    metadata = PermissionMetadata(version=version)
    metadata.permission_codes.set(1, "user:query")
    return metadata


def _snapshot(version: int = 1) -> PermissionSnapshot:
    """构造权限快照。

    Args:
        version: 权限版本。

    Returns:
        PermissionSnapshot: 快照。
    """
    return PermissionSnapshot(version=version)


def _rules(*values: object) -> ConcurrentStableList[ScopeCondition]:
    """构造规则求值结果（条件列表）。

    Args:
        *values: 条件值。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for value in values:
        result.add(ScopeCondition("id", "in", [value]))
    return result


def _scope_row(
    data_source_key: str = "area", *, policy_type: object = "select", config: object = None
) -> ConcurrentStableDict[str, object]:
    """构造一条快照数据范围规则行（引用登记侧口径）。

    Args:
        data_source_key: 字典类型。
        policy_type: 策略类型（可为非法值，用于跳过分支）。
        config: 规则行（缺省空列表）。

    Returns:
        ConcurrentStableDict[str, object]: 规则行。
    """
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("data_source_key", data_source_key)
    row.set("policy_type", policy_type)
    row.set("config", [] if config is None else config)
    return row


def _snapshot_with(*rows: ConcurrentStableDict[str, object]) -> PermissionSnapshot:
    """构造带数据范围规则行的快照。

    Args:
        *rows: 规则行。

    Returns:
        PermissionSnapshot: 快照。
    """
    scopes: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for row in rows:
        scopes.add(row)
    return PermissionSnapshot(data_scopes=scopes)


def _rule_key(data_source_key: str = "area") -> str:
    """取与 `_scope_row` 同源的层2 规则键。

    Args:
        data_source_key: 字典类型。

    Returns:
        str: 规则键（`permission_rule_key` 产物）。
    """
    key = permission_rule_key(data_source_key=data_source_key, policy_type="select", config=[])
    assert key is not None
    return key


@pytest.mark.kiwi_id(2321)
def test_subject_and_metadata_are_single_copy_per_key() -> None:
    """层1：同键两次读返回同一对象（进程内单份）；换来源 / 换版本即未命中。"""
    store = PermissionCacheStore()
    data = _subject(marker="custom")
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=data)
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is data
    assert store.get_subject(source=_OTHER_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=2) is None

    metadata = _metadata()
    store.set_metadata(source=_SOURCE, locale="zh-CN", version=1, value=metadata)
    assert store.get_metadata(source=_SOURCE, locale="zh-CN", version=1) is metadata
    assert store.get_metadata(source=_SOURCE, locale="en-US", version=1) is None
    assert store.stats()["subject_items"] == 1
    assert store.stats()["metadata_items"] == 1


@pytest.mark.kiwi_id(2321)
def test_ttl_expiry_per_layer(clock: _Clock) -> None:
    """TTL：层1 用户条目 / 层1 元数据 / 层3 快照各自过期（版本号异常时的自愈防线）。"""
    store = PermissionCacheStore(snapshot_ttl=10, metadata_ttl=20)
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_subject())
    store.set_metadata(source=_SOURCE, locale="zh-CN", version=1, value=_metadata())
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot())

    clock.now += 11
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.get_metadata(source=_SOURCE, locale="zh-CN", version=1) is not None

    clock.now += 10
    assert store.get_metadata(source=_SOURCE, locale="zh-CN", version=1) is None


@pytest.mark.kiwi_id(2321)
def test_activity_tracking_and_idle_sweep(clock: _Clock) -> None:
    """活动时间：读写刷新；超 `idle_seconds` 即注销该用户快照与层1 条目。"""
    store = PermissionCacheStore(snapshot_ttl=100_000)
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_subject())
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot())

    clock.now += 1799
    assert store.sweep_idle(1800) == 0
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is not None

    clock.now += 1801  # 上一次访问刷新了活动时间 → 再闲置满阈值才注销
    assert store.sweep_idle(1800) == 1
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.stats()["active_users"] == 0


@pytest.mark.kiwi_id(2321)
def test_sweep_skips_when_threshold_non_positive() -> None:
    """闲置阈值非正：不注销（视为关闭闲置注销，仅保留 TTL 与容量淘汰）。"""
    store = PermissionCacheStore()
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot())
    assert store.sweep_idle(0) == 0
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is not None


@pytest.mark.kiwi_id(2321)
def test_layers_evict_by_capacity() -> None:
    """三层各自条目上限生效（LRU：最久未用先淘汰）。"""
    store = PermissionCacheStore(subject_max_items=1, metadata_max_items=1, snapshot_max_items=1)
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=1, version=1, value=_subject("a"))
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=2, version=1, value=_subject("b"))
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=1, version=1) is None
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=2, version=1) is not None

    store.set_metadata(source=_SOURCE, locale="zh-CN", version=1, value=_metadata())
    store.set_metadata(source=_SOURCE, locale="en-US", version=1, value=_metadata())
    assert store.get_metadata(source=_SOURCE, locale="zh-CN", version=1) is None

    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=1, version=1, value=_snapshot())
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=2, version=1, value=_snapshot())
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=1, version=1) is None
    assert store.stats()["snapshot_items"] == 1


@pytest.mark.kiwi_id(2321)
def test_rule_layer_shares_and_enforces_element_budget() -> None:
    """层2：同键覆盖不重复记账；超元素预算即淘汰最久未用规则。"""
    store = PermissionCacheStore(rule_max_elements=4)
    store.set_rule(source=_SOURCE, rule_key="1|select|aaa", value=_rules(1, 2))
    store.set_rule(source=_SOURCE, rule_key="1|select|aaa", value=_rules(1, 2))  # 同键覆盖
    assert store.stats()["rule_elements"] == 2

    store.set_rule(source=_SOURCE, rule_key="1|select|bbb", value=_rules(3, 4))
    assert store.stats()["rule_elements"] == 4

    store.set_rule(source=_SOURCE, rule_key="1|select|ccc", value=_rules(5))
    assert store.get_rule(source=_SOURCE, rule_key="1|select|aaa") is None
    assert store.get_rule(source=_SOURCE, rule_key="1|select|ccc") is not None
    assert store.stats()["rule_elements"] == 3


@pytest.mark.kiwi_id(2321)
def test_rule_layer_drops_oversize_and_respects_item_limit() -> None:
    """层2：单条超预算不缓存；条目上限仍按 LRU 生效。"""
    budget = PermissionCacheStore(rule_max_elements=2)
    budget.set_rule(source=_SOURCE, rule_key="big", value=_rules(1, 2, 3))
    assert budget.get_rule(source=_SOURCE, rule_key="big") is None
    assert budget.stats()["rule_elements"] == 0

    limited = PermissionCacheStore(rule_max_items=1)
    limited.set_rule(source=_SOURCE, rule_key="a", value=_rules(1))
    limited.set_rule(source=_SOURCE, rule_key="b", value=_rules(2))
    assert limited.get_rule(source=_SOURCE, rule_key="a") is None
    assert limited.stats()["rule_items"] == 1


@pytest.mark.kiwi_id(2321)
def test_rule_layer_disabled_when_budget_non_positive() -> None:
    """层2 元素预算置 0：不缓存规则结果（调用方直接求值）。"""
    store = PermissionCacheStore(rule_max_elements=0)
    store.set_rule(source=_SOURCE, rule_key="a", value=_rules(1))
    assert store.get_rule(source=_SOURCE, rule_key="a") is None
    assert store.stats()["rule_items"] == 0


@pytest.mark.kiwi_id(2321)
def test_invalidate_user_scoped_by_source_and_metadata_reset() -> None:
    """失效：按来源清理指定用户（层1 + 层3）；元数据层整体清空。"""
    store = PermissionCacheStore()
    for source in (_SOURCE, _OTHER_SOURCE):
        store.set_subject(source=source, tenant_id="1001", user_id=5, version=1, value=_subject())
        store.set_snapshot(source=source, tenant_id="1001", user_id=5, version=1, value=_snapshot())

    assert store.invalidate_user(tenant_id="1001", user_id=5, source=_SOURCE) == 2
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.get_snapshot(source=_OTHER_SOURCE, tenant_id="1001", user_id=5, version=1) is not None

    assert store.invalidate_user(tenant_id="1001", user_id=5) == 2
    assert store.stats()["active_users"] == 0

    # 仅层1 有条目（尚未算过快照）的用户没有活动记录，失效同样要能清干净
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=6, version=1, value=_subject())
    assert store.invalidate_user(tenant_id="1001", user_id=6) == 1

    store.set_metadata(source=_SOURCE, locale="zh-CN", version=1, value=_metadata())
    store.set_metadata(source=_SOURCE, locale="en-US", version=1, value=_metadata())
    assert store.invalidate_metadata() == 2
    assert store.stats()["metadata_items"] == 0


@pytest.mark.kiwi_id(2321)
def test_clear_snapshots_keeps_subject_layer() -> None:
    """租户级失效：清空层3 但保留层1 用户条目（下次仅重建快照，不必跨服务取数）。"""
    store = PermissionCacheStore()
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_subject())
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot())
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=6, version=1, value=_snapshot())  # 仅快照用户
    assert store.clear_snapshots() == 2
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is None
    assert store.get_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1) is not None
    assert store.stats()["active_users"] == 1  # 仅层1 用户仍在活动表


@pytest.mark.kiwi_id(2323)
def test_snapshot_registers_and_releases_rule_references() -> None:
    """引用计数：写快照登记规则引用；失效 / 清空 / 闲置注销 / 过期各自释放（计数归零）。"""
    store = PermissionCacheStore()
    key = _rule_key()
    store.set_rule(source=_SOURCE, rule_key=key, value=_rules(1))
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot_with(_scope_row()))
    assert store.stats()["rule_refs"] == 1

    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=6, version=1, value=_snapshot_with(_scope_row()))
    assert store.stats()["rule_refs"] == 1  # 两条快照引用同一规则，规则数仍为 1

    assert store.invalidate_user(tenant_id="1001", user_id=6) == 1
    assert store.stats()["rule_refs"] == 1
    assert store.invalidate_user(tenant_id="1001", user_id=5) == 1
    assert store.stats()["rule_refs"] == 0

    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=7, version=1, value=_snapshot_with(_scope_row()))
    assert store.clear_snapshots() == 1
    assert store.stats()["rule_refs"] == 0

    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=8, version=1, value=_snapshot_with(_scope_row()))
    assert store.sweep_idle(1, now=1e9) == 1
    assert store.stats()["rule_refs"] == 0


@pytest.mark.kiwi_id(2323)
def test_snapshot_rewrite_and_eviction_release_references(clock: _Clock) -> None:
    """同键重写先释放旧引用；层3 LRU 淘汰 / TTL 过期同样释放。"""
    store = PermissionCacheStore(snapshot_ttl=10, snapshot_max_items=1)
    key = _rule_key()
    store.set_rule(source=_SOURCE, rule_key=key, value=_rules(1))

    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot_with(_scope_row()))
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot_with(_scope_row()))
    assert store.stats()["rule_refs"] == 1  # 同键重写不叠加

    store.set_snapshot(
        source=_SOURCE, tenant_id="1001", user_id=6, version=1, value=_snapshot_with(_scope_row("other"))
    )
    assert store.stats()["rule_refs"] == 1  # 层3 LRU 淘汰用户 5 → 其引用释放，仅剩用户 6

    clock.now += 11
    assert store.get_snapshot(source=_SOURCE, tenant_id="1001", user_id=6, version=1) is None
    assert store.stats()["rule_refs"] == 0  # TTL 过期一并释放


@pytest.mark.kiwi_id(2323)
def test_snapshot_skips_rows_without_rule_key() -> None:
    """引用登记跳过：无规则行 / 缺策略类型 / 指纹不可算（config 含不可序列化值）。"""
    store = PermissionCacheStore()
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=1, version=1, value=_snapshot())
    store.set_snapshot(
        source=_SOURCE,
        tenant_id="1001",
        user_id=2,
        version=1,
        value=_snapshot_with(_scope_row(policy_type=123)),
    )
    store.set_snapshot(
        source=_SOURCE,
        tenant_id="1001",
        user_id=3,
        version=1,
        value=_snapshot_with(_scope_row(config=[{1, 2}])),
    )
    assert store.stats()["rule_refs"] == 0


@pytest.mark.kiwi_id(2323)
def test_zero_reference_rule_evicted_first() -> None:
    """零引用优先：超条目上限先淘汰最久未用的零引用规则，被引用规则保留。"""
    store = PermissionCacheStore(rule_max_items=2)
    key = _rule_key()
    store.set_rule(source=_SOURCE, rule_key=key, value=_rules(1))
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot_with(_scope_row()))
    store.set_rule(source=_SOURCE, rule_key="other", value=_rules(2))
    store.set_rule(source=_SOURCE, rule_key="third", value=_rules(3))

    assert store.get_rule(source=_SOURCE, rule_key=key) is not None
    assert store.get_rule(source=_SOURCE, rule_key="other") is None
    assert store.get_rule(source=_SOURCE, rule_key="third") is not None
    assert store.stats()["rule_evicted_total"] == 1


@pytest.mark.kiwi_id(2323)
def test_referenced_rule_evicted_when_all_referenced() -> None:
    """全部被引用：退化为 LRU 淘汰（规则引用记账保留，后续命中重算）。"""
    store = PermissionCacheStore(rule_max_items=1)
    key = _rule_key()
    store.set_rule(source=_SOURCE, rule_key=key, value=_rules(1))
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot_with(_scope_row()))
    store.set_rule(source=_SOURCE, rule_key="other", value=_rules(2))

    assert store.get_rule(source=_SOURCE, rule_key=key) is None
    assert store.get_rule(source=_SOURCE, rule_key="other") is not None
    assert store.stats()["rule_refs"] == 1


@pytest.mark.kiwi_id(2323)
def test_element_budget_counts_value_elements() -> None:
    """元素预算按值元素总数计：大集合单条即超预算（不缓存），且不残留账目。"""
    store = PermissionCacheStore(rule_max_elements=1000)
    store.set_rule(source=_SOURCE, rule_key="big", value=_rules(1), elements=5000)
    assert store.get_rule(source=_SOURCE, rule_key="big") is None
    assert store.stats()["rule_elements"] == 0
    assert store.stats()["rule_estimated_bytes"] == 0
    assert store.stats()["rule_evicted_total"] == 1


@pytest.mark.kiwi_id(2323)
def test_rule_accounts_reclaimed_on_ttl_expiry(clock: _Clock) -> None:
    """TTL 过期：条目删除的同时回冲元素 / 字节账目（旧口径会长期占用预算）。"""
    store = PermissionCacheStore(snapshot_ttl=10, rule_max_elements=100)
    store.set_rule(source=_SOURCE, rule_key="a", value=_rules(1), elements=3)
    assert store.stats()["rule_elements"] == 3

    clock.now += 11
    assert store.get_rule(source=_SOURCE, rule_key="a") is None
    assert store.stats()["rule_elements"] == 0
    assert store.stats()["rule_estimated_bytes"] == 0


@pytest.mark.kiwi_id(2323)
def test_stats_reports_estimated_bytes_refs_and_caps() -> None:
    """度量：估算字节 = 条目开销 + 元素数 × 元素字节；各层上限随配置输出；超阈计数可复位。"""
    store = PermissionCacheStore(rule_max_items=9, rule_max_elements=50, snapshot_max_items=7)
    store.set_rule(source=_SOURCE, rule_key="a", value=_rules(1), elements=4)
    store.record_oversized_rule()
    store.record_oversized_rule()
    stats = store.stats()
    assert stats["rule_estimated_bytes"] == RULE_ENTRY_OVERHEAD_BYTES + 4 * RULE_ELEMENT_BYTES
    assert stats["oversized_rejections"] == 2
    assert stats["rule_max_items"] == 9
    assert stats["rule_max_elements"] == 50
    assert stats["snapshot_max_items"] == 7
    assert stats["subject_max_items"] == DEFAULT_SUBJECT_CACHE_MAX_ITEMS
    assert stats["metadata_max_items"] == DEFAULT_METADATA_CACHE_MAX_ITEMS

    store.reset()
    assert store.stats()["oversized_rejections"] == 0
    assert store.stats()["rule_refs"] == 0


@pytest.mark.kiwi_id(2321)
def test_reset_clears_all_layers() -> None:
    """复位：三层与活动记录一并清空（保留容量配置）。"""
    store = PermissionCacheStore(subject_max_items=1)
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_subject())
    store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=5, version=1, value=_snapshot())
    store.set_rule(source=_SOURCE, rule_key="a", value=_rules(1))
    store.reset()
    stats = store.stats()
    assert stats["subject_items"] == 0
    assert stats["metadata_items"] == 0
    assert stats["rule_items"] == 0
    assert stats["rule_elements"] == 0
    assert stats["rule_estimated_bytes"] == 0
    assert stats["snapshot_items"] == 0
    assert stats["active_users"] == 0
    assert stats["subject_max_items"] == 1  # 容量配置保留


@pytest.mark.kiwi_id(2321)
def test_configure_reads_options_with_conservative_defaults() -> None:
    """配置：`[permission].options` 分层键生效；缺项 / 类型不符回落缺省。"""
    options: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    options.set(OPTION_SUBJECT_CACHE_MAX_ITEMS, 1)
    options.set(OPTION_SNAPSHOT_CACHE_MAX_ITEMS, True)  # 布尔不算整数 → 回落缺省
    options.set(OPTION_METADATA_CACHE_MAX_ITEMS, "8")  # 字符串不算整数 → 回落缺省
    options.set(OPTION_RULE_CACHE_MAX_ELEMENTS, 5)
    store = configure_permission_cache_store(options, snapshot_ttl=60)
    assert current_permission_cache_store() is store
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=1, version=1, value=_subject())
    store.set_subject(source=_SOURCE, tenant_id="1001", user_id=2, version=1, value=_subject())
    assert store.stats()["subject_items"] == 1
    assert store.get_rule(source=_SOURCE, rule_key="missing") is None
    assert DEFAULT_SUBJECT_CACHE_MAX_ITEMS == 2000
    assert DEFAULT_SNAPSHOT_CACHE_MAX_ITEMS == 5000
    assert DEFAULT_METADATA_CACHE_MAX_ITEMS == 16
    assert DEFAULT_RULE_CACHE_MAX_ELEMENTS == 200_000


@pytest.mark.kiwi_id(2321)
def test_int_option_fallbacks_and_singleton_reset() -> None:
    """选项解析助手：None / 缺项 / 布尔 / 整数；进程级单份经复位重建。"""
    assert int_option(None, "k", 7) == 7
    assert int_option({}, "k", 7) == 7
    assert int_option({"k": True}, "k", 7) == 7
    assert int_option({"k": 3}, "k", 7) == 3

    first = current_permission_cache_store()
    first.set_rule(source=_SOURCE, rule_key="a", value=_rules(1))
    reset_permission_cache_store()
    second = current_permission_cache_store()
    assert second is not first
    assert second.get_rule(source=_SOURCE, rule_key="a") is None
    reset_permission_cache_store()  # 无实例时复位不报错
