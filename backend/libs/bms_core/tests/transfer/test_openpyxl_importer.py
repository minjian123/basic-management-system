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
from bms_core.transfer.importer import ParsedRow, validate_rows_common
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


async def test_value_types_and_errors() -> None:
    """文本 / 整数 / 数字 / 布尔 / 日期 / 日期时间的转换与非法值。"""
    from datetime import date, datetime

    columns = ConcurrentStableList(
        (
            ColumnSpec(key="t", title="文本"),
            ColumnSpec(key="i", title="整数", value_type="int"),
            ColumnSpec(key="n", title="数字", value_type="number"),
            ColumnSpec(key="b", title="布尔", value_type="bool"),
            ColumnSpec(key="d", title="日期", value_type="date"),
            ColumnSpec(key="dt", title="日期时间", value_type="datetime"),
            ColumnSpec(key="bad", title="坏类型", value_type="bad"),
        )
    )
    rows = ConcurrentStableList(
        (
            ParsedRow(
                row_no=2,
                values=ConcurrentStableFrozenDict[str, object](
                    {
                        "t": datetime(2026, 1, 2, 3, 4, 5),
                        "i": "5",
                        "n": "1.5",
                        "b": "yes",
                        "d": datetime(2026, 1, 2, 3, 4, 5),
                        "dt": date(2026, 1, 2),
                    }
                ),
            ),
            ParsedRow(
                row_no=3,
                values=ConcurrentStableFrozenDict[str, object](
                    {
                        "t": date(2026, 1, 2),
                        "i": 6,
                        "n": 2.5,
                        "b": "false",
                        "d": "2026-01-02",
                        "dt": "2026-01-02T03:04:05",
                    }
                ),
            ),
            ParsedRow(
                row_no=4,
                values=ConcurrentStableFrozenDict[str, object](
                    {
                        "i": True,
                        "n": True,
                        "b": "maybe",
                        "d": "not-date",
                        "dt": "not-date",
                        "bad": "x",
                    }
                ),
            ),
        )
    )
    result = await validate_rows_common(rows, columns=columns)
    assert result.valid_rows[0].values["i"] == 5
    assert result.valid_rows[0].values["n"] == 1.5
    assert result.valid_rows[0].values["b"] is True
    assert result.valid_rows[0].values["d"] == date(2026, 1, 2)
    assert result.valid_rows[0].values["dt"] == datetime(2026, 1, 2, 0, 0)
    assert result.valid_rows[0].values["t"] == "2026-01-02 03:04:05"
    assert result.valid_rows[1].values["d"] == date(2026, 1, 2)
    assert result.valid_rows[1].values["dt"] == datetime(2026, 1, 2, 3, 4, 5)
    fields = {(error.row, error.field) for error in result.errors}
    assert fields == {
        (4, "i"),
        (4, "n"),
        (4, "b"),
        (4, "d"),
        (4, "dt"),
        (4, "bad"),
    }


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


def test_zip_inspect_rejects_missing_parts_and_bad_paths() -> None:
    """zip 缺少 OOXML 条目 / 条目路径非法。"""
    from zipfile import ZipFile

    missing = BytesIO()
    with ZipFile(missing, "w") as archive:
        archive.writestr("foo.txt", b"x")
    with pytest.raises(XlsxInvalidFileError):
        inspect_xlsx(missing.getvalue(), max_uncompressed_bytes=1024, max_zip_entries=10)

    bad_path = BytesIO()
    with ZipFile(bad_path, "w") as archive:
        archive.writestr("../evil", b"x")
        archive.writestr("[Content_Types].xml", b"x")
        archive.writestr("xl/workbook.xml", b"x")
    with pytest.raises(XlsxInvalidFileError):
        inspect_xlsx(bad_path.getvalue(), max_uncompressed_bytes=1024, max_zip_entries=10)


def test_zip_inspect_rejects_encrypted(monkeypatch: pytest.MonkeyPatch) -> None:
    """加密标记的 zip 条目整体拒绝。"""
    from types import SimpleNamespace

    class _Archive:
        def __enter__(self) -> _Archive:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def infolist(self) -> ConcurrentStableList[SimpleNamespace]:
            return ConcurrentStableList(
                (
                    SimpleNamespace(filename="[Content_Types].xml", flag_bits=0, file_size=1),
                    SimpleNamespace(filename="xl/workbook.xml", flag_bits=1, file_size=1),
                )
            )

    def _fake_zip(*_args: object, **_kwargs: object) -> _Archive:
        return _Archive()

    monkeypatch.setattr("bms_core.transfer.openpyxl_io.ZipFile", _fake_zip)
    with pytest.raises(XlsxInvalidFileError, match="加密"):
        inspect_xlsx(b"x", max_uncompressed_bytes=1024, max_zip_entries=10)


