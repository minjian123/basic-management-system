"""打印导出能力域 · reportlab 渲染器（04_02）。

- `PdfRenderConfig`：字体（内置 CID 或 `font_path` 指定 TTF）/ 字号 / 页边距 / 页脚开关。
- `ReportPdfRenderer`：把「模板元数据 + 单据数据」或「列定义 + 行集」渲染成 PDF 字节。
  - `render_document`：单份单据（标题 / 主表字段两列 / 明细表）；
  - `render_merged`：多份单据合并为一份 PDF（份间分页，不引入 PDF 合并库）；
  - `render_list`：列表表格（跨页重复表头）。
- 版式承担服务端可控部分：水印（斜向灰字）、页脚（打印人 / 打印时间 / 页码）、长明细跨页表头重复。
- 中文字体：缺省用 reportlab 内置 CID 字体 `STSong-Light`（不嵌入字形、零字体文件）；配置 `font_path`
  后改用 TTF 嵌入，保证跨阅读器一致。

口径：模板变量清单由模板来源给出，渲染器只按实际数据渲染、不臆造字段；时间一律 UTC
`YYYY-MM-DD HH:mm:ss`（时区转换归 05_02）。本模块是同步 CPU 代码，调用方统一经 `asyncio.to_thread`。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.print.base import (
    DEFAULT_PAPER,
    PRINT_ORIENTATIONS,
    PRINT_TONES,
    PrintDocument,
    PrintOptions,
    PrintTemplateInfo,
)
from bms_core.transfer.base import ColumnSpec

__all__ = ["BUILTIN_CID_FONT", "PdfRenderConfig", "ReportPdfRenderer"]

BUILTIN_CID_FONT = "STSong-Light"
"""内置中文字体（reportlab CID 字体，零字体文件）。"""

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
"""页脚打印时间格式（UTC）。"""

_MAX_COLUMN_TITLE = 40
"""表头标题最大字符数（超出截断，避免单列撑爆页宽）。"""

_HEADER_COLOR = colors.HexColor("#1F3864")
"""彩色模式表头底色（深蓝）。"""

_MONO_HEADER_COLOR = colors.HexColor("#404040")
"""黑白模式表头底色（深灰）。"""

_GRID_COLOR = colors.HexColor("#BFBFBF")
"""表格网格线颜色。"""

_LABEL_BACKGROUND = colors.HexColor("#F2F2F2")
"""主表字段标签列底色（浅灰）。"""


@dataclass(frozen=True)
class PdfRenderConfig(BaseValueObject):
    """渲染配置（字体 / 字号 / 页边距 / 页脚）。"""

    font_name: str = "BMS-CJK"
    """TTF 字体注册名（配 `font_path` 时生效；缺省走内置 CID 字体）。"""

    font_path: str = ""
    """TTF 字体路径；空表示用内置 CID 字体。"""

    font_size: float = 10.0
    """正文字号（磅）。"""

    margin_mm: float = 15.0
    """页边距（毫米）。"""

    footer_enabled: bool = True
    """是否渲染页脚（打印人 / 时间 / 页码）。"""


class ReportPdfRenderer:
    """reportlab 渲染器（同步，调用方置于线程执行）。"""

    def __init__(self, config: PdfRenderConfig | None = None) -> None:
        """初始化并注册字体。

        Args:
            config: 渲染配置（None 用缺省）。
        """
        self._config = config or PdfRenderConfig()
        self._font_name = self._resolve_font()

    def render_document(
        self,
        template: PrintTemplateInfo,
        document: PrintDocument,
        options: PrintOptions | None = None,
    ) -> bytes:
        """渲染单份单据 PDF。

        Args:
            template: 模板元数据（标题取模板名）。
            document: 单据数据（主表字段 / 明细行）。
            options: 渲染选项（None 用平台缺省）。

        Returns:
            bytes: PDF 字节。
        """
        story = self._document_story(template, document, options)
        return self._build(story, options)

    def render_merged(
        self,
        template: PrintTemplateInfo,
        documents: ConcurrentStableList[PrintDocument],
        options: PrintOptions | None = None,
    ) -> bytes:
        """把多份单据合并渲染为一份 PDF（份间分页）。

        Args:
            template: 模板元数据。
            documents: 单据集合（空集合渲染一页空提示）。
            options: 渲染选项。

        Returns:
            bytes: PDF 字节。
        """
        story: ConcurrentStableList[Flowable] = ConcurrentStableList()
        for index, document in enumerate(documents):
            if index > 0:
                story.add(PageBreak())
            for item in self._document_story(template, document, options):
                story.add(item)
        if not documents:
            story.add(Paragraph("无可打印单据", self._text_style()))
        return self._build(story, options)

    def render_list(
        self,
        title: str,
        columns: ConcurrentStableList[ColumnSpec],
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        options: PrintOptions | None = None,
    ) -> bytes:
        """渲染列表 PDF（表格式，跨页重复表头）。

        Args:
            title: 报表标题。
            columns: 列定义（列序与表头）。
            rows: 数据行（列键 → 已脱敏值）。
            options: 渲染选项。

        Returns:
            bytes: PDF 字节。
        """
        story: ConcurrentStableList[Flowable] = ConcurrentStableList()
        story.add(Paragraph(escape(title or "列表"), self._title_style()))
        story.add(Spacer(1, 4 * mm))
        if not rows:
            story.add(Paragraph("当前筛选无数据", self._text_style()))
            return self._build(story, options)
        header: ConcurrentStableList[object] = ConcurrentStableList(
            self._cell(column.title[:_MAX_COLUMN_TITLE], header=True) for column in columns
        )
        data: ConcurrentStableList[ConcurrentStableList[object]] = ConcurrentStableList((header,))
        for row in rows:
            data.add(ConcurrentStableList(self._cell(_display(row.get(column.key))) for column in columns))
        story.add(self._table(data, column_count=len(columns), options=options))
        return self._build(story, options)

    def _document_story(
        self,
        template: PrintTemplateInfo,
        document: PrintDocument,
        options: PrintOptions | None,
    ) -> ConcurrentStableList[Flowable]:
        """构造单份单据的 story（标题 / 主表字段 / 明细表）。

        Args:
            template: 模板元数据。
            document: 单据数据。
            options: 渲染选项。

        Returns:
            ConcurrentStableList[object]: story 元素序列。
        """
        story: ConcurrentStableList[Flowable] = ConcurrentStableList()
        story.add(Paragraph(escape(template.name or template.key), self._title_style()))
        if document.biz_key:
            story.add(Paragraph(f"单据编号：{escape(document.biz_key)}", self._text_style()))
        story.add(Spacer(1, 4 * mm))
        if document.fields:
            field_rows: ConcurrentStableList[ConcurrentStableList[object]] = ConcurrentStableList()
            for key, value in document.fields.items():
                field_rows.add(ConcurrentStableList((self._cell(str(key), bold=True), self._cell(_display(value)))))
            table = Table([list(row) for row in field_rows], colWidths=[self._label_width(), None])
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, _GRID_COLOR),
                        ("BACKGROUND", (0, 0), (0, -1), _LABEL_BACKGROUND),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.add(table)
            story.add(Spacer(1, 4 * mm))
        if document.rows:
            header_keys: ConcurrentStableList[str] = ConcurrentStableList(document.rows[0].keys())
            header: ConcurrentStableList[object] = ConcurrentStableList(
                self._cell(key[:_MAX_COLUMN_TITLE], header=True) for key in header_keys
            )
            detail: ConcurrentStableList[ConcurrentStableList[object]] = ConcurrentStableList((header,))
            for row in document.rows:
                detail.add(ConcurrentStableList(self._cell(_display(row.get(key))) for key in header_keys))
            story.add(self._table(detail, column_count=len(header_keys), options=options))
        return story

    def _table(
        self,
        data: ConcurrentStableList[ConcurrentStableList[object]],
        *,
        column_count: int,
        options: PrintOptions | None,
    ) -> LongTable:
        """构造跨页重复表头的表格。

        Args:
            data: 表格数据（首行为表头）。
            column_count: 列数。
            options: 渲染选项（色调影响表头配色）。

        Returns:
            LongTable: 表格元素。
        """
        count = max(column_count, 1)
        usable = self._usable_width(options) - (count * 2)
        widths: ConcurrentStableList[float] = ConcurrentStableList([usable / count] * count)
        table = LongTable([list(row) for row in data], colWidths=list(widths), repeatRows=1)
        header_back = _HEADER_COLOR if self._tone(options) == PRINT_TONES[0] else _MONO_HEADER_COLOR
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), header_back),
                    ("GRID", (0, 0), (-1, -1), 0.4, _GRID_COLOR),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table

    def _build(self, story: ConcurrentStableList[Flowable], options: PrintOptions | None) -> bytes:
        """把 story 渲染为 PDF 字节（挂水印与页脚回调）。

        Args:
            story: story 元素序列。
            options: 渲染选项。

        Returns:
            bytes: PDF 字节。
        """
        margin = self._config.margin_mm * mm
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=self._page_size(options),
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
        )
        decorate = self._page_decorator(options)
        document.build(list(story), onFirstPage=decorate, onLaterPages=decorate)
        return buffer.getvalue()

    def _page_decorator(self, options: PrintOptions | None) -> Callable[[Canvas, object], None]:
        """构造页装饰回调（水印 + 页脚）。

        Args:
            options: 渲染选项。

        Returns:
            Callable[[Canvas, object], None]: 页回调（canvas, doc）。
        """
        watermark = (options.watermark if options is not None else "") or ""
        printed_by = (options.printed_by if options is not None else None) or ""
        printed_at = datetime.now(UTC).strftime(_TIME_FORMAT)
        font = self._font_name
        margin = self._config.margin_mm * mm
        page_width = self._page_size(options)[0]
        page_height = self._page_height(options)
        footer_enabled = self._config.footer_enabled

        def decorate(canvas: Canvas, doc: object) -> None:
            """绘制水印与页脚。

            Args:
                canvas: reportlab canvas。
                doc: 当前文档（取页码）。
            """
            canvas.saveState()
            if watermark:
                canvas.setFont(font, max(18.0, self._config.font_size * 3))
                canvas.setFillGray(0.86)
                canvas.translate(page_width / 2, page_height / 2)
                canvas.rotate(45)
                canvas.drawCentredString(0, 0, watermark)
                canvas.setFillGray(0)
            if footer_enabled:
                page_number = getattr(doc, "page", 1)
                canvas.setFont(font, 8)
                canvas.setFillGray(0.4)
                if printed_by:
                    canvas.drawString(margin, margin / 2, printed_by)
                canvas.drawCentredString(page_width / 2, margin / 2, printed_at)
                canvas.drawRightString(page_width - margin, margin / 2, f"第 {page_number} 页")
            canvas.restoreState()

        return decorate

    def _resolve_font(self) -> str:
        """注册并返回生效字体名（同名只注册一次）。

        Returns:
            str: 注册到 reportlab 的字体名。
        """
        path = self._config.font_path.strip()
        name = self._config.font_name.strip() or "BMS-CJK"
        if not path:
            if BUILTIN_CID_FONT not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(UnicodeCIDFont(BUILTIN_CID_FONT))  # pyright: ignore[reportUnknownMemberType]
            return BUILTIN_CID_FONT
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, path))  # pyright: ignore[reportUnknownMemberType]
        return name

    def _text_style(self) -> ParagraphStyle:
        """正文样式。

        Returns:
            ParagraphStyle: 段落样式。
        """
        return ParagraphStyle(
            "bms-text",
            fontName=self._font_name,
            fontSize=self._config.font_size,
            leading=self._config.font_size * 1.4,
        )

    def _title_style(self) -> ParagraphStyle:
        """标题样式。

        Returns:
            ParagraphStyle: 段落样式。
        """
        size = self._config.font_size + 6
        return ParagraphStyle("bms-title", fontName=self._font_name, fontSize=size, leading=size * 1.4)

    def _cell(self, text: str, *, header: bool = False, bold: bool = False) -> Paragraph:
        """单元格段落（自动换行 + XML 转义）。

        Args:
            text: 文本。
            header: 是否表头（白字，配深色底）。
            bold: 是否加粗（字号微增；CID 字体无真粗体）。

        Returns:
            Paragraph: 单元格段落。
        """
        size = self._config.font_size + (0.5 if bold or header else 0)
        style = ParagraphStyle(
            "bms-cell",
            fontName=self._font_name,
            fontSize=size,
            leading=size * 1.3,
            textColor=colors.white if header else colors.black,
        )
        return Paragraph(escape(text), style)

    def _page_size(self, options: PrintOptions | None) -> tuple[float, float]:
        """按纸张与方向取页面尺寸。

        Args:
            options: 渲染选项。

        Returns:
            tuple[float, float]: 页面尺寸（磅）。
        """
        paper = options.paper if options is not None else DEFAULT_PAPER
        base = A5 if paper == "A5" else A4
        orientation = options.orientation if options is not None else PRINT_ORIENTATIONS[0]
        return landscape(base) if orientation == PRINT_ORIENTATIONS[1] else base

    def _page_height(self, options: PrintOptions | None) -> float:
        """页面高度。

        Args:
            options: 渲染选项。

        Returns:
            float: 页面高度（磅）。
        """
        return self._page_size(options)[1]

    def _usable_width(self, options: PrintOptions | None) -> float:
        """可用页宽（页宽 - 左右边距）。

        Args:
            options: 渲染选项。

        Returns:
            float: 可用宽度（磅）。
        """
        return self._page_size(options)[0] - 2 * self._config.margin_mm * mm

    def _label_width(self) -> float:
        """主表字段标签列宽。

        Returns:
            float: 列宽（磅）。
        """
        return 40 * mm

    def _tone(self, options: PrintOptions | None) -> str:
        """生效色调。

        Args:
            options: 渲染选项。

        Returns:
            str: color / mono。
        """
        return options.tone if options is not None else PRINT_TONES[0]


def _display(value: object) -> str:
    """单元格展示文本（None → 空串，其余 str）。

    Args:
        value: 原值。

    Returns:
        str: 展示文本。
    """
    if value is None:
        return ""
    return str(value)
