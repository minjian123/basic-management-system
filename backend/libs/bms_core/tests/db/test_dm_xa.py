"""达梦 XA 自定义方言单元用例（需求 05-5；Kiwi 2245）：注册可解析 / 方言归一 / 同步方言集。"""

import pytest
from sqlalchemy.engine import make_url

from bms_core.db.dialects.dm_xa import DMXADialect
from bms_core.db.engine import _normalize_dialect_url  # pyright: ignore[reportPrivateUsage]
from bms_core.db.sync import SYNC_ONLY_DIALECTS, is_sync_only_url

pytestmark = [pytest.mark.kiwi_id(2245)]


def test_dmxa_dialect_registered() -> None:
    """`dmxa+dmPython` 经方言注册表解析为自定义 `DMXADialect`。"""
    assert make_url("dmxa+dmPython://user:pwd@host:5236").get_dialect() is DMXADialect


def test_normalize_dm_url_to_dmxa() -> None:
    """达梦连接串方言归一：`dm` → `dmxa`；已是 `dmxa` 保持不变；非达梦不动。"""
    assert _normalize_dialect_url("dm+dmPython://user:pwd@host:5236").startswith("dmxa+dmPython://")
    assert _normalize_dialect_url("dmxa+dmPython://user:pwd@host:5236").startswith("dmxa+dmPython://")
    assert _normalize_dialect_url("mysql+aiomysql://user:pwd@host:3306/db").startswith("mysql+aiomysql://")


def test_dmxa_is_sync_only() -> None:
    """`dmxa` 属同步方言（无异步驱动）：`create` 抛错、`create_sync` 可用。"""
    assert "dmxa" in SYNC_ONLY_DIALECTS
    assert is_sync_only_url("dmxa+dmPython://user:pwd@host:5236") is True
