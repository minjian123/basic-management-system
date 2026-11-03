"""打印能力域 · 运行期参数（`print.*`）：批量读取 + 代码默认回落（04_03）。

口径与 `ExportLimits` / `ImportLimits` / `FileLimits` 一致：一次 `get_many` 批量取全部键；
缺失 / 非法 / 源不可达一律回落代码默认，解析失败只 `warning`；缓存由 `BaseConfigSource` 承担。

兼容：`print.pdf.sync_max_docs` 缺失时回退读 `export.pdf.sync_max_docs`（该键为 04_02 期间
打印阈值借用导出段的历史位置，存量租户库可能只有旧键），保证上线后阈值不突变。
"""

from __future__ import annotations

from dataclasses import dataclass

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject

__all__ = [
    "ARTIFACT_TTL_KEY",
    "CLEANUP_BATCH_SIZE_KEY",
    "DEFAULT_ARTIFACT_TTL",
    "DEFAULT_CLEANUP_BATCH_SIZE",
    "DEFAULT_PDF_SYNC_MAX_DOCS",
    "LEGACY_PDF_SYNC_MAX_DOCS_KEY",
    "PDF_SYNC_MAX_DOCS_KEY",
    "PrintLimits",
]

_LOGGER = get_logger("bms")

ARTIFACT_TTL_KEY = "print.artifact_ttl"
"""单据打印产物保留期参数键（秒）。"""

PDF_SYNC_MAX_DOCS_KEY = "print.pdf.sync_max_docs"
"""批量打印同步份数上限参数键（份）。"""

LEGACY_PDF_SYNC_MAX_DOCS_KEY = "export.pdf.sync_max_docs"
"""批量打印同步份数上限的旧参数键（仅回退读取）。"""

CLEANUP_BATCH_SIZE_KEY = "print.cleanup_batch_size"
"""打印产物清理单批作业数参数键。"""

DEFAULT_ARTIFACT_TTL = 7 * 24 * 60 * 60
"""产物保留期代码默认（7 天，与导出产物同口径）。"""

DEFAULT_PDF_SYNC_MAX_DOCS = 50
"""批量打印同步份数上限代码默认（50 份）。"""

DEFAULT_CLEANUP_BATCH_SIZE = 100
"""清理单批作业数代码默认（100 个作业）。"""


@dataclass(frozen=True)
class PrintLimits(BaseValueObject):
    """打印生效参数（已解析）。"""

    artifact_ttl: int = DEFAULT_ARTIFACT_TTL
    """产物保留期（秒）。"""

    pdf_sync_max_docs: int = DEFAULT_PDF_SYNC_MAX_DOCS
    """批量打印同步份数上限。"""

    cleanup_batch_size: int = DEFAULT_CLEANUP_BATCH_SIZE
    """清理单批作业数。"""

    @classmethod
    async def load(cls, source: BaseConfigSource | None) -> PrintLimits:
        """从系统参数源加载（源为 None / 不可达 / 值非法时回落代码默认）。

        Args:
            source: 系统参数取数实现（None 表示不接线，全用代码默认）。

        Returns:
            PrintLimits: 生效参数。
        """
        if source is None:
            return cls()
        keys: ConcurrentStableList[str] = ConcurrentStableList(
            (ARTIFACT_TTL_KEY, PDF_SYNC_MAX_DOCS_KEY, LEGACY_PDF_SYNC_MAX_DOCS_KEY, CLEANUP_BATCH_SIZE_KEY)
        )
        values = await source.get_many(keys)
        return cls(
            artifact_ttl=_as_int(values, ARTIFACT_TTL_KEY, DEFAULT_ARTIFACT_TTL),
            pdf_sync_max_docs=_pdf_sync_max_docs(values),
            cleanup_batch_size=_as_int(values, CLEANUP_BATCH_SIZE_KEY, DEFAULT_CLEANUP_BATCH_SIZE),
        )


def _pdf_sync_max_docs(values: ConcurrentStableDict[str, str]) -> int:
    """取批量打印同步份数上限（新键优先，缺失时回退旧键，再缺失用代码默认）。

    Args:
        values: 参数取值结果。

    Returns:
        int: 生效份数上限。
    """
    for key in (PDF_SYNC_MAX_DOCS_KEY, LEGACY_PDF_SYNC_MAX_DOCS_KEY):
        parsed = _parse_int(values, key)
        if parsed is not None:
            return parsed
        if values.get(key) is not None:
            # 键存在但值非法：不继续回退旧键，直接用默认（避免旧键残留值掩盖配置错误）
            return DEFAULT_PDF_SYNC_MAX_DOCS
    return DEFAULT_PDF_SYNC_MAX_DOCS


def _as_int(values: ConcurrentStableDict[str, str], key: str, default: int) -> int:
    """取正整数参数值（缺失 / 非法回落默认）。

    Args:
        values: 参数取值结果。
        key: 参数键。
        default: 代码默认。

    Returns:
        int: 生效值。
    """
    parsed = _parse_int(values, key)
    return default if parsed is None else parsed


def _parse_int(values: ConcurrentStableDict[str, str], key: str) -> int | None:
    """解析正整数参数（缺失 / 非法 / 非正返回 None，并留 warning）。

    Args:
        values: 参数取值结果。
        key: 参数键。

    Returns:
        int | None: 解析结果；不可用时 None。
    """
    raw = values.get(key)
    if raw is None:
        return None
    try:
        parsed = int(str(raw))
    except TypeError, ValueError:
        _LOGGER.warning("打印参数值非法（回落代码默认）", key=key)
        return None
    if parsed <= 0:
        _LOGGER.warning("打印参数值非正（回落代码默认）", key=key)
        return None
    return parsed