def test_read_sheet_rows_error_paths() -> None:
    """解析异常 / 缺 sheet / 缺表头 / 尾部空列头 / 短行。"""
    from datetime import date, datetime
    from zipfile import ZipFile

    import bms_core.transfer.openpyxl_io as io

    columns = ConcurrentStableList((ColumnSpec(key="name", title="姓名"),))
    corrupted = BytesIO()
    with ZipFile(corrupted, "w") as archive:
        archive.writestr("[Content_Types].xml", b"not-xml")
        archive.writestr("xl/workbook.xml", b"not-xml")
    with pytest.raises(XlsxInvalidFileError, match="解析失败"):
        io.read_sheet_rows(
            corrupted.getvalue(),
            sheet_name=DATA_SHEET_NAME,
            columns=columns,
            max_uncompressed_bytes=1024 * 1024,
            max_zip_entries=100,
        )

    data = _workbook([["张三"]])
    with pytest.raises(XlsxTemplateMismatchError):
        io.read_sheet_rows(
            data,
            sheet_name="其他",
            columns=columns,
            max_uncompressed_bytes=1024 * 1024,
            max_zip_entries=100,
        )

    empty_book = Workbook()
    empty_sheet = empty_book.active
    assert empty_sheet is not None
    empty_sheet.title = DATA_SHEET_NAME
    empty_output = BytesIO()
    empty_book.save(empty_output)
    empty_book.close()
    with pytest.raises(XlsxInvalidFileError, match="表头"):
        io.read_sheet_rows(
            empty_output.getvalue(),
            sheet_name=DATA_SHEET_NAME,
            columns=columns,
            max_uncompressed_bytes=1024 * 1024,
            max_zip_entries=100,
        )

    blank_tail = _workbook([["张三"]], headers=["姓名", " "])
    rows = io.read_sheet_rows(
        blank_tail,
        sheet_name=DATA_SHEET_NAME,
        columns=columns,
        max_uncompressed_bytes=1024 * 1024,
        max_zip_entries=100,
    )
    assert rows[0].values["name"] == "张三"

    short_columns = ConcurrentStableList((ColumnSpec(key="name", title="姓名"), ColumnSpec(key="age", title="年龄")))
    short = _workbook([["张三"]], headers=["姓名", "年龄"])
    rows = io.read_sheet_rows(
        short,
        sheet_name=DATA_SHEET_NAME,
        columns=short_columns,
        max_uncompressed_bytes=1024 * 1024,
        max_zip_entries=100,
    )
    assert rows[0].values["age"] is None

    dated = _workbook(
        [[date(2026, 1, 2), datetime(2026, 1, 2, 3, 4, 5)]],
        headers=["日期", "日期时间"],
    )
    dated_columns = ConcurrentStableList((ColumnSpec(key="d", title="日期"), ColumnSpec(key="dt", title="日期时间")))
    rows = io.read_sheet_rows(
        dated,
        sheet_name=DATA_SHEET_NAME,
        columns=dated_columns,
        max_uncompressed_bytes=1024 * 1024,
        max_zip_entries=100,
    )
    assert rows[0].values["d"] == "2026-01-02 00:00:00"
    assert rows[0].values["dt"] == "2026-01-02 03:04:05"


def test_from_limits_and_defensive_active() -> None:
    """按参数构造导入器；工作簿无默认 sheet 属防御性失败。"""
    from bms_core.transfer.limits import ImportLimits

    importer = OpenpyxlImporter.from_limits(ImportLimits(max_uncompressed_bytes=1, max_zip_entries=2))
    assert importer._max_uncompressed_bytes == 1  # pyright: ignore[reportPrivateUsage]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "bms_core.transfer.openpyxl_io.Workbook",
        lambda: type("_Book", (), {"active": None})(),
    )
    try:
        with pytest.raises(RuntimeError, match="默认 sheet"):
            build_template(_COLUMNS)
    finally:
        monkeypatch.undo()
