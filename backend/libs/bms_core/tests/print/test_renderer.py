"""reportlab 渲染器测试：单据 / 列表 / 合并 / 纸张方向 / 水印与页脚。"""

from __future__ import annotations

import re

import pytest
from reportlab.pdfbase.ttfonts import TTFError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.print.base import PrintDocument, PrintOptions, PrintTemplateInfo
from bms_core.print.renderer import PdfRenderConfig, ReportPdfRenderer
from bms_core.transfer.base import ColumnSpec

pytestmark = pytest.mark.kiwi_id(2402)

_TEMPLATE = PrintTemplateInfo(key="generic_document", name="通用单据")
_COLUMNS: ConcurrentStableList[ColumnSpec] = ConcurrentStableList(
    (ColumnSpec(key="name", title="姓名"), ColumnSpec(key="status", title="状态"))
)


def _page_count(data: bytes) -> int:
    """统计 PDF 页对象数（未压缩对象直接匹配）。"""
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def _media_box(data: bytes) -> tuple[float, float]:
    """取首个页面尺寸（宽, 高）。"""
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    assert match is not None
    return float(match.group(1)), float(match.group(2))


def _document(rows: int = 0) -> PrintDocument:
    detail: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
        ConcurrentStableDict({"项目": f"第 {index} 行", "金额": index * 10}) for index in range(rows)
    )
    return PrintDocument(
        biz_key="SO-2026-001",
        fields=ConcurrentStableDict({"客户": "示例客户", "金额": 100}),
        rows=detail,
    )


def test_render_document_with_fields_and_rows() -> None:
    """单据渲染产出 PDF；含明细表。"""
    renderer = ReportPdfRenderer()
    data = renderer.render_document(_TEMPLATE, _document(rows=3))
    assert data.startswith(b"%PDF")
    assert len(data) > 1000
    assert _page_count(data) >= 1


def test_render_merged_multi_page() -> None:
    """合并渲染：份间分页，页数 ≥ 份数。"""
    renderer = ReportPdfRenderer()
    documents: ConcurrentStableList[PrintDocument] = ConcurrentStableList(
        (_document(rows=1), _document(rows=1), _document(rows=1))
    )
    data = renderer.render_merged(_TEMPLATE, documents)
    assert _page_count(data) >= 3


def test_render_merged_empty() -> None:
    """空集合渲染空提示页（不报错）。"""
    data = ReportPdfRenderer().render_merged(_TEMPLATE, ConcurrentStableList[PrintDocument]())
    assert data.startswith(b"%PDF")


def test_render_list_repeats_header_across_pages() -> None:
    """列表多行跨页（表头重复由 LongTable 承担，此处断言页数 > 1）。"""
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
        ConcurrentStableDict({"name": f"用户{index}", "status": "启用"}) for index in range(200)
    )
    data = ReportPdfRenderer().render_list("用户列表", _COLUMNS, rows)
    assert _page_count(data) > 1


def test_render_list_empty() -> None:
    """0 行列表渲染空提示（不报错）。"""
    data = ReportPdfRenderer().render_list(
        "用户列表", _COLUMNS, ConcurrentStableList[ConcurrentStableDict[str, object]]()
    )
    assert data.startswith(b"%PDF")


def test_page_size_follows_paper_and_orientation() -> None:
    """纸张与方向影响页面尺寸：A5 小于 A4；横向交换宽高。"""
    renderer = ReportPdfRenderer()
    a4 = _media_box(renderer.render_list("t", _COLUMNS, ConcurrentStableList[ConcurrentStableDict[str, object]]()))
    a5 = _media_box(
        renderer.render_list(
            "t",
            _COLUMNS,
            ConcurrentStableList[ConcurrentStableDict[str, object]](),
            PrintOptions(paper="A5"),
        )
    )
    assert a5[0] < a4[0] and a5[1] < a4[1]
    landscape_size = _media_box(
        renderer.render_list(
            "t",
            _COLUMNS,
            ConcurrentStableList[ConcurrentStableDict[str, object]](),
            PrintOptions(orientation="landscape"),
        )
    )
    assert landscape_size[0] > landscape_size[1]


def test_watermark_changes_output() -> None:
    """水印参数参与渲染（产出字节不同）。"""
    renderer = ReportPdfRenderer(config=PdfRenderConfig(footer_enabled=False))
    plain = renderer.render_list("t", _COLUMNS, ConcurrentStableList[ConcurrentStableDict[str, object]]())
    marked = renderer.render_list(
        "t",
        _COLUMNS,
        ConcurrentStableList[ConcurrentStableDict[str, object]](),
        PrintOptions(watermark="内部资料"),
    )
    assert plain != marked


def test_font_path_invalid_raises() -> None:
    """TTF 路径不存在时注册失败（渲染器构造即报错，不静默降级）。"""
    with pytest.raises(TTFError):
        ReportPdfRenderer(config=PdfRenderConfig(font_path="missing-font.ttf"))
