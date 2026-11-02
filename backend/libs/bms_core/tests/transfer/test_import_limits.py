"""导入参数测试：默认值 / 参数覆盖 / 非法回落。"""

from __future__ import annotations

import pytest

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.transfer.limits import (
    BATCH_SIZE_KEY,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_ROWS,
    DEFAULT_MAX_SIZE,
    DEFAULT_RATE_LIMIT_LIMIT,
    DEFAULT_SYNC_MAX_ROWS,
    RATE_LIMIT_KEY,
    SYNC_MAX_ROWS_KEY,
    ImportLimits,
)

pytestmark = pytest.mark.kiwi_id(2401)


class _Source(BaseConfigSource):
    """固定值参数源。"""

    def __init__(self, values: ConcurrentStableDict[str, str]) -> None:
        self._values = values

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})


async def test_defaults_without_source() -> None:
    """未接线 / 空源用代码默认。"""
    limits = await ImportLimits.load(None)
    assert limits.max_size == DEFAULT_MAX_SIZE
    assert limits.max_rows == DEFAULT_MAX_ROWS
    assert limits.sync_max_rows == DEFAULT_SYNC_MAX_ROWS
    assert limits.batch_size == DEFAULT_BATCH_SIZE
    assert limits.rate_limit == DEFAULT_RATE_LIMIT_LIMIT


async def test_overrides_and_invalid() -> None:
    """合法值覆盖；非法 / 非正值回落默认。"""
    source = _Source(
        ConcurrentStableDict(
            {
                "import.upload.max_size": "1024",
                SYNC_MAX_ROWS_KEY: "5",
                BATCH_SIZE_KEY: "not-int",
                RATE_LIMIT_KEY: "-1",
            }
        )
    )
    limits = await ImportLimits.load(source)
    assert limits.max_size == 1024
    assert limits.sync_max_rows == 5
    assert limits.batch_size == DEFAULT_BATCH_SIZE
    assert limits.rate_limit == DEFAULT_RATE_LIMIT_LIMIT
