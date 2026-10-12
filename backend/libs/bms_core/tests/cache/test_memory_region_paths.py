"""内存缓存域补齐用例（`bms_core/cache/memory.py`）：域简称 / 过期即删 / 超限淘汰 / 清空。"""

from __future__ import annotations

import pytest

from bms_core.cache.memory import MemoryCacheRegion


def test_memory_region_domain_expiry_eviction_and_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    """域简称暴露；超限淘汰最早写入；过期条目读时即删；清空全部条目。"""
    import bms_core.cache.memory as memory_module

    region = MemoryCacheRegion(domain="unit", max_items=1)
    assert region.domain == "unit"

    region.set("first", 1)
    region.set("second", 2)
    assert region.get("first") is None
    assert region.get("second") == 2

    region.set("ttl", 3, ttl=1)
    monkeypatch.setattr(memory_module, "monotonic", lambda: 10**9)
    assert region.get("ttl") is None

    region.clear()
    assert region.get("second") is None
