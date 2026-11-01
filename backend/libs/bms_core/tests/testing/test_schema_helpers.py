"""`ensure_tables` 幂等建表用例（04-6-2）：已存在即通过 / 其它错误照抛 / 缺省建全量。

被测对象是并发建表的**容错口径**：单库化后全 worker 共用一份共享库，多个 worker 同时建同一张表
必然有一方拿到「already exists」——该错误要吞掉（表已由别人建好即是成功），其它 `OperationalError`
（权限 / 磁盘 / 语法）必须照抛，否则会把真实故障静默成「建表成功」。
"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.schema import ensure_tables

pytestmark = pytest.mark.kiwi_id(2400)

_TABLE = cast("Table", SysConfig.__table__)
"""任取一张已登记的表（`ensure_tables` 的入参；建表由 `Table.create` 替身拦下，不真的写库）。"""


def _already_exists(self: Table, bind: object, **kwargs: object) -> None:
    """替身：建表报「已存在」（模拟并发下另一 worker 刚建完）。"""
    del self, bind, kwargs
    raise OperationalError("CREATE TABLE t", {}, RuntimeError("table t already exists"))


def _disk_full(self: Table, bind: object, **kwargs: object) -> None:
    """替身：建表报其它故障（磁盘满）。"""
    del self, bind, kwargs
    raise OperationalError("CREATE TABLE t", {}, RuntimeError("database or disk is full"))


async def test_ensure_tables_swallows_already_exists(
    shared_platform_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发建表撞「已存在」：视为成功，不抛出。"""
    monkeypatch.setattr(Table, "create", _already_exists)
    await ensure_tables(shared_platform_engine, ConcurrentStableList((_TABLE,)))


async def test_ensure_tables_reraises_other_operational_errors(
    shared_platform_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非「已存在」的 `OperationalError`：照抛（不静默降级为成功）。"""
    monkeypatch.setattr(Table, "create", _disk_full)
    with pytest.raises(OperationalError, match="disk is full"):
        await ensure_tables(shared_platform_engine, ConcurrentStableList((_TABLE,)))


async def test_ensure_tables_defaults_to_full_metadata(shared_platform_engine: AsyncEngine) -> None:
    """入参缺省：按 `Base.metadata` 全量并集建表（共享库已建齐，本用例验证缺省分支可走通）。"""
    await ensure_tables(shared_platform_engine)
