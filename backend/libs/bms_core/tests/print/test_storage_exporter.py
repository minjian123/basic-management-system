"""真实打印导出器测试：落存储 / 取址 / 逐份与合并 / 失败不中断。"""

from __future__ import annotations

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError, PrintTemplateNotFoundError
from bms_core.print.base import (
    PRINT_CONTENT_TYPE,
    PrintDocument,
    PrintOptions,
    PrintTemplateInfo,
)
from bms_core.print.exporter import StoragePrintExporter
from bms_core.print.renderer import ReportPdfRenderer
from bms_core.print.templates import DEFAULT_DOCUMENT_TEMPLATE_KEY, BuiltinPrintTemplateProvider
from bms_core.storage.base import DEFAULT_PRESIGN_TTL, BaseObjectStorage, PresignedUrl, StoredObject
from bms_core.transfer.base import ColumnSpec

pytestmark = pytest.mark.kiwi_id(2402)

_TEMPLATE_KEY = DEFAULT_DOCUMENT_TEMPLATE_KEY


class _Storage(BaseObjectStorage):
    """内存对象存储（记录写入内容与取址参数）。"""

    plugin_name = ""

    def __init__(self) -> None:
        self.objects: ConcurrentStableDict[str, tuple[bytes, str | None]] = ConcurrentStableDict()
        self.presign_calls: ConcurrentStableList[int] = ConcurrentStableList()

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        self.objects.set(key, (data, content_type))
        return StoredObject(key=key, size=len(data), content_type=content_type)

    async def get(self, key: str) -> bytes:
        return self.objects[key][0]

    async def delete(self, key: str) -> None:
        del self.objects[key]

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def presign(self, key: str, *, method: str = "GET", expires_in: int = DEFAULT_PRESIGN_TTL) -> PresignedUrl:
        self.presign_calls.add(expires_in)
        return PresignedUrl(url=f"file://{key}", expires_in=expires_in, method=method)


class _Renderer:
    """测试渲染器（可按单据键注入失败）。"""

    def __init__(self, fail_keys: ConcurrentStableList[str] | None = None) -> None:
        self._fail = set(fail_keys or ())

    def render_document(
        self, template: PrintTemplateInfo, document: PrintDocument, options: PrintOptions | None = None
    ) -> bytes:
        del template, options
        if (document.biz_key or "") in self._fail:
            raise RuntimeError("渲染失败")
        return b"%PDF-1.4 demo"

    def render_merged(
        self,
        template: PrintTemplateInfo,
        documents: ConcurrentStableList[PrintDocument],
        options: PrintOptions | None = None,
    ) -> bytes:
        del template, documents, options
        return b"%PDF-1.4 merged"

    def render_list(
        self,
        title: str,
        columns: ConcurrentStableList[ColumnSpec],
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        options: PrintOptions | None = None,
    ) -> bytes:
        del title, columns, rows, options
        return b"%PDF-1.4 list"


def _exporter(renderer: _Renderer | None = None, ttl: int = 600) -> tuple[StoragePrintExporter, _Storage]:
    storage = _Storage()
    exporter = StoragePrintExporter(
        storage=storage,
        templates=BuiltinPrintTemplateProvider(),
        renderer=cast("ReportPdfRenderer", renderer or _Renderer()),
        presign_ttl=ttl,
    )
    return exporter, storage


async def test_export_pdf_stores_and_presigns() -> None:
    """单份导出：落对象存储（PDF 类型）+ 限时取址（有效期取参）。"""
    exporter, storage = _exporter()
    result = await exporter.export_pdf(_TEMPLATE_KEY, PrintDocument(biz_key="SO-1"))
    assert result.object_key.startswith("demo/prints/generic_document/")
    assert result.object_key.endswith(".pdf")
    assert result.content_type == PRINT_CONTENT_TYPE
    assert result.size > 0
    assert result.url is not None and result.url.startswith("file://")
    assert result.expires_in == 600
    assert storage.presign_calls == (600,)
    stored = storage.objects[result.object_key]
    assert stored[1] == PRINT_CONTENT_TYPE


