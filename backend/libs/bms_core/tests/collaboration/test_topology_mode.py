"""部署模式三态判定（07C `02_02`；Kiwi 2367）。

覆盖详细设计 §6 用例 1~7：承载服务 → `local`、集合内他域 → `colocated`、集合外 → `remote`、
显式空集合、服务键为空、默认拓扑未装载、集合含未登记单元。
"""

from collections.abc import Iterator

import pytest

from bms_core.collaboration import (
    DEFAULT_TOPOLOGY_TENANT,
    CapabilityMode,
    TopologyEntry,
    TopologySnapshot,
    instance_units,
    register_instance_context,
    register_topology_snapshot,
    reset_instance_context,
    reset_topology_resolver,
    reset_topology_snapshots,
    resolve_for,
)
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.exceptions import CatalogError
from bms_core.db.keys import build_platform_db_key
from bms_core.services.module_registry import register_domain_services, reset_domain_services

pytestmark = pytest.mark.kiwi_id(2367)

_TENANT = 7


def _snapshot(tenant_id: int, entries: ConcurrentStableDict[str, TopologyEntry]) -> TopologySnapshot:
    """构造快照（版本恒 1）。

    Args:
        tenant_id: 租户主键。
        entries: 域 → 条目。

    Returns:
        TopologySnapshot: 快照。
    """
    return TopologySnapshot(tenant_id=tenant_id, version=1, entries=ConcurrentStableFrozenDict(entries.to_list()))


def _merged() -> TopologySnapshot:
    """合并部署（阶段 A）：单元 = 该域承载服务键。

    Returns:
        TopologySnapshot: 默认拓扑快照。
    """
    return _snapshot(
        DEFAULT_TOPOLOGY_TENANT,
        ConcurrentStableDict({"auth": TopologyEntry(unit_key="identity"), "org": TopologyEntry(unit_key="mdm")}),
    )


def _split(tenant_id: int = DEFAULT_TOPOLOGY_TENANT) -> TopologySnapshot:
    """拆分部署（阶段 B 形态）：单元与承载服务分离。

    Args:
        tenant_id: 租户主键。

    Returns:
        TopologySnapshot: 拆分拓扑快照。
    """
    return _snapshot(
        tenant_id,
        ConcurrentStableDict({"auth": TopologyEntry(unit_key="core"), "org": TopologyEntry(unit_key="grp-ops")}),
    )


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """每例复位快照、解析器、本实例身份与域映射，并登记两个域（`auth` / `org`）。

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


def test_carried_domain_is_local_and_peer_is_colocated() -> None:
    """用例 1：阶段 A 未声明集合——自域 `local`、他域 `colocated`，不出现 `remote`。"""
    register_topology_snapshot(_merged())
    register_instance_context("identity", None)

    auth = resolve_for(_TENANT, "auth")
    org = resolve_for(_TENANT, "org")

    assert auth.mode == CapabilityMode.LOCAL
    assert auth.unit_key == "identity"
    assert org.mode == CapabilityMode.COLOCATED
    assert org.service_key == "mdm"


def test_declared_unit_without_carrier_is_colocated() -> None:
    """用例 2：单元 ∈ 本实例集合、但该域由别的服务承载 → `colocated`。"""
    register_topology_snapshot(_split())
    register_instance_context("billing", ConcurrentStableList(("core", "grp-ops")))

    auth = resolve_for(_TENANT, "auth")

    assert auth.mode == CapabilityMode.COLOCATED
    assert auth.unit_key == "core"


def test_unit_outside_declared_units_is_remote() -> None:
    """用例 3：单元 ∉ 本实例集合 → `remote`（跨实例组）。"""
    register_topology_snapshot(_split())
    register_instance_context("billing", ConcurrentStableList(("grp-ops",)))

    auth = resolve_for(_TENANT, "auth")
    org = resolve_for(_TENANT, "org")

    assert auth.mode == CapabilityMode.REMOTE
    assert org.mode == CapabilityMode.COLOCATED


def test_empty_declared_units_makes_peers_remote() -> None:
    """用例 4：显式空集合——不承载任何单元，他域全 `remote`（自域仍 `local`，判据优先看承载服务）。"""
    register_topology_snapshot(_merged())
    register_instance_context("identity", ConcurrentStableList())

    assert resolve_for(_TENANT, "auth").mode == CapabilityMode.LOCAL
    assert resolve_for(_TENANT, "org").mode == CapabilityMode.REMOTE
    assert list(instance_units()) == []


def test_blank_service_key_never_reports_local() -> None:
    """用例 5：服务键为空（无从判断同进程）→ 不产生 `local`，退化为 `colocated`。"""
    register_topology_snapshot(_merged())
    register_instance_context("", None)

    assert resolve_for(_TENANT, "auth").mode == CapabilityMode.COLOCATED


def test_missing_default_snapshot_yields_no_units() -> None:
    """用例 6：默认拓扑未装载——承载集合为空，解析报 `not_loaded`（与过渡实现等价，不误报同组）。"""
    register_instance_context("identity", None)

    assert list(instance_units()) == []
    with pytest.raises(CatalogError, match="部署拓扑未装载"):
        resolve_for(_TENANT, "auth")


def test_declared_unit_must_exist_in_default_topology() -> None:
    """用例 7：集合含未登记单元 → `CatalogError`（配置漂移，启动期拒启语义）。"""
    register_topology_snapshot(_merged())

    with pytest.raises(CatalogError, match="未在默认拓扑登记") as captured:
        register_instance_context("identity", ConcurrentStableList(("identity", "ghost")))
    assert captured.value.data == {"reason": "unit_not_registered", "units": ["ghost"]}


def test_register_returns_effective_units() -> None:
    """登记返回生效集合：未声明取默认拓扑全部单元，声明则原样返回。"""
    register_topology_snapshot(_merged())

    assert list(register_instance_context("identity", None)) == ["identity", "mdm"]
    assert list(register_instance_context("identity", ConcurrentStableList(("mdm",)))) == ["mdm"]


def test_declared_units_skip_validation_without_snapshot() -> None:
    """默认拓扑未装载时无法校验，声明集合原样生效（降级路径不误拒启）。"""
    assert list(register_instance_context("identity", ConcurrentStableList(("core",)))) == ["core"]


def test_phase_a_keeps_db_key_and_base_url_from_unit() -> None:
    """阶段 A 等价性：单元 = 承载服务键，库键与基址与改造前一致。"""
    register_topology_snapshot(_merged())
    register_instance_context("identity", None)

    target = resolve_for(_TENANT, "org")

    assert list(target.db_keys) == [build_platform_db_key("mdm")]
    assert target.base_url == "http://mdm:8000"
