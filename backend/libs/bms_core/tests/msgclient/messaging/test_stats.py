"""03-6 用例：客户端计数器（Kiwi 2510）。

覆盖要点：无标签时键就是指标名，带标签时是 `名{键=值}`；快照是不可变副本（取走后不受后续自增影响）。
"""

from __future__ import annotations

import pytest

from bms_core.msgclient.messaging import ClientStats

pytestmark = pytest.mark.kiwi_id(2510)


def test_stats_counts_with_and_without_labels() -> None:
    """计数器：无标签键是指标名，带标签键是「名{键=值}」。"""
    stats = ClientStats()
    stats.incr("dedup_hits_total")
    stats.incr("dedup_hits_total")
    stats.incr("requests_total", op="publish")
    snapshot = stats.snapshot()
    assert snapshot.get("dedup_hits_total") == 2
    assert snapshot.get("requests_total{op=publish}") == 1


def test_stats_snapshot_is_a_copy() -> None:
    """快照取走后继续自增：旧快照不变（避免排障时数字自己变）。"""
    stats = ClientStats()
    stats.incr("requests_total", op="publish")
    snapshot = stats.snapshot()
    stats.incr("requests_total", op="publish")
    assert snapshot.get("requests_total{op=publish}") == 1
    assert stats.snapshot().get("requests_total{op=publish}") == 2
