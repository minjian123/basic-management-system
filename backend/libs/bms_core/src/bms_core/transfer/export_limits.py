"""导入导出能力域 · 导出运行期参数（`export.*`）：批量读取 + 代码默认回落。

口径与 `ImportLimits` / `FileLimits` 一致：一次 `get_many` 批量取全部键；缺失 / 非法 / 源不可达一律回落
代码默认，解析失败只 `warning`；缓存由 `BaseConfigSource` 承担，本层不自建缓存。
"""

from __future__ import annotations

from dataclasses import dataclass

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject

__all__ = [
    "ARTIFACT_TTL_KEY",
    "DEFAULT_ARTIFACT_TTL",
    "DEFAULT_FETCH_BATCH_SIZE",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_PDF_SYNC_MAX_DOCS",
    "DEFAULT_PRESIGN_TTL",
    "DEFAULT_RATE_LIMIT_LIMIT",
    "DEFAULT_RATE_LIMIT_WINDOW",
    "DEFAULT_SYNC_MAX_ROWS",
    "FETCH_BATCH_SIZE_KEY",
    "MAX_ROWS_KEY",
    "PDF_SYNC_MAX_DOCS_KEY",
    "PRESIGN_TTL_KEY",
    "RATE_LIMIT_KEY",
    "RATE_LIMIT_WINDOW_KEY",
    "SYNC_MAX_ROWS_KEY",
    "ExportLimits",
]

_LOGGER = get_logger("bms")

SYNC_MAX_ROWS_KEY = "export.sync_max_rows"
"""Excel 同步阈值参数键（行数）。"""

MAX_ROWS_KEY = "export.max_rows"
"""单次导出行数上限参数键。"""

FETCH_BATCH_SIZE_KEY = "export.fetch_batch_size"
"""取数分批大小参数键（同时是进度上报粒度）。"""

RATE_LIMIT_KEY = "export.rate_limit.limit"
"""用户维度限流次数参数键。"""

RATE_LIMIT_WINDOW_KEY = "export.rate_limit.window"
"""用户维度限流窗口参数键（秒）。"""

ARTIFACT_TTL_KEY = "export.artifact_ttl"
"""异步导出产物保留期参数键（秒）。"""

PRESIGN_TTL_KEY = "export.presign_ttl"
"""产物取址有效期参数键（秒）。"""

PDF_SYNC_MAX_DOCS_KEY = "export.pdf.sync_max_docs"
"""PDF 同步份数上限参数键（份 / 行）。"""

DEFAULT_SYNC_MAX_ROWS = 5000
"""Excel 同步阈值代码默认（5000 行）。"""

DEFAULT_MAX_ROWS = 50000
"""单次导出行数上限代码默认（50000 行）。"""

DEFAULT_FETCH_BATCH_SIZE = 500
"""取数分批大小代码默认（500 行）。"""

DEFAULT_RATE_LIMIT_LIMIT = 20
"""用户维度窗口内次数代码默认。"""

DEFAULT_RATE_LIMIT_WINDOW = 60
"""用户维度限流窗口代码默认（60 秒）。"""

DEFAULT_ARTIFACT_TTL = 7 * 24 * 60 * 60
"""产物保留期代码默认（7 天）。"""

DEFAULT_PRESIGN_TTL = 3600
"""产物取址有效期代码默认（1 小时）。"""

DEFAULT_PDF_SYNC_MAX_DOCS = 50
"""PDF 同步份数上限代码默认（50 份）。"""


@dataclass(frozen=True)
class ExportLimits(BaseValueObject):
    """导出生效参数（已解析）。"""

    sync_max_rows: int = DEFAULT_SYNC_MAX_ROWS
    """Excel 同步阈值（行数）。"""

    max_rows: int = DEFAULT_MAX_ROWS
    """单次导出行数上限。"""

    fetch_batch_size: int = DEFAULT_FETCH_BATCH_SIZE
    """取数分批大小。"""

    rate_limit: int = DEFAULT_RATE_LIMIT_LIMIT
    """用户维度窗口内次数。"""

    rate_limit_window: int = DEFAULT_RATE_LIMIT_WINDOW
    """用户维度限流窗口（秒）。"""

    artifact_ttl: int = DEFAULT_ARTIFACT_TTL
    """产物保留期（秒）。"""

    presign_ttl: int = DEFAULT_PRESIGN_TTL
    """产物取址有效期（秒）。"""

    pdf_sync_max_docs: int = DEFAULT_PDF_SYNC_MAX_DOCS
    """PDF 同步份数上限。"""

    @classmethod
    async def load(cls, source: BaseConfigSource | None) -> ExportLimits:
        """从系统参数源加载（源为 None / 不可达 / 值非法时回落代码默认）。

        Args:
            source: 系统参数取数实现（None 表示不接线，全用代码默认）。

        Returns:
            ExportLimits: 生效参数。
        """
        if source is None:
            return cls()
        keys: ConcurrentStableList[str] = ConcurrentStableList(
            (
                SYNC_MAX_ROWS_KEY,
                MAX_ROWS_KEY,
                FETCH_BATCH_SIZE_KEY,
                RATE_LIMIT_KEY,
                RATE_LIMIT_WINDOW_KEY,
                ARTIFACT_TTL_KEY,
                PRESIGN_TTL_KEY,
                PDF_SYNC_MAX_DOCS_KEY,
            )
        )
        values = await source.get_many(keys)
        return cls(
            sync_max_rows=_as_int(values, SYNC_MAX_ROWS_KEY, DEFAULT_SYNC_MAX_ROWS),
            max_rows=_as_int(values, MAX_ROWS_KEY, DEFAULT_MAX_ROWS),
            fetch_batch_size=_as_int(values, FETCH_BATCH_SIZE_KEY, DEFAULT_FETCH_BATCH_SIZE),
            rate_limit=_as_int(values, RATE_LIMIT_KEY, DEFAULT_RATE_LIMIT_LIMIT),
            rate_limit_window=_as_int(values, RATE_LIMIT_WINDOW_KEY, DEFAULT_RATE_LIMIT_WINDOW),
            artifact_ttl=_as_int(values, ARTIFACT_TTL_KEY, DEFAULT_ARTIFACT_TTL),
            presign_ttl=_as_int(values, PRESIGN_TTL_KEY, DEFAULT_PRESIGN_TTL),
            pdf_sync_max_docs=_as_int(values, PDF_SYNC_MAX_DOCS_KEY, DEFAULT_PDF_SYNC_MAX_DOCS),
        )


def _as_int(values: ConcurrentStableDict[str, str], key: str, default: int) -> int:
    """取正整数参数值（缺失 / 非法回落默认）。

    Args:
        values: 参数取值结果。
        key: 参数键。
        default: 代码默认。

    Returns:
        int: 生效值。
    """
    raw = values.get(key)
    if raw is None:
        return default
    try:
        parsed = int(str(raw))
    except TypeError, ValueError:
        _LOGGER.warning("导出参数值非法（回落代码默认）", key=key)
        return default
    if parsed <= 0:
        _LOGGER.warning("导出参数值非正（回落代码默认）", key=key)
        return default
    return parsed
