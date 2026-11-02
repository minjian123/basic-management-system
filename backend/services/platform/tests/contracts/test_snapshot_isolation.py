"""会话级装配快照的视图族隔离（守卫契约套件 `567` 的快照夹具）。

背景：会话级夹具先于用例函数级隔离夹具执行。同一 worker 内先前的声明注册 / 投影类用例会把
「无来源（`source` 为空）」的种子记录留在进程里；装配应用再按清单装载同键记录（`source` =
清单 `product_key`）时，`register_seed_records` 的同键异值判定会拒绝，使整份快照及其所有用例
error（曾以 `test_class_impl_contract[...]` 批量 error 的形式在推送预检中暴露）。`build_snapshot()`
因此在装配前复位视图族。
"""

from dataclasses import replace

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import (
    register_seed_records,
    reset_seed_records,
    seed_catalog_view,
)
from tests.contracts.support import build_snapshot

pytestmark = pytest.mark.kiwi_id(567)


def test_build_snapshot_resets_polluted_seed_view() -> None:
    """残留「无来源」种子不阻断快照装配。"""
    load_product_manifests(ConcurrentStableList())
    seeded = seed_catalog_view()
    assert seeded, "本仓清单应至少声明一个种子"
    target = seeded[0]

    # 模拟投影类用例的残留：同一份声明、`source` 为空（注册表快照行不含来源列）
    reset_seed_records()
    register_seed_records(ConcurrentStableFrozenList((replace(target, source=""),)))

    assert build_snapshot()


def test_build_snapshot_restores_manifest_source() -> None:
    """复位后装回的种子与清单同声明同来源（来源不被抹空、记录不重复）。"""
    load_product_manifests(ConcurrentStableList())
    target = seed_catalog_view()[0]

    build_snapshot()

    matched = [record for record in seed_catalog_view() if record.name == target.name]
    assert len(matched) == 1
    assert matched[0] == target
    assert matched[0].source == target.source
