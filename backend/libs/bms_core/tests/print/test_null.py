"""占位打印实现（`null` 插件）：模板来源恒空 / 恒未命中，导出恒返回占位产物。"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import PrintTemplateNotFoundError
from bms_core.print.base import (
    NULL_PRINT_BIZ_KEY,
    NULL_PRINT_URL,
    PRINT_CONTENT_TYPE,
    PRINT_PLACEHOLDER_MESSAGE,
    PrintDocument,
    PrintOptions,
)
from bms_core.print.null import NullPrintExporter, NullPrintTemplateProvider
from bms_core.transfer.base import ColumnSpec

pytestmark = pytest.mark.kiwi_id(2402)

_COLUMNS: ConcurrentStableList[ColumnSpec] = ConcurrentStableList(
    (ColumnSpec(key="name", title="姓名"), ColumnSpec(key="status", title="状态"))
)


async def test_template_provider_is_empty_and_never_hits() -> None:
    """模板来源：清单恒空、取模板恒未命中（不臆造模板定义）。"""
    provider = NullPrintTemplateProvider()
    assert list(await provider.list()) == []
    assert list(await provider.list(biz_type="sale")) == []
    with pytest.raises(PrintTemplateNotFoundError):
        await provider.get("order")


async def test_export_pdf_returns_placeholder_artifact() -> None:
    """单条导出：有单据键按单据键命名产物，缺省回落占位单据键。"""
    exporter = NullPrintExporter()
    artifact = await exporter.export_pdf("generic_document", PrintDocument(biz_key="SO-1"))
    assert artifact.object_key.endswith("/SO-1.pdf")
    assert artifact.file_name == "generic_document.pdf"
    assert artifact.content_type == PRINT_CONTENT_TYPE
    assert artifact.url == NULL_PRINT_URL
    assert artifact.expires_in > 0
    assert artifact.message == PRINT_PLACEHOLDER_MESSAGE

    fallback = await exporter.export_pdf("generic_document", PrintDocument(biz_key=None))
    assert fallback.object_key.endswith(f"/{NULL_PRINT_BIZ_KEY}.pdf")


async def test_batch_print_empty_keys_returns_message_only() -> None:
    """批量打印：空键集合返回空汇总（零产物）。"""
    result = await NullPrintExporter().batch_print(
        ConcurrentStableList(), template_key="generic_document", mode="separate"
    )
    assert result.total == 0
    assert list(result.items) == []
    assert result.message == PRINT_PLACEHOLDER_MESSAGE


async def test_batch_print_separate_uses_document_keys() -> None:
    """逐份：单据数据里的键优先、缺省回落键集合；数据比键短时按位置回落。"""
    exporter = NullPrintExporter()
    keys: ConcurrentStableList[str] = ConcurrentStableList(("A", "B", "C"))
    documents: ConcurrentStableList[PrintDocument] = ConcurrentStableList(
        (PrintDocument(biz_key="DOC-A"), PrintDocument(biz_key=None))
    )
    result = await exporter.batch_print(
        keys,
        template_key="generic_document",
        mode="separate",
        options=PrintOptions(paper="A4"),
        documents=documents,
    )
    assert result.total == 3
    assert result.succeeded == 3
    assert result.failed == 0
    names = [item.file_name for item in result.items]
    # 第 1 份取单据数据里的键、第 2 份回落键集合、第 3 份超出数据长度回落键集合
    assert names == [
        "generic_document-DOC-A.pdf",
        "generic_document-B.pdf",
        "generic_document-C.pdf",
    ]


async def test_batch_print_merged_single_artifact() -> None:
    """合并：整批产出单份产物，以批内首个单据键为标识（无单据数据时取键集合首项）。"""
    exporter = NullPrintExporter()
    result = await exporter.batch_print(
        ConcurrentStableList(("A", "B")), template_key="generic_document", mode="merged"
    )
    assert result.total == 2
    assert len(result.items) == 1
    assert result.items[0].object_key.endswith("/A.pdf")
    assert result.items[0].file_name == "generic_document.pdf"


async def test_export_list_uses_title_as_identifier() -> None:
    """列表导出：标题非空作产物标识，标题为空回落 `list`。"""
    exporter = NullPrintExporter()
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    titled = await exporter.export_list("用户列表", _COLUMNS, rows)
    # 对象 key 分段经清洗（仅字母 / 数字 / `_` / `.` / `-`），中文标题落为下划线；文件名保留原文
    assert titled.object_key.startswith("global/prints/list/")
    assert titled.object_key.endswith(".pdf")
    assert titled.file_name == "用户列表.pdf"

    untitled = await exporter.export_list("", _COLUMNS, rows, options=PrintOptions(paper="A4"))
    assert untitled.object_key.endswith("/list.pdf")
    assert untitled.file_name == "list.pdf"
