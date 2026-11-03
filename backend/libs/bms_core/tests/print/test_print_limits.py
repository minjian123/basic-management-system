"""打印参数测试（04_03）：默认值 / 新键覆盖 / 旧键回退 / 非法回落。"""

from __future__ import annotations

import pytest

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.print.limits import (
    ARTIFACT_TTL_KEY,
    CLEANUP_BATCH_SIZE_KEY,
    DEFAULT_ARTIFACT_TTL,
    DEFAULT_CLEANUP_BATCH_SIZE,
    DEFAULT_PDF_SYNC_MAX_DOCS,
    LEGACY_PDF_SYNC_MAX_DOCS_KEY,
    PDF_SYNC_MAX_DOCS_KEY,
    PrintLimits,
)

pytestmark = pytest.mark.kiwi_id(2403)


class _Source(BaseConfigSource):
    """固定值参数源（只返回请求到的键）。"""

    def __init__(self, values: ConcurrentStableDict[str, str]) -> None:
        """初始化。

        Args:
            values: 键值表。
        """
        self._values = values

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """按请求键返回已有值。

        Args:
            keys: 请求键。

        Returns:
            ConcurrentStableDict[str, str]: 命中的键值。
        """
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})


def _source(**values: str) -> _Source:
    """构造参数源。

    Args:
        **values: 键值对。

    Returns:
        _Source: 参数源。
    """
    return _Source(ConcurrentStableDict(values))


async def test_defaults_without_source() -> None:
    """未接线（None）：三个参数全部取代码默认。"""
    limits = await PrintLimits.load(None)
    assert limits.artifact_ttl == DEFAULT_ARTIFACT_TTL
    assert limits.pdf_sync_max_docs == DEFAULT_PDF_SYNC_MAX_DOCS
    assert limits.cleanup_batch_size == DEFAULT_CLEANUP_BATCH_SIZE


async def test_empty_source_falls_back_to_defaults() -> None:
    """空源（无任何键）：同样回落默认。"""
    limits = await PrintLimits.load(_source())
    assert limits.artifact_ttl == DEFAULT_ARTIFACT_TTL
    assert limits.pdf_sync_max_docs == DEFAULT_PDF_SYNC_MAX_DOCS
    assert limits.cleanup_batch_size == DEFAULT_CLEANUP_BATCH_SIZE


async def test_values_from_source() -> None:
    """三键齐备：全部按配置生效。"""
    limits = await PrintLimits.load(
        _source(**{ARTIFACT_TTL_KEY: "3600", PDF_SYNC_MAX_DOCS_KEY: "5", CLEANUP_BATCH_SIZE_KEY: "20"})
    )
    assert limits.artifact_ttl == 3600
    assert limits.pdf_sync_max_docs == 5
    assert limits.cleanup_batch_size == 20


async def test_pdf_sync_max_docs_falls_back_to_legacy_key() -> None:
    """新键缺失、旧键有值：取旧键（存量租户库只有 export.pdf.sync_max_docs）。"""
    limits = await PrintLimits.load(_source(**{LEGACY_PDF_SYNC_MAX_DOCS_KEY: "8"}))
    assert limits.pdf_sync_max_docs == 8


async def test_pdf_sync_max_docs_prefers_new_key() -> None:
    """两键都有值：新键优先。"""
    limits = await PrintLimits.load(_source(**{PDF_SYNC_MAX_DOCS_KEY: "3", LEGACY_PDF_SYNC_MAX_DOCS_KEY: "99"}))
    assert limits.pdf_sync_max_docs == 3


async def test_pdf_sync_max_docs_invalid_new_key_does_not_fall_back() -> None:
    """新键存在但非法：回落代码默认，不再读旧键（避免旧值掩盖配置错误）。"""
    limits = await PrintLimits.load(_source(**{PDF_SYNC_MAX_DOCS_KEY: "abc", LEGACY_PDF_SYNC_MAX_DOCS_KEY: "99"}))
    assert limits.pdf_sync_max_docs == DEFAULT_PDF_SYNC_MAX_DOCS


async def test_pdf_sync_max_docs_invalid_legacy_key() -> None:
    """新键缺失、旧键非法：回落代码默认。"""
    limits = await PrintLimits.load(_source(**{LEGACY_PDF_SYNC_MAX_DOCS_KEY: "-1"}))
    assert limits.pdf_sync_max_docs == DEFAULT_PDF_SYNC_MAX_DOCS


async def test_invalid_and_non_positive_values_fall_back() -> None:
    """非法字符串与非正数：回落代码默认（保留期与批大小）。"""
    limits = await PrintLimits.load(_source(**{ARTIFACT_TTL_KEY: "not-a-number", CLEANUP_BATCH_SIZE_KEY: "0"}))
    assert limits.artifact_ttl == DEFAULT_ARTIFACT_TTL
    assert limits.cleanup_batch_size == DEFAULT_CLEANUP_BATCH_SIZE
