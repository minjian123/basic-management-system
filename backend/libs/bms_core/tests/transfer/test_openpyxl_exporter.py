"""导出 xlsx 写出测试：表头 / 列序 / 值兜底 / 分块拼接。"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.transfer import openpyxl_exporter
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.openpyxl_exporter import OpenpyxlExporter
from bms_core.transfer.openpyxl_io import DATA_SHEET_NAME, build_export_workbook

pytestmark = pytest.mark.kiwi_id(2402)

_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (
        ColumnSpec(key="name", title="姓名"),
        ColumnSpec(key="status", title="状态"),
        ColumnSpec(key="phone", title="手机号"),
    )
)


def _rows() -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    return ConcurrentStableList(
        (
            ConcurrentStableDict({"name": "张三", "status": "启用", "phone": "138****0000"}),
            ConcurrentStableDict({"name": "李四", "status": None}),
        )
    )


def test_build_export_workbook_header_and_rows() -> None:
    """表头与列序一致；缺失列为空；行数一致。"""
    data = build_export_workbook(_COLUMNS, _rows())
    workbook = load_workbook(BytesIO(data))
    sheet = workbook[DATA_SHEET_NAME]
    assert [cell.value for cell in sheet[1]] == ["姓名", "状态", "手机号"]
    assert sheet.max_row == 3
    assert [cell.value for cell in sheet[2]] == ["张三", "启用", "138****0000"]
    assert [cell.value for cell in sheet[3]] == ["李四", None, None]


def test_build_export_workbook_value_fallback() -> None:
    """布尔 / 日期 / 日期时间兜底格式化。"""
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
        (
            ConcurrentStableDict(
                {
                    "name": True,
                    "status": datetime(2026, 11, 2, 10, 30, 0),
                    "phone": date(2026, 11, 2),
                }
            ),
        )
    )
    data = build_export_workbook(_COLUMNS, rows)
    sheet = load_workbook(BytesIO(data))[DATA_SHEET_NAME]
    assert [cell.value for cell in sheet[2]] == ["是", "2026-11-02 10:30:00", "2026-11-02"]


async def test_exporter_stream_matches_workbook(monkeypatch: pytest.MonkeyPatch) -> None:
    """分块拼接等于完整工作簿；小块时多块产出。"""
    monkeypatch.setattr(openpyxl_exporter, "EXPORT_CHUNK_SIZE", 64)
    exporter = OpenpyxlExporter()
    chunks = [chunk async for chunk in exporter.export(_rows(), columns=ConcurrentStableList(_COLUMNS))]
    assert len(chunks) > 1
    # xlsx 元数据含生成时间，两次生成字节不保证一致：按可解析内容断言
    sheet = load_workbook(BytesIO(b"".join(chunks)))[DATA_SHEET_NAME]
    assert [cell.value for cell in sheet[1]] == ["姓名", "状态", "手机号"]
    assert sheet.max_row == 3


def test_exporter_plugin_name_is_empty() -> None:
    """插件名置空（由显式工厂登记，避免自动登记重名）。"""
    assert OpenpyxlExporter.plugin_name == ""
