"""导出脱敏工具用例（Kiwi 2225）：`mask_rows` 按「列名 → 策略」逐行逐列掩码，未声明列原样。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.masking.default import DefaultMasker
from bms_core.permission.null import NullPermissionChecker
from bms_core.transfer.masking import mask_rows


def _rows() -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """构造两行导出数据（含敏感列与普通列）。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 导出行。
    """
    return ConcurrentStableList(
        [
            ConcurrentStableDict({"name": "甲", "phone": "13800001111", "dept": "研发"}),
            ConcurrentStableDict({"name": "乙", "phone": "13900002222", "dept": "测试"}),
        ]
    )


@pytest.mark.kiwi_id(2225)
def test_mask_rows_masks_declared_columns_only() -> None:
    """声明列按策略掩码、未声明列原样；返回新序列且不改入参。"""
    rows = _rows()
    masked = mask_rows(
        rows,
        ConcurrentStableDict({"phone": "phone"}),
        DefaultMasker(checker=NullPermissionChecker()),
    )
    assert [str(row["phone"]) for row in masked] == ["138****1111", "139****2222"]
    assert [str(row["name"]) for row in masked] == ["甲", "乙"]
    assert [str(row["dept"]) for row in masked] == ["研发", "测试"]
    assert rows[0]["phone"] == "13800001111"


@pytest.mark.kiwi_id(2225)
def test_mask_rows_empty_fields_returns_input() -> None:
    """空映射原样返回入参（不构造新序列）。"""
    rows = _rows()
    assert mask_rows(rows, ConcurrentStableDict(), DefaultMasker(checker=NullPermissionChecker())) is rows
