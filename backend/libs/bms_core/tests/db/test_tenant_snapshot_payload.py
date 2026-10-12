"""租户注册快照载荷用例（`bms_core/db/tenant_registry.py`）：载荷往返、非法 `code` 与主键归一。"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.tenant_registry import TenantSnapshot, _tenant_id  # pyright: ignore[reportPrivateUsage]


def test_snapshot_payload_roundtrip_with_and_without_version() -> None:
    """载荷往返：不带版本戳时不写 `version` 键；带版本戳时原样落键。"""
    snapshot = TenantSnapshot(code="demo", name="演示租户", tenant_id=7)
    payload = snapshot.to_payload()
    assert "version" not in payload
    restored = TenantSnapshot.from_payload(payload)
    assert restored.code == "demo"
    assert restored.tenant_id == 7

    stamped = snapshot.to_payload(version=3)
    assert stamped["version"] == 3


@pytest.mark.parametrize("code", [1, "", None])
def test_snapshot_from_payload_rejects_bad_code(code: object) -> None:
    """`code` 缺失 / 非字符串 / 空串 → `KeyError`。"""
    with pytest.raises(KeyError):
        TenantSnapshot.from_payload(ConcurrentStableDict({"code": code}))


def test_snapshot_from_payload_requires_code_field() -> None:
    """`code` 字段完全缺失 → `KeyError`。"""
    with pytest.raises(KeyError):
        TenantSnapshot.from_payload(ConcurrentStableDict())


def test_tenant_id_normalization() -> None:
    """主键归一：布尔 / 非数字字符串 / 缺失 → None；整数与十进制字符串均接受。"""
    assert _tenant_id(True) is None
    assert _tenant_id(7) == 7
    assert _tenant_id("7") == 7
    assert _tenant_id("abc") is None
    assert _tenant_id(None) is None
