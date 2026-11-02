"""打印导出能力域 · 真实导出实现（reportlab + 对象存储，04_02）。

- `StoragePrintExporter`（插件名 `reportlab`，由 `core/assembly.py` 的显式工厂登记）：取模板元数据 →
  reportlab 渲染 → 落对象存储 → 生成限时预签名取址。
- `export_pdf`：单份单据；`batch_print`：逐份（separate）或合并（merged）；`export_list`：列表表格。
- 批量语义：`documents` 与 `keys` 同序等长；缺 `documents` 时按单据键渲染简版页（不臆造业务字段）；
  单份失败计入 `failed` 并继续，不整体中断。

口径：产物只落对象存储（不建 `sys_file`、不占文件配额）；租户位取请求 / 作业上下文
（`current_tenant_context()`）；对象 key 由 `build_print_object_key` 派生，业务与路由不得自拼。
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.core.logging import get_logger
from bms_core.db.tenant import current_tenant_context
from bms_core.print.base import (
    NULL_PRINT_BIZ_KEY,
    PRINT_BATCH_MODES,
    PRINT_CONTENT_TYPE,
    BasePrintExporter,
    BasePrintTemplateProvider,
    PrintBatchResult,
    PrintDocument,
    PrintExportResult,
    PrintOptions,
    PrintTemplateInfo,
    build_print_object_key,
)
from bms_core.print.renderer import ReportPdfRenderer
from bms_core.storage.base import DEFAULT_PRESIGN_TTL, BaseObjectStorage
from bms_core.transfer.base import ColumnSpec

__all__ = ["StoragePrintExporter"]

_LOGGER = get_logger("bms")

_TIME_FORMAT = "%Y%m%d%H%M%S"
"""产物文件名时间戳格式（UTC）。"""


class StoragePrintExporter(BasePrintExporter):
    """真实打印导出：渲染 PDF、落对象存储、返回限时取址。"""

    # 由 `core/assembly.py` 的显式工厂登记为 `print_exporter:reportlab`；置空避免自动登记重名。
    plugin_name = ""

    def __init__(
        self,
        *,
        storage: BaseObjectStorage,
        templates: BasePrintTemplateProvider,
        renderer: ReportPdfRenderer | None = None,
        presign_ttl: int = DEFAULT_PRESIGN_TTL,
    ) -> None:
        """初始化。

        Args:
            storage: 对象存储实现（产物落点与取址）。
            templates: 模板来源（模板键 → 模板元数据）。
            renderer: 渲染器（None 用缺省配置的 reportlab 渲染器）。
            presign_ttl: 取址有效期（秒）。
        """
        self._storage = storage
        self._templates = templates
        self._renderer = renderer or ReportPdfRenderer()
        self._presign_ttl = presign_ttl

    async def export_pdf(
        self,
        template_key: str,
        document: PrintDocument,
        *,
        options: PrintOptions | None = None,
    ) -> PrintExportResult:
        """导出单份单据 PDF。

        Args:
            template_key: 打印模板键。
            document: 单据数据。
            options: 渲染选项（None 用平台缺省）。

        Returns:
            PrintExportResult: 产物（对象 key / 文件名 / 限时取址）。

        Raises:
            PrintTemplateNotFoundError: 模板键未命中（50201 / 404）。
        """
        template = await self._templates.get(template_key)
        biz_key = document.biz_key or NULL_PRINT_BIZ_KEY
        data = await asyncio.to_thread(self._renderer.render_document, template, document, options)
        return await self._store(template_key, biz_key, data, f"{template.name}_{biz_key}.pdf")

    async def batch_print(
        self,
        keys: ConcurrentStableList[str],
        *,
        template_key: str,
        mode: str = "separate",
        options: PrintOptions | None = None,
        documents: ConcurrentStableList[PrintDocument] | None = None,
    ) -> PrintBatchResult:
        """批量打印（逐份 / 合并）。

        Args:
            keys: 单据键集合（空集合返回空汇总）。
            template_key: 打印模板键。
            mode: 批量模式（separate / merged）。
            options: 渲染选项。
            documents: 单据数据（与 `keys` 同序等长；None 渲染简版页）。

        Returns:
            PrintBatchResult: 批量结果（汇总计数 + 产物明细 + 失败摘要）。

        Raises:
            ParamError: `mode` 非法或 `documents` 长度不符（`10001`）。
            PrintTemplateNotFoundError: 模板键未命中（50201 / 404）。
        """
        if mode not in PRINT_BATCH_MODES:
            raise ParamError(f"批量打印模式非法：{mode}")
        if not keys:
            return PrintBatchResult(total=0, succeeded=0, failed=0)
        if documents is not None and len(documents) != len(keys):
            raise ParamError(f"documents 数量与单据键不一致（{len(documents)} != {len(keys)}）")
        template = await self._templates.get(template_key)
        resolved: ConcurrentStableList[PrintDocument] = ConcurrentStableList(
            documents[index] if documents is not None else PrintDocument(biz_key=key) for index, key in enumerate(keys)
        )
        if mode == PRINT_BATCH_MODES[1]:
            return await self._merged(template, template_key, keys, resolved, options)
        return await self._separate(template, template_key, keys, resolved, options)

    async def export_list(
        self,
        title: str,
        columns: ConcurrentStableList[ColumnSpec],
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        options: PrintOptions | None = None,
    ) -> PrintExportResult:
        """导出列表 PDF（表格）。

        Args:
            title: 报表标题。
            columns: 列定义（列序与表头）。
            rows: 数据行（已脱敏）。
            options: 渲染选项。

        Returns:
            PrintExportResult: 产物（对象 key / 文件名 / 限时取址）。
        """
        data = await asyncio.to_thread(self._renderer.render_list, title, columns, rows, options)
        token = secrets.token_urlsafe(12)
        stamp = datetime.now(UTC).strftime(_TIME_FORMAT)
        return await self._store("list", token, data, f"{title or '列表'}_{stamp}.pdf")

    async def _separate(
        self,
        template: PrintTemplateInfo,
        template_key: str,
        keys: ConcurrentStableList[str],
        documents: ConcurrentStableList[PrintDocument],
        options: PrintOptions | None,
    ) -> PrintBatchResult:
        """逐份渲染（单份失败不中断）。"""
        items: ConcurrentStableList[PrintExportResult] = ConcurrentStableList()
        failed = 0
        first_error: str | None = None
        for key, document in zip(keys, documents, strict=True):
            biz_key = document.biz_key or key
            try:
                data = await asyncio.to_thread(self._renderer.render_document, template, document, options)
                items.add(await self._store(template_key, biz_key, data, f"{template.name}_{biz_key}.pdf"))
            except Exception as exc:  # 单份失败不阻断整批（记 warning + 计数）
                failed += 1
                first_error = first_error or str(exc)
                _LOGGER.warning("批量打印单份失败", biz_key=biz_key, error=str(exc))
        return PrintBatchResult(
            total=len(keys),
            succeeded=len(items),
            failed=failed,
            items=items,
            message=first_error,
        )

    async def _merged(
        self,
        template: PrintTemplateInfo,
        template_key: str,
        keys: ConcurrentStableList[str],
        documents: ConcurrentStableList[PrintDocument],
        options: PrintOptions | None,
    ) -> PrintBatchResult:
        """合并渲染为一份产物（以批内首个单据键为标识）。"""
        data = await asyncio.to_thread(self._renderer.render_merged, template, documents, options)
        # 合并产物以「首单据键 + merged」标识：既保留单据来源，又不覆盖同键的逐份产物
        biz_key = f"{keys[0]}-merged"
        stamp = datetime.now(UTC).strftime(_TIME_FORMAT)
        artifact = await self._store(template_key, biz_key, data, f"{template.name}_{stamp}.pdf")
        return PrintBatchResult(
            total=len(keys),
            succeeded=len(keys),
            failed=0,
            items=ConcurrentStableList((artifact,)),
        )

    async def _store(
        self,
        template_key: str,
        biz_key: str,
        data: bytes,
        file_name: str,
    ) -> PrintExportResult:
        """落对象存储并生成限时取址。

        Args:
            template_key: 模板键（对象 key 分段）。
            biz_key: 单据键（对象 key 末段）。
            data: PDF 字节。
            file_name: 文件名。

        Returns:
            PrintExportResult: 产物。
        """
        key = build_print_object_key(
            template_key=template_key,
            biz_key=biz_key,
            tenant=current_tenant_context().code,
        )
        await self._storage.put(key, data, content_type=PRINT_CONTENT_TYPE)
        url = await self._storage.presign(key, expires_in=self._presign_ttl)
        return PrintExportResult(
            object_key=key,
            file_name=file_name,
            size=len(data),
            content_type=PRINT_CONTENT_TYPE,
            url=url.url,
            expires_in=url.expires_in,
        )
