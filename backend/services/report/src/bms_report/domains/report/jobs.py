"""报表域作业：批量打印（`print.batch.execute`，超阈值转后台）。

- 负载：`{template_key, keys, documents, mode, options}`（`documents` 与 `keys` 同序等长；缺省渲染简版页）；
- 执行：经打印导出出口 `batch_print` 渲染并落对象存储，结果摘要写 `sys_job.result`（产物清单）；
- 失败：单份失败计入 `failed` 并继续（出口已实现），整体异常由执行器转失败终态；`max_attempts=1`。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.plugins import ensure_job_plugins
from bms_core.print.base import (
    PRINT_BATCH_MODES,
    BasePrintExporter,
    PrintDocument,
    PrintOptions,
)

__all__ = ["PrintBatchJob"]

_LOGGER = get_logger("bms")


class PrintBatchJob(BaseJobHandler):
    """批量打印作业：逐份 / 合并渲染并落对象存储。"""

    job_type = "print.batch.execute"
    description = "批量打印（逐份 / 合并）超阈值转后台：渲染产物并落对象存储"

    def __init__(self, *, exporter: BasePrintExporter | None = None) -> None:
        """初始化。

        Args:
            exporter: 打印导出（None 按配置解析）。
        """
        self._exporter = exporter

    async def run(self, ctx: JobContext) -> JobResult:
        """执行批量打印。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功（产物清单 + 汇总）/ 取消。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        template_key = str(ctx.payload.get("template_key") or "")
        keys = _keys(ctx)
        mode = str(ctx.payload.get("mode") or PRINT_BATCH_MODES[0])
        documents = _documents(ctx)
        options = _options(ctx)
        exporter = self._exporter if self._exporter is not None else _exporter()
        if await ctx.should_cancel():
            return JobResult.canceled("批量打印已取消")
        result = await exporter.batch_print(
            keys,
            template_key=template_key,
            mode=mode,
            options=options,
            documents=documents or None,
        )
        items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
            ConcurrentStableDict(
                {
                    "object_key": item.object_key,
                    "file_name": item.file_name,
                    "size": item.size,
                    "content_type": item.content_type,
                    "url": item.url,
                    "expires_in": item.expires_in,
                }
            )
            for item in result.items
        )
        output: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "total": result.total,
                "succeeded": result.succeeded,
                "failed": result.failed,
                "items": items,
            }
        )
        await ctx.report_progress(result.succeeded + result.failed, result.total)
        if result.failed:
            _LOGGER.warning(
                "批量打印部分失败",
                template_key=template_key,
                failed=result.failed,
                message=result.message,
            )
        return JobResult.success(output, message=f"批量打印完成：成功 {result.succeeded} / 失败 {result.failed}")


def _keys(ctx: JobContext) -> ConcurrentStableList[str]:
    """读取单据键集合。"""
    raw = ctx.payload.get("keys")
    keys: ConcurrentStableList[str] = ConcurrentStableList()
    if _items(raw) is not None:
        for item in _items(raw) or ():
            keys.add(str(item))
    return keys


def _documents(ctx: JobContext) -> ConcurrentStableList[PrintDocument]:
    """读取单据数据（缺省空集合表示渲染简版页）。"""
    raw = ctx.payload.get("documents")
    documents: ConcurrentStableList[PrintDocument] = ConcurrentStableList()
    items = _items(raw)
    if items is None:
        return documents
    for item in items:
        if not isinstance(item, dict):
            continue
        payload = cast("dict[str, object]", item)
        raw_fields = payload.get("fields")
        fields: ConcurrentStableDict[str, object] = (
            ConcurrentStableDict(cast("dict[str, object]", raw_fields))
            if isinstance(raw_fields, dict)
            else ConcurrentStableDict()
        )
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for row in _items(payload.get("rows")) or ():
            if isinstance(row, dict):
                rows.add(ConcurrentStableDict(cast("dict[str, object]", row)))
        documents.add(
            PrintDocument(
                biz_key=None if payload.get("biz_key") is None else str(payload.get("biz_key")),
                fields=fields,
                rows=rows,
            )
        )
    return documents


def _items(raw: object) -> ConcurrentStableList[object] | None:
    """把可迭代负载（JSON 数组 / 集合容器）统一为列表（字符串与映射不算）。

    Args:
        raw: 原始负载值。

    Returns:
        ConcurrentStableList[object] | None: 元素列表；非可迭代返回 None。
    """
    if isinstance(raw, str | bytes | dict) or not isinstance(raw, Iterable):
        return None
    items: ConcurrentStableList[object] = ConcurrentStableList()
    for item in cast("Iterable[object]", raw):
        items.add(item)
    return items


def _options(ctx: JobContext) -> PrintOptions | None:
    """读取渲染选项（缺省 None 表示平台缺省）。"""
    raw = ctx.payload.get("options")
    if not isinstance(raw, dict):
        return None
    payload = cast("dict[str, object]", raw)
    return PrintOptions(
        paper=str(payload.get("paper") or "A4"),
        orientation=str(payload.get("orientation") or "portrait"),
        tone=str(payload.get("tone") or "color"),
        watermark=str(payload.get("watermark") or ""),
        printed_by=None if payload.get("printed_by") is None else str(payload.get("printed_by")),
    )


def _exporter() -> BasePrintExporter:
    """解析打印导出实现。

    Returns:
        BasePrintExporter: 打印导出实例。
    """
    settings = get_settings()
    return cast(
        "BasePrintExporter",
        resolve_plugin(
            "print_exporter", settings.print_exporter.provider, expected_version=BasePrintExporter.contract_version
        ),
    )
