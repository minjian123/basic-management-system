"""导出参数测试：默认值 / 参数覆盖 / 非法回落。"""

from __future__ import annotations

import pytest

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.transfer.export_limits import (
    ARTIFACT_TTL_KEY,
    DEFAULT_ARTIFACT_TTL,
    DEFAULT_FETCH_BATCH_SIZE,
    DEFAULT_MAX_ROWS,
    DEFAULT_PDF_SYNC_MAX_DOCS,
    DEFAULT_PRESIGN_TTL,
    DEFAULT_RATE_LIMIT_LIMIT,
    DEFAULT_RATE_LIMIT_WINDOW,
    DEFAULT_SYNC_MAX_ROWS,
    FETCH_BATCH_SIZE_KEY,
    MAX_ROWS_KEY,
    PDF_SYNC_MAX_DOCS_KEY,
    RATE_LIMIT_KEY,
    SYNC_MAX_ROWS_KEY,
    ExportLimits,
)

pytestmark = pytest.mark.kiwi_id(2402)


class _Source(BaseConfigSource):
    """固定值参数源。"""

    def __init__(self, values: ConcurrentStableDict[str, str]) -> None:
        self._values = values

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})


async def test_defaults_without_source() -> None:
    """未接线 / 空源用代码默认。"""
    limits = await ExportLimits.load(None)
    assert limits.sync_max_rows == DEFAULT_SYNC_MAX_ROWS
    assert limits.max_rows == DEFAULT_MAX_ROWS
    assert limits.fetch_batch_size == DEFAULT_FETCH_BATCH_SIZE
    assert limits.rate_limit == DEFAULT_RATE_LIMIT_LIMIT
    assert limits.rate_limit_window == DEFAULT_RATE_LIMIT_WINDOW
    assert limits.artifact_ttl == DEFAULT_ARTIFACT_TTL
    assert limits.presign_ttl == DEFAULT_PRESIGN_TTL
    assert limits.pdf_sync_max_docs == DEFAULT_PDF_SYNC_MAX_DOCS


async def test_overrides_and_invalid() -> None:
    """合法值覆盖；非法 / 非正值回落默认。"""
    source = _Source(
        ConcurrentStableDict(
            {
                SYNC_MAX_ROWS_KEY: "100",
                MAX_ROWS_KEY: "2000",
                FETCH_BATCH_SIZE_KEY: "not-int",
                RATE_LIMIT_KEY: "-1",
                ARTIFACT_TTL_KEY: "60",
                PDF_SYNC_MAX_DOCS_KEY: "5",
            }
        )
    )
    limits = await ExportLimits.load(source)
    assert limits.sync_max_rows == 100
    assert limits.max_rows == 2000
    assert limits.fetch_batch_size == DEFAULT_FETCH_BATCH_SIZE
    assert limits.rate_limit == DEFAULT_RATE_LIMIT_LIMIT
    assert limits.artifact_ttl == 60
    assert limits.pdf_sync_max_docs == 5
    assert limits.presign_ttl == DEFAULT_PRESIGN_TTL
