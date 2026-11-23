"""进程级拓扑状态的留存与恢复（13_09；Kiwi 2547）。

覆盖 `topology_state()` / `restore_topology_state()` 的整份留存与还原语义：多租户 × 多版本
快照、各租户当前生效版本、实例上下文的两种形态（未声明 / 已声明）。这是测试隔离夹具
`isolated_topology` 的底层能力——域归属判定读的就是这些进程级全局，用例改写后不恢复会让
同 worker 的后继用例报「业务域未在本实例启用」（403）。
"""

from collections.abc import Iterator

import pytest

from bms_core.collaboration import (
    DEFAULT_TOPOLOGY_TENANT,
    TopologyEntry,
    TopologySnapshot,
    TopologyState,
    instance_units,
    register_instance_context,
    register_topology_snapshot,
    reset_instance_context,
    reset_topology_snapshots,
    restore_topology_state,
    topology_snapshot,
    topology_state,
)
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)

pytestmark = pytest.mark.kiwi_id(2547)


def _entries(*pairs: tuple[str, str]) -> ConcurrentStableFrozenDict[str, TopologyEntry]:
    """构造「域 → 条目」映射。

    Args:
        *pairs: `(域, 部署单元)` 对。

    Returns:
        ConcurrentStableFrozenDict[str, TopologyEntry]: 冻结映射（快照字段类型）。
    """
    entries: ConcurrentStableDict[str, TopologyEntry] = ConcurrentStableDict()
    for domain, unit_key in pairs:
        entries.set(domain, TopologyEntry(unit_key=unit_key))
    return ConcurrentStableFrozenDict(entries.to_list())


def _snapshot(tenant_id: int, version: int, *pairs: tuple[str, str]) -> TopologySnapshot:
    """构造快照。

    Args:
        tenant_id: 租户主键（`0` 为默认拓扑）。
        version: 拓扑版本。
        *pairs: `(域, 部署单元)` 对。

    Returns:
        TopologySnapshot: 快照。
    """
    return TopologySnapshot(tenant_id=tenant_id, version=version, entries=_entries(*pairs))


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    """每例前后清空拓扑进程态与实例上下文（本文件只测留存 / 恢复，不需基线）。

    Yields:
        None: 用例运行期。
    """
    reset_topology_snapshots()
    reset_instance_context()
    yield
    reset_topology_snapshots()
    reset_instance_context()


def test_defaults_are_empty() -> None:
    """无参构造：四个字段分别为空集 / 空映射 / 空串 / `None`（不留共享可变默认值）。"""
    state = TopologyState()

    assert list(state.snapshots) == []
    assert state.current_versions.to_list() == []
    assert state.instance_service == ""
    assert state.instance_units is None


def test_state_keeps_all_snapshots_and_current_versions() -> None:
    """留存：同租户历史版本同租户多版本共存，各租户当前版本取最后登记。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 1, ("mdm", "mdm")))
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 2, ("core", "core")))
    register_topology_snapshot(_snapshot(11, 1, ("mdm", "grp-ops")))

    state = topology_state()

    assert sorted((snapshot.tenant_id, snapshot.version) for snapshot in state.snapshots) == [(0, 1), (0, 2), (11, 1)]
    assert sorted(state.current_versions.to_list()) == [(0, 2), (11, 1)]


def test_restore_undoes_overwrite_and_addition() -> None:
    """恢复：覆盖当前版本与新增租户都被撤回，回到留存时的快照集合。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 1, ("mdm", "mdm")))
    state = topology_state()

    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 2, ("core", "core")))
    register_topology_snapshot(_snapshot(12, 1, ("mdm", "grp-ops")))
    restore_topology_state(state)

    current = topology_snapshot(DEFAULT_TOPOLOGY_TENANT)
    assert current is not None
    assert current.version == 1
    assert sorted(current.entries.keys()) == ["mdm"]
    # 租户 12 的登记被撤回：解析回退到默认拓扑（不是自己的快照）
    fallback = topology_snapshot(12)
    assert fallback is not None
    assert fallback.tenant_id == DEFAULT_TOPOLOGY_TENANT


def test_restore_clears_when_baseline_empty() -> None:
    """恢复：留存时无任何快照 → 用例内登记的租户被清空（不留残值）。"""
    state = topology_state()

    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 1, ("mdm", "mdm")))
    assert topology_snapshot(DEFAULT_TOPOLOGY_TENANT) is not None

    restore_topology_state(state)

    assert topology_snapshot(DEFAULT_TOPOLOGY_TENANT) is None


def test_restore_keeps_undeclared_instance_context() -> None:
    """实例上下文未声明（`None`）：恢复后仍取默认拓扑全部单元，而不是空集。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 1, ("mdm", "mdm"), ("core", "grp-core")))
    state = topology_state()

    register_instance_context("platform", ConcurrentStableList(("grp-core",)))
    assert list(instance_units()) == ["grp-core"]

    restore_topology_state(state)

    assert list(instance_units()) == ["mdm", "grp-core"]


def test_restore_keeps_declared_instance_context() -> None:
    """实例上下文已声明：恢复后仍是原集合（复位成「未声明」会改变解析模式）。"""
    register_topology_snapshot(_snapshot(DEFAULT_TOPOLOGY_TENANT, 1, ("mdm", "mdm")))
    register_instance_context("platform", ConcurrentStableList(("mdm",)))
    state = topology_state()

    reset_instance_context()
    restore_topology_state(state)

    assert list(instance_units()) == ["mdm"]
