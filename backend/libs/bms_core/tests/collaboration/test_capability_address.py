"""第二段解析地址进入调用链（07C `02_02`；Kiwi 2367）。

覆盖详细设计 §6 用例 8~10 与 17~18：显式基址优先、非法基址拒绝、能力请求携带解析地址、
两套拓扑下同一能力取址不同且各自正确、跨租户不串。
"""

from collections.abc import Iterator

import pytest

from bms_core.collaboration import (
    DEFAULT_TOPOLOGY_TENANT,
    CapabilityEndpoint,
    CapabilityMode,
    CapabilityTarget,
    TopologyEntry,
    TopologySnapshot,
    build_capability_request,
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
    ConcurrentStableFrozenList,
)
from bms_core.core.exceptions import ParamError
from bms_core.servicecall.base import ServiceRequest, build_service_url, validate_service_request
from bms_core.services.module_registry import register_domain_services, reset_domain_services

pytestmark = pytest.mark.kiwi_id(2367)

PATH = "/api/v1/demo/user-roles"
"""能力访问面路径。"""


def _snapshot(tenant_id: int, unit_key: str) -> TopologySnapshot:
    """构造单域快照（`org` → 给定单元）。

    Args:
        tenant_id: 租户主键。
        unit_key: 部署单元。

    Returns:
        TopologySnapshot: 快照。
    """
    return TopologySnapshot(
        tenant_id=tenant_id,
        version=1,
        entries=ConcurrentStableFrozenDict(ConcurrentStableDict({"org": TopologyEntry(unit_key=unit_key)}).to_list()),
    )


def _endpoint(target: CapabilityTarget) -> CapabilityEndpoint:
    """按解析目标构造能力取用结果。

    Args:
        target: 第二段解析结果。

    Returns:
        CapabilityEndpoint: 取用结果（字段对地址无影响，取最小集）。
    """
    return CapabilityEndpoint(
        name="demo.org.user-roles",
        domain="org",
        kind="read",
        contract_version="0.1.0",
        target=target,
        path=PATH,
    )


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """每例复位拓扑进程态与域映射，并登记一个域（`org` → `mdm`）。

    Yields:
        None: 用例运行期。
    """
    reset_topology_snapshots()
    reset_topology_resolver()
    reset_instance_context()
    reset_domain_services()
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm"}))
    yield
    reset_topology_snapshots()
    reset_topology_resolver()
    reset_instance_context()
    reset_domain_services()


def test_explicit_base_url_wins_and_is_normalized() -> None:
    """用例 8：显式基址优先，尾部斜杠归一（不与模板重复拼 `/`）。"""
    request = ServiceRequest(service="mdm", method="GET", path=PATH, base_url="http://core:9000/")

    assert build_service_url(request) == "http://core:9000/api/v1/demo/user-roles"


def test_request_without_base_url_keeps_template() -> None:
    """未给显式基址：沿用既有模板派生（消费方改造前后行为不变）。"""
    request = ServiceRequest(service="mdm", method="GET", path=PATH)

    assert build_service_url(request) == "http://mdm:8000/api/v1/demo/user-roles"


@pytest.mark.parametrize("base_url", ["mdm:8000", "ftp://core:9000", ""])
def test_illegal_base_url_is_rejected(base_url: str) -> None:
    """用例 9：显式基址非 http(s) → `ParamError`（10001），不发起调用。"""
    request = ServiceRequest(service="identity", method="GET", path=PATH, base_url=base_url)

    with pytest.raises(ParamError, match="显式基址须为 http") as captured:
        validate_service_request(request)
    assert captured.value.code == 10001


def test_capability_request_carries_resolved_base_url() -> None:
    """用例 10：能力请求携带第二段解析出的单元地址；阶段 A 与按服务键派生同值。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, "mdm"))

    endpoint = _endpoint(resolve_for(DEFAULT_TOPOLOGY_TENANT, "org"))
    request = build_capability_request(endpoint, method="GET")

    assert request.service == "mdm"
    assert request.base_url == "http://mdm:8000"
    assert build_service_url(request) == "http://mdm:8000/api/v1/demo/user-roles"


def test_two_topologies_resolve_different_addresses() -> None:
    """用例 17：合并（单元 = 服务键）与拆分（单元 = `core`）两套夹具取址不同且各自正确。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, "mdm"))
    merged = build_capability_request(_endpoint(resolve_for(7, "org")), method="GET")

    reset_topology_snapshots()
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, "core"))
    split = build_capability_request(_endpoint(resolve_for(7, "org")), method="GET")

    assert build_service_url(merged) == "http://mdm:8000/api/v1/demo/user-roles"
    assert build_service_url(split) == "http://core:8000/api/v1/demo/user-roles"
    assert merged.service == split.service == "mdm"


def test_cross_tenant_addresses_do_not_leak() -> None:
    """用例 18：两个租户各自拓扑取到自己的单元与地址（缓存 / 快照不串租户）。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, "mdm"))
    register_topology_snapshot(_snapshot(11, "core"))
    register_topology_snapshot(_snapshot(12, "grp-ops"))

    eleven = resolve_for(11, "org")
    twelve = resolve_for(12, "org")

    assert (eleven.unit_key, eleven.base_url) == ("core", "http://core:8000")
    assert (twelve.unit_key, twelve.base_url) == ("grp-ops", "http://grp-ops:8000")
    assert resolve_for(DEFAULT_TOPOLOGY_TENANT, "org").unit_key == "mdm"


def test_target_base_url_is_the_only_address_source() -> None:
    """解析目标的 `base_url` 与 `db_keys` 同源于单元：地址不依赖消费方自拼。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, "core"))
    register_instance_context("billing", ConcurrentStableFrozenList(("core",)))

    target = resolve_for(7, "org")

    assert target.mode == CapabilityMode.COLOCATED
    assert target.base_url == "http://core:8000"
    assert list(target.db_keys) == ["platform_core"]
