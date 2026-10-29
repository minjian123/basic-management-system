"""租户拓扑快照与第二段解析：回退 / 覆盖 / 失败三态 / 库派生 / 协议替换（07C `02_01`；Kiwi 2366）。

覆盖设计 §5 用例 2（覆盖默认）、3（租户无记录回退）、11（`disabled`）、12（版本可见）、
13（库派生）、14（协议替换）；用例 2 的分层部分（服务端整批写入）见平台服务测试。
"""

from collections.abc import Iterator
from typing import cast

import pytest

from bms_core.collaboration import (
    DEFAULT_TOPOLOGY_TENANT,
    TOPOLOGY_SNAPSHOT_LIMIT,
    CapabilityMode,
    DomainLayoutTopologyResolver,
    TenantTopologyResolver,
    TopologyEntry,
    TopologySnapshot,
    register_topology_resolver,
    register_topology_snapshot,
    reset_instance_context,
    reset_topology_resolver,
    reset_topology_snapshots,
    resolve_for,
    resolve_topology,
    topology_snapshot,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.context import current_tenant_id
from bms_core.core.exceptions import CatalogError
from bms_core.db.keys import build_platform_db_key
from bms_core.servicecall.base import DEFAULT_BASE_URL_TEMPLATE, service_base_url
from bms_core.services.module_registry import register_domain_services, reset_domain_services

pytestmark = pytest.mark.kiwi_id(2366)

_TENANT = 7


def _reason(exc: CatalogError) -> str:
    """取异常携带的失败原因（`data.reason`；`data` 为 `object`，测试内显式收窄）。

    Args:
        exc: 抛出的目录异常。

    Returns:
        str: 失败原因标识。
    """
    data = cast("ConcurrentStableDict[str, str]", exc.data)
    return data["reason"]


@pytest.fixture(autouse=True)
def _isolate_topology() -> Iterator[None]:
    """每例复位快照、解析器与域映射，并登记两个域（`auth` / `org`）。

    Yields:
        None: 用例运行期。
    """
    reset_topology_snapshots()
    reset_topology_resolver()
    reset_instance_context()
    reset_domain_services()
    register_domain_services(ConcurrentStableFrozenDict({"auth": "identity", "org": "mdm"}))
    yield
    reset_topology_snapshots()
    reset_topology_resolver()
    reset_instance_context()
    reset_domain_services()


def _snapshot(tenant_id: int, version: int, entries: ConcurrentStableDict[str, TopologyEntry]) -> TopologySnapshot:
    """构造快照。

    Args:
        tenant_id: 租户主键。
        version: 版本号。
        entries: 域 → 条目。

    Returns:
        TopologySnapshot: 快照。
    """
    return TopologySnapshot(
        tenant_id=tenant_id,
        version=version,
        entries=ConcurrentStableFrozenDict(entries.to_list()),
    )


def _default(version: int = 1) -> TopologySnapshot:
    """默认拓扑快照（两域均启用，单元取承载服务键）。

    Args:
        version: 版本号。

    Returns:
        TopologySnapshot: 默认拓扑快照。
    """
    return _snapshot(
        DEFAULT_TOPOLOGY_TENANT,
        version,
        ConcurrentStableDict(
            {
                "auth": TopologyEntry(unit_key="identity"),
                "org": TopologyEntry(unit_key="mdm"),
            }
        ),
    )


def test_not_loaded_reports_reason() -> None:
    """快照未装载：抛 `CatalogError` 且 `reason=not_loaded`（拒启级语义）。"""
    with pytest.raises(CatalogError) as captured:
        resolve_for(_TENANT, "auth")
    assert captured.value.data == {"reason": "not_loaded", "tenant_id": _TENANT, "domain": "auth"}


def test_tenant_without_snapshot_falls_back_to_default() -> None:
    """租户无记录：整体回退默认拓扑（不逐域合并）；阶段 A 单元 = 承载服务键。

    `mode` 由 07C `02_02` 判定：本实例未登记承载集合（视为全组）且该域不由本服务承载 → `colocated`。
    """
    register_topology_snapshot(_default())
    target = resolve_for(_TENANT, "auth")
    assert target.unit_key == "identity"
    assert target.service_key == "identity"
    assert target.mode == CapabilityMode.COLOCATED


def test_tenant_snapshot_overrides_default() -> None:
    """租户有自己的版本：解析取租户版本，不合并默认。"""
    register_topology_snapshot(_default())
    register_topology_snapshot(_snapshot(_TENANT, 3, ConcurrentStableDict({"auth": TopologyEntry(unit_key="core")})))
    assert resolve_for(_TENANT, "auth").unit_key == "core"
    with pytest.raises(CatalogError) as captured:
        resolve_for(_TENANT, "org")
    assert _reason(captured.value) == "not_registered"


def test_domain_not_registered_in_topology() -> None:
    """域不在快照内：`reason=not_registered`。"""
    register_topology_snapshot(_default())
    with pytest.raises(CatalogError, match="未在当前租户的部署拓扑登记"):
        resolve_for(_TENANT, "file")


def test_domain_disabled_is_business_state() -> None:
    """域 `disabled`：`reason=not_enabled`（业务态，不是配置缺失）。"""
    register_topology_snapshot(
        _snapshot(
            DEFAULT_TOPOLOGY_TENANT,
            1,
            ConcurrentStableDict(
                {
                    "auth": TopologyEntry(unit_key="identity", status="disabled"),
                    "org": TopologyEntry(unit_key="mdm"),
                }
            ),
        )
    )
    with pytest.raises(CatalogError) as captured:
        resolve_for(_TENANT, "auth")
    assert _reason(captured.value) == "not_enabled"


def test_domain_without_layout_service_is_rejected() -> None:
    """拓扑有记录但域布局未登记承载服务：同样按 `not_registered` 拒绝（不拼不可达地址）。"""
    register_topology_snapshot(_snapshot(_TENANT, 1, ConcurrentStableDict({"ghost": TopologyEntry(unit_key="core")})))
    with pytest.raises(CatalogError, match="未登记承载服务"):
        resolve_for(_TENANT, "ghost")


def test_db_key_and_base_url_derive_from_unit() -> None:
    """库键与基址由部署单元派生：`db_keys=[platform_{unit}]`（租户库键由调用方派生）。"""
    register_topology_snapshot(_snapshot(_TENANT, 1, ConcurrentStableDict({"auth": TopologyEntry(unit_key="core")})))
    target = resolve_for(_TENANT, "auth")
    assert list(target.db_keys) == [build_platform_db_key("core")]
    assert target.base_url == service_base_url("core", DEFAULT_BASE_URL_TEMPLATE)


def test_new_version_becomes_visible() -> None:
    """同租户新版本写入后解析返回新结果（不残留旧快照）。"""
    register_topology_snapshot(_snapshot(_TENANT, 1, ConcurrentStableDict({"auth": TopologyEntry(unit_key="core")})))
    assert resolve_for(_TENANT, "auth").unit_key == "core"
    register_topology_snapshot(
        _snapshot(_TENANT, 2, ConcurrentStableDict({"auth": TopologyEntry(unit_key="dom-auth")}))
    )
    assert resolve_for(_TENANT, "auth").unit_key == "dom-auth"
    updated = topology_snapshot(_TENANT)
    assert updated is not None
    assert updated.version == 2


def test_snapshot_limit_evicts_oldest() -> None:
    """快照超容量淘汰最早登记（防止进程内无限增长）。"""
    for tenant in range(TOPOLOGY_SNAPSHOT_LIMIT + 1):
        register_topology_snapshot(_snapshot(tenant + 1, 1, ConcurrentStableDict({"auth": TopologyEntry("core")})))
    assert topology_snapshot(1) is None
    assert topology_snapshot(TOPOLOGY_SNAPSHOT_LIMIT + 1) is not None


def test_default_snapshot_lookup_returns_none_without_data() -> None:
    """默认拓扑本身无快照时返回 None（区别于「租户回退」分支）。"""
    assert topology_snapshot(DEFAULT_TOPOLOGY_TENANT) is None


def test_resolver_uses_request_tenant_context() -> None:
    """协议入口：租户取 `current_tenant_id` 上下文；上下文缺失按默认拓扑。"""
    register_topology_snapshot(_default())
    register_topology_snapshot(_snapshot(9, 1, ConcurrentStableDict({"auth": TopologyEntry(unit_key="core")})))
    resolver = TenantTopologyResolver()
    token = current_tenant_id.set("9")
    try:
        assert resolver.resolve("auth").unit_key == "core"
    finally:
        current_tenant_id.reset(token)
    assert resolver.resolve("auth").unit_key == "identity"


def test_resolver_tolerates_illegal_tenant_context() -> None:
    """上下文值非法（非数字）：按默认拓扑解析，不抛类型错误。"""
    register_topology_snapshot(_default())
    token = current_tenant_id.set("not-a-number")
    try:
        assert TenantTopologyResolver.tenant_id() == DEFAULT_TOPOLOGY_TENANT
        assert TenantTopologyResolver().resolve("auth").unit_key == "identity"
    finally:
        current_tenant_id.reset(token)


def test_registered_resolver_replaces_transitional_default() -> None:
    """协议替换：登记后 `resolve_topology()` 返回本实现；未登记仍是 07B 过渡实现。"""
    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)
    register_topology_resolver(TenantTopologyResolver())
    assert isinstance(resolve_topology(), TenantTopologyResolver)


def test_reset_clears_snapshots() -> None:
    """复位后快照清空（测试隔离与热重启语义）。"""
    register_topology_snapshot(_default())
    reset_topology_snapshots()
    assert topology_snapshot(DEFAULT_TOPOLOGY_TENANT) is None


def test_transitional_resolver_rejects_domain_without_service() -> None:
    """07B 过渡实现：域布局未登记承载服务时抛 `CatalogError`（未换代前也不会拼错地址）。"""
    reset_domain_services()
    with pytest.raises(CatalogError, match="业务域未在部署拓扑登记"):
        DomainLayoutTopologyResolver().resolve("auth")


def test_transitional_resolver_keeps_domain_as_unit() -> None:
    """07B 过渡实现：`unit_key` 取业务域、库键为空集（换代前的等价语义，不得漂移）。"""
    target = DomainLayoutTopologyResolver().resolve("auth")
    assert target.unit_key == "auth"
    assert target.service_key == "identity"
    assert list(target.db_keys) == []
