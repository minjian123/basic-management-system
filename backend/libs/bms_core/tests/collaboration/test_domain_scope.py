"""业务域归属内核（07C `04_03`；Kiwi 编号归 `05_01` 统一登记）。

覆盖详细设计 §5 用例 5~7、9~10、13 的内核部分：域段解析（含 `unknown` 兜底）、本实例承载域
（拓扑 ∩ 承载单元）、令牌域声明解析、入站域归属判定三道拒法（未启用 / 未声明 / 声明不符）与
审计表归属。

拓扑以默认拓扑快照为准：`[topology].units` 只声明单元，域由拓扑解析——配置侧不另立域清单。
"""

from collections.abc import Iterator

import pytest

from bms_core.collaboration.domain_scope import (
    DOMAIN_CLAIM,
    UNKNOWN_DOMAIN,
    check_domain_attribution,
    claimed_domains,
    domain_of_path,
    domain_of_table,
    domains_of_units,
    enabled_domains,
    instance_domains,
)
from bms_core.collaboration.topology import (
    DEFAULT_TOPOLOGY_TENANT,
    TopologyEntry,
    TopologySnapshot,
    register_instance_context,
    register_topology_snapshot,
    reset_instance_context,
    reset_topology_snapshots,
)
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import PermissionError
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)

_CAPABILITY_ROLE = "platform.role.query"
"""能力名（提供方域 `role`）。"""

_CAPABILITY_USER = "platform.user.query"
"""能力名（提供方域 `user`）。"""


def _snapshot(entries: ConcurrentStableDict[str, TopologyEntry]) -> TopologySnapshot:
    """构造默认拓扑快照（版本恒 1）。

    Args:
        entries: 域 → 条目。

    Returns:
        TopologySnapshot: 快照。
    """
    return TopologySnapshot(
        tenant_id=DEFAULT_TOPOLOGY_TENANT,
        version=1,
        entries=ConcurrentStableFrozenDict(entries.to_list()),
    )


def _split_topology() -> TopologySnapshot:
    """拆分拓扑：`role` 在 `platform` 单元、`user` 在 `userops` 单元（`menu_form` 停用）。

    Returns:
        TopologySnapshot: 默认拓扑快照。
    """
    return _snapshot(
        ConcurrentStableDict(
            {
                "role": TopologyEntry(unit_key="platform"),
                "user": TopologyEntry(unit_key="userops"),
                "menu_form": TopologyEntry(unit_key="platform", status="disabled"),
            }
        )
    )


@pytest.fixture(autouse=True)
def _isolation() -> Iterator[None]:
    """用例前后复位进程级登记（域映射 / 能力目录 / 拓扑 / 本实例身份）。"""
    reset_domain_services()
    reset_collaboration_records()
    reset_topology_snapshots()
    reset_instance_context()
    yield
    reset_domain_services()
    reset_collaboration_records()
    reset_topology_snapshots()
    reset_instance_context()


def _register_domains() -> None:
    """登记三个业务域与其承载服务（域段解析与能力域归属的来源）。"""
    register_domain_services(
        ConcurrentStableFrozenDict({"role": "platform", "user": "platform", "menu_form": "platform"})
    )


def _register_capabilities() -> None:
    """登记两条能力（提供方域 `role` / `user`）。"""
    register_collaboration_records(
        (
            CollaborationRecord(
                name=_CAPABILITY_ROLE,
                domain="role",
                kind="read",
                contract_version="0.1.0",
                path="/api/v1/role/list",
                product_key="platform",
            ),
            CollaborationRecord(
                name=_CAPABILITY_USER,
                domain="user",
                kind="read",
                contract_version="0.1.0",
                path="/api/v1/user/list",
                product_key="platform",
            ),
        )
    )


def test_domain_of_path_maps_registered_domain() -> None:
    """内部路径取已登记域段；未登记域段与外部路径一律 `unknown`。"""
    _register_domains()

    assert domain_of_path("/api/v1/role/list") == "role"
    assert domain_of_path("/api/v1/role") == "role"
    assert domain_of_path("/api/v1/platform/internal/tenant-topologies") == UNKNOWN_DOMAIN, "服务级内部面不是域"
    assert domain_of_path("/api/org/v1/role/list") == UNKNOWN_DOMAIN, "外部命名空间路径非内部形态"
    assert domain_of_path("/health/live") == UNKNOWN_DOMAIN
    assert domain_of_path("") == UNKNOWN_DOMAIN


