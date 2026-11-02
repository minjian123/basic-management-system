"""导入导出能力域 · openpyxl 读写助手（模板 / 解析 / 错误明细共用）。

- `inspect_xlsx`：xlsx 容器与 zip 安全检查（扩展名由调用方校验；本函数只看字节）。
- `read_sheet_rows`：按列定义读取指定 sheet，返回带 Excel 行号的 `ParsedRow`。
- `build_template`：生成「数据」+「填写说明」两 sheet 的模板。
- `build_error_report`：按行错误生成错误明细 xlsx（写模式，低内存）。

口径：openpyxl 读取统一 `read_only=True, data_only=True`（公式只取缓存值、不执行）；所有调用由
`OpenpyxlImporter` 放到 `asyncio.to_thread`，本模块保持同步纯函数，便于测试与复用。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import ImportFileInvalidError, ImportTemplateMismatchError
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.importer import ParsedRow

__all__ = [
    "DATA_SHEET_NAME",
    "NOTES_SHEET_NAME",
    "XLSX_CONTENT_TYPE",
    "XlsxInvalidFileError",
    "XlsxTemplateMismatchError",
    "build_error_report",
    "build_template",
    "inspect_xlsx",
    "read_sheet_rows",
]

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
"""xlsx 内容类型（模板 / 错误明细响应头）。"""

DATA_SHEET_NAME = "数据"
"""模板数据 sheet 名称（解析按名称定位，不依赖顺序）。"""

NOTES_SHEET_NAME = "填写说明"
"""模板填写说明 sheet 名称。"""

_REQUIRED_WORKBOOK_PARTS = ("[Content_Types].xml", "xl/workbook.xml")
"""xlsx 必需容器条目（缺失即非 OOXML 工作簿）。"""

_TYPE_LABELS = {
    "text": "文本",
    "int": "整数",
    "number": "数字",
    "bool": "布尔",
    "date": "日期",
    "datetime": "日期时间",
}
"""列值类型中文说明（只进填写说明 sheet）。"""


class XlsxInvalidFileError(ImportFileInvalidError):
    """xlsx 文件非法（非 OOXML / 结构损坏 / zip 超限 / 无数据行）。"""


class XlsxTemplateMismatchError(ImportTemplateMismatchError):
    """模板不匹配（缺少数据 sheet / 表头列数、列序、列头文本不一致）。"""


def inspect_xlsx(data: bytes, *, max_uncompressed_bytes: int, max_zip_entries: int) -> None:
    """校验 xlsx 容器与 zip 安全边界。

    Args:
        data: 文件字节。
        max_uncompressed_bytes: 解压后总大小上限（字节）。
        max_zip_entries: zip 条目数上限。

    Raises:
        XlsxInvalidFileError: 非 zip / 缺 OOXML 条目 / 条目或解压超限 / 加密 / 路径非法。
    """
    if not data:
        raise XlsxInvalidFileError("文件为空")
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > max_zip_entries:
                raise XlsxInvalidFileError(f"zip 条目数超限（>{max_zip_entries}）")
            names = {info.filename for info in infos}
            for required in _REQUIRED_WORKBOOK_PARTS:
                if required not in names:
                    raise XlsxInvalidFileError(f"不是有效的 xlsx（缺少 {required}）")
            total = 0
            for info in infos:
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise XlsxInvalidFileError("zip 条目路径非法")
                if info.flag_bits & 0x1:
                    raise XlsxInvalidFileError("不支持加密工作簿")
                total += int(info.file_size)
                if total > max_uncompressed_bytes:
                    raise XlsxInvalidFileError(f"解压后大小超限（>{max_uncompressed_bytes}）")
    except BadZipFile as exc:
        raise XlsxInvalidFileError("不是有效的 xlsx（zip 容器损坏）") from exc


def read_sheet_rows(
    data: bytes,
    *,
    sheet_name: str,
    columns: ConcurrentStableList[ColumnSpec],
    max_uncompressed_bytes: int,
    max_zip_entries: int,
) -> ConcurrentStableList[ParsedRow]:
    """读取指定 sheet 的数据行（第 1 行表头，第 2 行起为数据）。

    Args:
        data: 文件字节。
        sheet_name: sheet 名称（模板固定「数据」）。
        columns: 列定义（列数 / 列序 / 列头文本按此严格核对）。
        max_uncompressed_bytes: 解压后总大小上限。
        max_zip_entries: zip 条目数上限。

    Returns:
        ConcurrentStableList[ParsedRow]: 数据行（整行为空的跳过）。

    Raises:
        XlsxInvalidFileError: 文件非法 / 无表头 / 无数据行。
        XlsxTemplateMismatchError: sheet 缺失 / 表头不匹配。
    """
    inspect_xlsx(data, max_uncompressed_bytes=max_uncompressed_bytes, max_zip_entries=max_zip_entries)
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True, keep_vba=False)
    except Exception as exc:  # openpyxl 的异常类型较多，统一转文件非法
        raise XlsxInvalidFileError("xlsx 解析失败") from exc
    try:
        if sheet_name not in workbook.sheetnames:
            raise XlsxTemplateMismatchError(f"模板缺少「{sheet_name}」sheet")
        worksheet = workbook[sheet_name]
        iterator = worksheet.iter_rows(values_only=True)
        header = next(iterator, None)
        if header is None:
            raise XlsxInvalidFileError("模板缺少表头")
        titles = ["" if value is None else str(value).strip() for value in header]
        while titles and titles[-1] == "":
            titles.pop()
        expected = [column.title for column in columns]
        if titles != expected:
            raise XlsxTemplateMismatchError("表头列数、列序或列头文本与模板不一致")
        rows: ConcurrentStableList[ParsedRow] = ConcurrentStableList()
        for row_no, values in enumerate(iterator, start=2):
            cells = list(values)
            if all(_is_blank(value) for value in cells):
                continue
            if len(cells) < len(columns):  # pragma: no cover（openpyxl read_only 一般按表头宽度补齐）
                cells.extend([None] * (len(columns) - len(cells)))
            row_values = ConcurrentStableFrozenDict[str, object](
                {column.key: _cell_value(cells[index]) for index, column in enumerate(columns)}
            )
            rows.add(ParsedRow(row_no=row_no, values=row_values))
        if not rows:
            raise XlsxInvalidFileError("模板没有数据行")
        return rows
    finally:
        workbook.close()


def build_template(columns: ConcurrentStableList[ColumnSpec]) -> bytes:
    """生成导入模板（「数据」+「填写说明」）。

    Args:
        columns: 列定义。

    Returns:
        bytes: xlsx 字节。
    """
    workbook = Workbook()
    data_sheet = workbook.active
    if data_sheet is None:
        raise RuntimeError("工作簿缺少默认 sheet")
    data_sheet.title = DATA_SHEET_NAME
    data_sheet.append([column.title for column in columns])
    for index, column in enumerate(columns, start=1):
        data_sheet.column_dimensions[get_column_letter(index)].width = max(12, len(column.title) * 2 + 4)
    data_sheet.freeze_panes = "A2"
    for index, column in enumerate(columns, start=1):
        if not column.choices:
            continue
        validation = DataValidation(
            type="list",
            formula1='"' + ",".join(column.choices) + '"',
            allow_blank=not column.required,
        )
        validation.error = f"{column.title}取值非法"
        validation.errorTitle = "取值非法"
        letter = get_column_letter(index)
        data_sheet.add_data_validation(validation)
        validation.add(f"{letter}2:{letter}10000")  # pyright: ignore[reportUnknownMemberType]

    notes_sheet = workbook.create_sheet(NOTES_SHEET_NAME)
    notes_sheet.append(["列名", "是否必填", "类型", "最大长度", "可选值 / 格式", "示例", "说明"])
    for cell in notes_sheet[1]:
        cell.font = Font(bold=True)
    for column in columns:
        notes_sheet.append(
            [
                column.title,
                "是" if column.required else "否",
                _TYPE_LABELS.get(column.value_type, column.value_type),
                column.max_length if column.max_length is not None else "不限",
                "、".join(column.choices) if column.choices else (column.pattern or ""),
                column.example,
                column.note,
            ]
        )
    for index, width in enumerate((16, 10, 10, 10, 30, 20, 40), start=1):
        notes_sheet.column_dimensions[get_column_letter(index)].width = width
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def build_error_report(
    errors: Iterable[tuple[int, str, str]], *, column_titles: ConcurrentStableDict[str, str]
) -> bytes:
    """生成错误明细 xlsx（行号 / 列 / 原因）。

    Args:
        errors: `(行号, 字段键, 原因)` 序列。
        column_titles: 字段键 → 列标题（查不到时展示字段键）。

    Returns:
        bytes: xlsx 字节。
    """
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet("错误明细")
    worksheet.append(["行号", "列", "原因"])
    for row_no, column_key, message in errors:
        worksheet.append([row_no, column_titles.get(column_key, column_key), message])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _is_blank(value: object) -> bool:
    """单元格是否为空。

    Args:
        value: 单元格值。

    Returns:
        bool: 空为 True。
    """
    return value is None or (isinstance(value, str) and value.strip() == "")


def _cell_value(value: object) -> object:
    """单元格值清洗（日期转 ISO 文本；字符串去空白；其余原样交给通用校验）。

    Args:
        value: 单元格值。

    Returns:
        object: 清洗后的值。
    """
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value
