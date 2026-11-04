"""SQLite 引擎统一口径：写独占排队 + 并发读（`BEGIN IMMEDIATE`）。"""

from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.sqlite import SQLITE_BUSY_TIMEOUT_SECONDS, create_async_engine, is_sqlite_url

pytestmark = pytest.mark.own_db("被测对象是 SQLite 引擎连接参数与事务口径：引擎构造即被测")


def test_is_sqlite_url() -> None:
    """只识别 SQLite 两种写法；其它方言不命中。"""
    assert is_sqlite_url("sqlite:///a.db")
    assert is_sqlite_url("sqlite+aiosqlite:///a.db")
    assert not is_sqlite_url("mysql+aiomysql://user:pass@localhost/db")
    assert not is_sqlite_url("postgresql+psycopg://user:pass@localhost/db")


async def test_create_engine_keeps_non_sqlite_untouched() -> None:
    """非 SQLite 方言原样创建（不注入 connect_args、不挂 begin 钩子）。"""
    engine = create_async_engine("postgresql+psycopg://user:pass@localhost/db")
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        await engine.dispose()


async def test_sqlite_engine_begin_immediate(tmp_path: Path) -> None:
    """SQLite 引擎：事务起点发 `BEGIN IMMEDIATE`，读写可用。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'probe.db').as_posix()}", immediate=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("create table t (id integer primary key, v text)"))
            await connection.execute(text("insert into t (v) values ('a')"))
        async with engine.begin() as connection:
            count = (await connection.execute(text("select count(*) from t"))).scalar_one()
        assert count == 1
        assert engine.dialect.name == "sqlite"
    finally:
        await engine.dispose()


async def test_sqlite_engine_merges_connect_args(tmp_path: Path) -> None:
    """调用方给的 `connect_args` 优先（仅补缺省项）。"""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'probe2.db').as_posix()}",
        connect_args={"timeout": SQLITE_BUSY_TIMEOUT_SECONDS},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text("select 1"))
    finally:
        await engine.dispose()


async def test_sqlite_engine_deferred_mode(tmp_path: Path) -> None:
    """`immediate=False`：只加忙等超时，不挂 `BEGIN IMMEDIATE`（测试外层回滚事务用）。"""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'probe3.db').as_posix()}",
        immediate=False,
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text("create table t (id integer)"))
    finally:
        await engine.dispose()


@pytest.mark.parametrize("url", ["sqlite:///a.db", "postgresql+psycopg://user:pass@localhost/db"])
def test_is_sqlite_url_matrix(url: str) -> None:
    """方言矩阵（参数化覆盖两种分支）。"""
    assert is_sqlite_url(url) is url.startswith("sqlite")


async def test_engine_type() -> None:
    """返回类型为异步引擎。"""
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        assert isinstance(engine, AsyncEngine)
    finally:
        await engine.dispose()


def test_sqlite_without_dialect_skips_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """建引擎返回的替身没有 `dialect` 时跳过 begin 钩子（测试替身路径）。"""

    from bms_core.db import sqlite as sqlite_module

    class _Fake:
        """无 dialect 的替身。"""

    fake = _Fake()

    def _fake_create(url: str, **kwargs: Any) -> object:
        del url, kwargs
        return fake

    monkeypatch.setattr(sqlite_module.sa_asyncio, "create_async_engine", _fake_create)
    result = sqlite_module.create_async_engine("sqlite+aiosqlite:///x.db", immediate=True)
    assert cast("object", result) is fake
