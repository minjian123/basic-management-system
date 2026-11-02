"""openpyxl 真实导入器测试：模板 / 解析 / 表头 / 类型 / 通用校验 / zip 安全 / 错误明细。"""

from collections.abc import Sequence
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.importer import ParsedRow
from bms_core.transfer.openpyxl import OpenpyxlImporter
from bms_core.transfer.openpyxl_io import (
    DATA_SHEET_NAME,
    NOTES_SHEET_NAME,
    XlsxInvalidFileError,
    XlsxTemplateMismatchError,
    build_error_report,
    build_template,
    inspect_xlsx,
)

pytestmark = pytest.mark.kiwi_id(2401)

_COLUMNS = ConcurrentStableList(
    (
        ColumnSpec(key="name", title="姓名", required=True, max_length=8, pattern=r"^[\u4e00-\u9fa5]+$"),
        ColumnSpec(key="age", title="年龄", value_type="int"),
        ColumnSpec(key="enabled", title="启用", value_type="bool"),
        ColumnSpec(
            key="status",
            title="状态",
            choices=ConcurrentStableFrozenList(("enabled", "disabled")),
        ),
    )
)


def _workbook(  # bare-collections:allow
    rows: Sequence[Sequence[object]], *, headers: Sequence[str] | None = None
) -> bytes:
    """构造测试 xlsx。

    Args:
        rows: 数据行。
        headers: 表头（缺省取 `_COLUMNS` 标题）。

    Returns:
        bytes: xlsx 字节。
    """
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = DATA_SHEET_NAME
    sheet.append(list(headers or [column.title for column in _COLUMNS]))
    for row in rows:
        sheet.append(list(row))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


async def test_parse_rows_and_validate() -> None:
    """解析带行号，通用校验通过时返回清洗值。"""
    data = _workbook([["张三", 18, "是", "enabled"], ["李四", "20", "0", "disabled"]])
    importer = OpenpyxlImporter()
    rows = await importer.parse_rows(data, columns=_COLUMNS)
    assert [row.row_no for row in rows] == [2, 3]
    assert rows[0].values["name"] == "张三"
    result = await importer.validate_rows(rows, columns=_COLUMNS)
    assert len(result.errors) == 0
    assert len(result.valid_rows) == 2
    assert result.valid_rows[1].values["age"] == 20
    assert result.valid_rows[1].values["enabled"] is False


async def test_header_mismatch_and_empty_data() -> None:
    """表头不匹配 / 无数据行 → 文件级错误。"""
    importer = OpenpyxlImporter()
    with pytest.raises(XlsxTemplateMismatchError):
        await importer.parse_rows(_workbook([["张三"]], headers=["姓名", "年龄"]), columns=_COLUMNS)
    with pytest.raises(XlsxInvalidFileError):
        await importer.parse_rows(_workbook([]), columns=_COLUMNS)


async def test_blank_rows_skipped() -> None:
    """整行为空跳过，行号保持 Excel 物理行号。"""
    data = _workbook([["张三", 18, "是", "enabled"], [None, None, None, None], ["李四", 20, "否", "disabled"]])
    rows = await OpenpyxlImporter().parse_rows(data, columns=_COLUMNS)
    assert [row.row_no for row in rows] == [2, 4]


async def test_generic_validation_errors() -> None:
    """必填 / 长度 / 正则 / 类型 / 可选值错误逐项报出。"""
    rows = ConcurrentStableList(
        (
            ParsedRow(
                row_no=2,
                values=ConcurrentStableFrozenDict[str, object](
                    {"name": "", "age": 1, "enabled": "yes", "status": "enabled"}
                ),
            ),
            ParsedRow(
                row_no=3,
                values=ConcurrentStableFrozenDict[str, object](
                    {"name": "abc", "age": "x", "enabled": "maybe", "status": "other"}
                ),
            ),
            ParsedRow(
                row_no=4,
                values=ConcurrentStableFrozenDict[str, object](
                    {"name": "张三丰四五六七八九", "age": 2, "enabled": "1", "status": "disabled"}
                ),
            ),
        )
    )
    result = await OpenpyxlImporter().validate_rows(rows, columns=_COLUMNS)
    fields = {(error.row, error.field) for error in result.errors}
    assert (2, "name") in fields
    assert (3, "name") in fields
    assert (3, "age") in fields
    assert (4, "name") in fields


def test_template_structure_and_choices() -> None:
    """模板含「数据」+「填写说明」两 sheet，数据 sheet 只有列头。"""
    data = build_template(_COLUMNS)
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        assert workbook.sheetnames == [DATA_SHEET_NAME, NOTES_SHEET_NAME]
        data_sheet = workbook[DATA_SHEET_NAME]
        rows = list(data_sheet.iter_rows(values_only=True))
        assert rows == [("姓名", "年龄", "启用", "状态")]
        notes = list(workbook[NOTES_SHEET_NAME].iter_rows(values_only=True))
        assert notes[0][0] == "列名"
        assert notes[1][1] == "是"
    finally:
        workbook.close()


def test_error_report() -> None:
    """错误明细 xlsx 含行号 / 列 / 原因。"""
    data = build_error_report(
        ((3, "name", "必填"), (5, "unknown", "非法")),
        column_titles=ConcurrentStableDict({"name": "姓名"}),
    )
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        active = workbook.active
        assert active is not None
        rows = list(active.iter_rows(values_only=True))
    finally:
        workbook.close()
    assert rows == [("行号", "列", "原因"), (3, "姓名", "必填"), (5, "unknown", "非法")]


def test_zip_security_limits() -> None:
    """zip 条目 / 解压大小上限与非法容器。"""
    data = _workbook([["张三", 18, "是", "enabled"]])
    inspect_xlsx(data, max_uncompressed_bytes=1024 * 1024, max_zip_entries=100)
    with pytest.raises(XlsxInvalidFileError):
        inspect_xlsx(data, max_uncompressed_bytes=1, max_zip_entries=100)
    with pytest.raises(XlsxInvalidFileError):
        inspect_xlsx(data, max_uncompressed_bytes=1024 * 1024, max_zip_entries=1)
    with pytest.raises(XlsxInvalidFileError):
        inspect_xlsx(b"not-a-zip", max_uncompressed_bytes=1024, max_zip_entries=1)
    with pytest.raises(XlsxInvalidFileError):
        inspect_xlsx(b"", max_uncompressed_bytes=1024, max_zip_entries=1)