def test_claimed_domains_parses_claim_forms() -> None:
    """域声明解析：空格分隔串 / 序列 / 去重保序；缺失与非法形态为空集。"""
    assert list(claimed_domains("role user")) == ["role", "user"]
    assert list(claimed_domains(" role  role user ")) == ["role", "user"]
    assert list(claimed_domains(("role", "user"))) == ["role", "user"]
    assert list(claimed_domains(None)) == []
    assert list(claimed_domains(123)) == []
    assert DOMAIN_CLAIM == "domains"


def test_instance_domains_are_topology_intersect_units() -> None:
    """本实例承载域 = 默认拓扑启用域 ∩ 本实例承载单元（停用域不入）。"""
    register_topology_snapshot(_split_topology())
    register_instance_context("platform", ConcurrentStableFrozenList(("platform",)))

    assert list(instance_domains()) == ["role"], "user 在 userops 单元、menu_form 已停用"
    assert list(domains_of_units(ConcurrentStableFrozenList(("userops",)))) == ["user"]
    assert list(domains_of_units(ConcurrentStableFrozenList())) == []


def test_instance_domains_empty_without_topology() -> None:
    """拓扑未装载：承载域为空集（调用方按「无法判定」处理，入站不按空集拒）。"""
    assert list(instance_domains()) == []


def test_enabled_domains_falls_back_to_registry_without_topology() -> None:
    """平台启用域：有拓扑取启用行；无拓扑回落域登记面。"""
    _register_domains()
    assert list(enabled_domains()) == ["role", "user", "menu_form"]

    register_topology_snapshot(_split_topology())
    assert list(enabled_domains()) == ["role", "user"], "停用域不计入边缘承载域"


def test_attribution_passes_when_domain_enabled_and_claimed() -> None:
    """域在本实例启用且调用方已声明：判定通过并返回提供方域。"""
    _register_domains()
    _register_capabilities()
    register_topology_snapshot(_split_topology())
    register_instance_context("platform", ConcurrentStableFrozenList(("platform",)))

    assert check_domain_attribution(_CAPABILITY_ROLE, claimed_domains("role user"), consumer="mdm") == "role"


def test_attribution_rejects_domain_not_enabled_here() -> None:
    """本实例不承载该域（域在别的单元）：拒绝，错误含域 / 能力 / 消费方。"""
    _register_domains()
    _register_capabilities()
    register_topology_snapshot(_split_topology())
    register_instance_context("platform", ConcurrentStableFrozenList(("platform",)))

    with pytest.raises(PermissionError, match="业务域未在本实例启用：user"):
        check_domain_attribution(_CAPABILITY_USER, claimed_domains("user"), consumer="mdm")


def test_attribution_rejects_missing_claim() -> None:
    """域声明缺失（旧版签发）：拒绝，并提示升级签发侧（不静默放行）。"""
    _register_domains()
    _register_capabilities()

    with pytest.raises(PermissionError, match="缺少业务域声明"):
        check_domain_attribution(_CAPABILITY_ROLE, claimed_domains(""), consumer="mdm")


def test_attribution_rejects_domain_mismatch() -> None:
    """声明不含被调能力所属域：拒绝，错误列出已声明域（越界可定位）。"""
    _register_domains()
    _register_capabilities()

    with pytest.raises(PermissionError, match="调用方未声明业务域：role"):
        check_domain_attribution(_CAPABILITY_ROLE, claimed_domains("user"), consumer="mdm")


def test_attribution_skips_enablement_check_without_topology() -> None:
    """拓扑未装载：只判声明（不因承载域为空集误拒）。"""
    _register_domains()
    _register_capabilities()

    assert check_domain_attribution(_CAPABILITY_ROLE, claimed_domains("role"), consumer="mdm") == "role"


def test_domain_of_table_uses_table_ownership() -> None:
    """审计域标注：表 → 归属域；未登记表回落 `unknown`。"""
    assert domain_of_table("sys_role") == "role"
    assert domain_of_table("sys_table_ownership") == "platform_registry"
    assert domain_of_table("no_such_table_xyz") == UNKNOWN_DOMAIN


def test_module_exports_domain_claim_contract() -> None:
    """域声明键与令牌契约同源（单一来源，不各写一份常量）。"""
    from bms_core.oauth.token import SERVICE_DOMAIN_CLAIM, SERVICE_DOMAIN_SEPARATOR

    assert DOMAIN_CLAIM == SERVICE_DOMAIN_CLAIM
    assert claimed_domains("role" + SERVICE_DOMAIN_SEPARATOR + "user") == ConcurrentStableList(("role", "user"))
