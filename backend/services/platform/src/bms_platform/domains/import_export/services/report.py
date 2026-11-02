"""导入域报告助手：错误项 / 作业结果解析 / report token 键与文件名。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.job import SysJobError
from bms_platform.domains.import_export.schemas.imports import ImportErrorItem

__all__ = [
    "build_error_items",
    "parse_job_result",
    "report_filename",
    "report_key",
    "token_payload",
]


def build_error_items(errors: Iterable[SysJobError]) -> ConcurrentStableList[ImportErrorItem]:
    """错误明细记录 → API 错误项。

    Args:
        errors: `sys_job_error` 记录。

    Returns:
        ConcurrentStableList[ImportErrorItem]: 错误项。
    """
    return ConcurrentStableList(
        ImportErrorItem(
            row=int(error.row_no or 0),
            column=error.column_key,
            message=error.message,
        )
        for error in errors
    )


def parse_job_result(raw: str | None) -> ConcurrentStableDict[str, object]:
    """解析 `sys_job.result` JSON。

    Args:
        raw: JSON 文本。

    Returns:
        ConcurrentStableDict[str, object]: 结果字段（非法 / 空返回空映射）。
    """
    if not raw:
        return ConcurrentStableDict[str, object]()
    try:
        value = json.loads(raw)
    except TypeError, ValueError:
        return ConcurrentStableDict[str, object]()
    if not isinstance(value, dict):
        return ConcurrentStableDict[str, object]()
    fields = cast("dict[str, object]", value)
    return ConcurrentStableDict({str(key): item for key, item in fields.items()})


def report_key(cache: CacheRegion, tenant: str | None, token: str) -> str:
    """错误明细 token 缓存 key。

    Args:
        cache: 缓存域。
        tenant: 租户编码。
        token: 错误明细 token。

    Returns:
        str: 缓存 key。
    """
    return cache.build_key(f"imports:report:{token}", tenant=tenant)


def token_payload(job_id: int, biz: str) -> ConcurrentStableDict[str, object]:
    """token → 作业映射载荷。

    Args:
        job_id: 作业主键。
        biz: 业务标识。

    Returns:
        ConcurrentStableDict[str, object]: 载荷。
    """
    return ConcurrentStableDict[str, object]({"job_id": job_id, "biz": biz})


def report_filename(title: str) -> str:
    """错误明细文件名。

    Args:
        title: 业务中文名。

    Returns:
        str: 文件名。
    """
    return f"{title}-导入错误明细-{datetime.now(UTC):%Y%m%d%H%M%S}.xlsx"
