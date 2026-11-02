"""导入导出能力域 · 导入运行期参数（`import.*`）：批量读取 + 代码默认回落。

口径与 `FileLimits` 一致：一次 `get_many` 批量取全部键；缺失 / 非法 / 源不可达一律回落代码默认，
解析失败只 `warning`；缓存由 `BaseConfigSource` 承担，本层不自建缓存。
"""

from __future__ import annotations

from dataclasses import dataclass

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject

__all__ = [
    "BATCH_SIZE_KEY",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_ERROR_REPORT_TTL",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_MAX_SIZE",
    "DEFAULT_MAX_UNCOMPRESSED_BYTES",
    "DEFAULT_MAX_ZIP_ENTRIES",
    "DEFAULT_RATE_LIMIT_LIMIT",
    "DEFAULT_RATE_LIMIT_WINDOW",
    "DEFAULT_SYNC_MAX_ROWS",
    "ERROR_REPORT_TTL_KEY",
    "MAX_ROWS_KEY",
    "MAX_SIZE_KEY",
    "MAX_UNCOMPRESSED_BYTES_KEY",
    "MAX_ZIP_ENTRIES_KEY",
    "RATE_LIMIT_KEY",
    "RATE_LIMIT_WINDOW_KEY",
    "SYNC_MAX_ROWS_KEY",
    "ImportLimits",
]

_LOGGER = get_logger("bms")

MAX_SIZE_KEY = "import.upload.max_size"
"""单文件大小上限参数键（字节）。"""

MAX_ROWS_KEY = "import.upload.max_rows"
"""单次数据行上限参数键。"""

SYNC_MAX_ROWS_KEY = "import.sync_max_rows"
"""同步内联阈值参数键。"""

BATCH_SIZE_KEY = "import.batch_size"
"""进度上报 / 取消检查粒度参数键（不是提交粒度）。"""

ERROR_REPORT_TTL_KEY = "import.error_report_ttl"
"""错误明细 token 有效期参数键（秒）。"""

MAX_UNCOMPRESSED_BYTES_KEY = "import.file.max_uncompressed_bytes"
"""zip 解压后总大小上限参数键（字节）。"""

MAX_ZIP_ENTRIES_KEY = "import.file.max_zip_entries"
"""zip 条目数上限参数键。"""

RATE_LIMIT_KEY = "import.rate_limit.limit"
"""用户维度限流次数参数键。"""

RATE_LIMIT_WINDOW_KEY = "import.rate_limit.window"
"""用户维度限流窗口参数键（秒）。"""

DEFAULT_MAX_SIZE = 20 * 1024 * 1024
"""单文件大小代码默认（20MB；与平台默认清单同值）。"""

DEFAULT_MAX_ROWS = 50000
"""单次数据行代码默认（50000；全量原子长事务上界）。"""

DEFAULT_SYNC_MAX_ROWS = 200
"""同步内联阈值代码默认（200 行）。"""

DEFAULT_BATCH_SIZE = 200
"""进度上报 / 取消检查粒度代码默认。"""

DEFAULT_ERROR_REPORT_TTL = 86400
"""错误明细 token 有效期代码默认（86400 秒）。"""

DEFAULT_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
"""zip 解压后总大小代码默认（100MB）。"""

DEFAULT_MAX_ZIP_ENTRIES = 2000
"""zip 条目数代码默认。"""

DEFAULT_RATE_LIMIT_LIMIT = 10
"""用户维度窗口内次数代码默认。"""

DEFAULT_RATE_LIMIT_WINDOW = 60
"""用户维度限流窗口代码默认（60 秒）。"""


@dataclass(frozen=True)
class ImportLimits(BaseValueObject):
    """导入生效参数（已解析；不含文件内容）。"""

    max_size: int = DEFAULT_MAX_SIZE
    """单文件大小上限（字节）。"""

    max_rows: int = DEFAULT_MAX_ROWS
    """单次数据行上限。"""

    sync_max_rows: int = DEFAULT_SYNC_MAX_ROWS
    """同步内联阈值。"""

    batch_size: int = DEFAULT_BATCH_SIZE
    """进度上报 / 取消检查粒度。"""

    error_report_ttl: int = DEFAULT_ERROR_REPORT_TTL
    """错误明细 token 有效期（秒）。"""

    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES
    """zip 解压后总大小上限（字节）。"""

    max_zip_entries: int = DEFAULT_MAX_ZIP_ENTRIES
    """zip 条目数上限。"""

    rate_limit: int = DEFAULT_RATE_LIMIT_LIMIT
    """用户维度窗口内次数。"""

    rate_limit_window: int = DEFAULT_RATE_LIMIT_WINDOW
    """用户维度限流窗口（秒）。"""

    @classmethod
    async def load(cls, source: BaseConfigSource | None) -> ImportLimits:
        """从系统参数源加载（源为 None / 不可达 / 值非法时回落代码默认）。

        Args:
            source: 系统参数取数实现（None 表示不接线，全用代码默认）。

        Returns:
            ImportLimits: 生效参数。
        """
        if source is None:
            return cls()
        keys: ConcurrentStableList[str] = ConcurrentStableList(
            (
                MAX_SIZE_KEY,
                MAX_ROWS_KEY,
                SYNC_MAX_ROWS_KEY,
                BATCH_SIZE_KEY,
                ERROR_REPORT_TTL_KEY,
                MAX_UNCOMPRESSED_BYTES_KEY,
                MAX_ZIP_ENTRIES_KEY,
                RATE_LIMIT_KEY,
                RATE_LIMIT_WINDOW_KEY,
            )
        )
        values = await source.get_many(keys)
        return cls(
            max_size=_as_int(values, MAX_SIZE_KEY, DEFAULT_MAX_SIZE),
            max_rows=_as_int(values, MAX_ROWS_KEY, DEFAULT_MAX_ROWS),
            sync_max_rows=_as_int(values, SYNC_MAX_ROWS_KEY, DEFAULT_SYNC_MAX_ROWS),
            batch_size=_as_int(values, BATCH_SIZE_KEY, DEFAULT_BATCH_SIZE),
            error_report_ttl=_as_int(values, ERROR_REPORT_TTL_KEY, DEFAULT_ERROR_REPORT_TTL),
            max_uncompressed_bytes=_as_int(values, MAX_UNCOMPRESSED_BYTES_KEY, DEFAULT_MAX_UNCOMPRESSED_BYTES),
            max_zip_entries=_as_int(values, MAX_ZIP_ENTRIES_KEY, DEFAULT_MAX_ZIP_ENTRIES),
            rate_limit=_as_int(values, RATE_LIMIT_KEY, DEFAULT_RATE_LIMIT_LIMIT),
            rate_limit_window=_as_int(values, RATE_LIMIT_WINDOW_KEY, DEFAULT_RATE_LIMIT_WINDOW),
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
        _LOGGER.warning("导入参数值非法（回落代码默认）", key=key)
        return default
    if parsed <= 0:
        _LOGGER.warning("导入参数值非正（回落代码默认）", key=key)
        return default
    return parsed