async def test_export_pdf_template_missing() -> None:
    """模板键未命中（50201）。"""
    exporter, _ = _exporter()
    with pytest.raises(PrintTemplateNotFoundError):
        await exporter.export_pdf("not-exists", PrintDocument(biz_key="SO-1"))


async def test_batch_separate_and_merged() -> None:
    """逐份出多份产物；合并出单份产物且计数为单据数。"""
    exporter, storage = _exporter()
    keys: ConcurrentStableList[str] = ConcurrentStableList(("A", "B"))
    documents: ConcurrentStableList[PrintDocument] = ConcurrentStableList(
        (PrintDocument(biz_key="A"), PrintDocument(biz_key="B"))
    )
    separate = await exporter.batch_print(keys, template_key=_TEMPLATE_KEY, documents=documents)
    assert separate.total == 2
    assert separate.succeeded == 2
    assert separate.failed == 0
    assert len(separate.items) == 2
    assert len(storage.objects) == 2
    merged = await exporter.batch_print(keys, template_key=_TEMPLATE_KEY, mode="merged", documents=documents)
    assert merged.succeeded == 2
    assert len(merged.items) == 1
    assert merged.items[0].object_key.endswith("/A-merged.pdf")
    assert len(storage.objects) == 3


async def test_batch_without_documents_renders_placeholder() -> None:
    """缺 documents 时按单据键渲染简版页（成功，不臆造字段）。"""
    exporter, _ = _exporter()
    result = await exporter.batch_print(ConcurrentStableList(("A",)), template_key=_TEMPLATE_KEY)
    assert result.succeeded == 1
    assert result.items[0].object_key.endswith("/A.pdf")


async def test_batch_single_failure_does_not_abort() -> None:
    """单份失败计入 failed，其余继续。"""
    exporter, _ = _exporter(renderer=_Renderer(fail_keys=ConcurrentStableList(("A",))))
    documents: ConcurrentStableList[PrintDocument] = ConcurrentStableList(
        (PrintDocument(biz_key="A"), PrintDocument(biz_key="B"))
    )
    result = await exporter.batch_print(
        ConcurrentStableList(("A", "B")), template_key=_TEMPLATE_KEY, documents=documents
    )
    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.message == "渲染失败"


async def test_batch_rejects_bad_mode_and_length() -> None:
    """非法模式 / documents 长度不符拒绝（10001）。"""
    exporter, _ = _exporter()
    documents: ConcurrentStableList[PrintDocument] = ConcurrentStableList((PrintDocument(biz_key="A"),))
    with pytest.raises(ParamError):
        await exporter.batch_print(
            ConcurrentStableList(("A",)), template_key=_TEMPLATE_KEY, mode="bad", documents=documents
        )
    with pytest.raises(ParamError):
        await exporter.batch_print(ConcurrentStableList(("A", "B")), template_key=_TEMPLATE_KEY, documents=documents)


async def test_batch_empty_keys() -> None:
    """空单据集合返回零计数（零副作用）。"""
    exporter, storage = _exporter()
    result = await exporter.batch_print(ConcurrentStableList[str](), template_key=_TEMPLATE_KEY)
    assert result.total == 0
    assert len(storage.objects) == 0


async def test_export_list_key_uses_list_segment() -> None:
    """列表 PDF 落 `prints/list/` 分段。"""
    exporter, _ = _exporter()
    columns: ConcurrentStableList[ColumnSpec] = ConcurrentStableList((ColumnSpec(key="name", title="姓名"),))
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
        (ConcurrentStableDict({"name": "张三"}),)
    )
    result = await exporter.export_list("用户列表", columns, rows)
    assert result.object_key.startswith("demo/prints/list/")
    assert result.file_name.startswith("用户列表_")
