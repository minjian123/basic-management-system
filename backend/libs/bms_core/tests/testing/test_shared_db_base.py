"""基座共享测试库准备集（通用实现，Kiwi 2413）。

覆盖 `bms_core.testing.shared_db`：默认模型模块清单、平台库 / 租户库准备集（建表 / 种子 /
主键对齐 / 服务目录种子）、建表与并发参数、域派生与布局缺失回退。

本模块自建库属「被测对象就是准备集本身」，故整体进 `own_db` 白名单。
"""

import asyncio
import importlib
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import shared_db as base_shared_db

pytestmark = [pytest.mark.kiwi_id(2413), pytest.mark.own_db("被测对象就是共享库准备集：建表与种子本身")]


def ensure_model_metadata() -> None:
    """确保 `Base.metadata` 已导入基础设施与共享模型（xdist 各 worker 的导入面可能不同）。

    为什么要显式导入：`tenant_metadata` 的建表集来自「元数据 ∩ 域表集」，模型未导入时交集为空，
    断言会随执行顺序（worker 分配）漂移。
    """
    importlib.import_module("bms_core.models.outbox")
    importlib.import_module("bms_core.models.job")
    importlib.import_module("bms_core.models.tenant.tenant")


def test_default_model_modules_covers_base_and_infrastructure() -> None:
    """默认模型清单：含基座基础设施（作业）与共享模型（平台 / 租户 / 系统参数）。"""
    modules = base_shared_db.default_model_modules()
    expected = {"bms_core.models.job", "bms_core.models.outbox", "bms_core.config.models"}
    assert expected <= set(modules)


def test_prepare_platform_without_seed_tenants(tmp_path: Path) -> None:
    """种子租户传空：只建表，不写租户行（也没有服务目录种子）。"""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'platform.db').as_posix()}"
    base_shared_db.prepare_platform(url, model_modules=["bms_core.models.job"], seed_tenant_ids=())
    assert _count(url, "SELECT COUNT(*) FROM sys_tenant") == 0
    assert _count(url, "SELECT COUNT(*) FROM sys_job") == 0
    assert _table_exists(url, "sys_job")


def test_prepare_platform_seeds_tenants_and_catalog(tmp_path: Path) -> None:
    """种子租户 + 主键对齐 + 服务目录种子；重复执行幂等。"""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'platform.db').as_posix()}"
    base_shared_db.prepare_platform(url, seed_catalog=True)
    base_shared_db.prepare_platform(url, seed_catalog=True)
    rows = _query(url, "SELECT code, id FROM sys_tenant WHERE deleted_at IS NULL ORDER BY code")
    padded = {code: str(tenant_id).zfill(38) for code, tenant_id in base_shared_db.SEED_TENANT_IDS}
    assert {row[0]: row[1] for row in rows} == padded
    assert _count(url, "SELECT COUNT(*) FROM sys_module") > 0


async def test_prepare_platform_async_aligns_custom_ids(tmp_path: Path) -> None:
    """异步入口 + 自定义种子主键：`sys_tenant` 与 `sys_tenant_database` 同步对齐。"""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'platform.db').as_posix()}"
    await base_shared_db.prepare_platform_async(url, seed_tenant_ids=(("demo", 7001),))
    rows = await _rows_async(
        url,
        "SELECT (SELECT id FROM sys_tenant WHERE code = 'demo' AND deleted_at IS NULL),"
        " (SELECT tenant_id FROM sys_tenant_database LIMIT 1)",
    )
    expected = str(7001).zfill(38)
    assert [str(cell) for cell in rows[0]] == [expected, expected]


async def test_prepare_tenant_async_with_extra_model_modules(tmp_path: Path) -> None:
    """异步入口 + 额外模型模块：域并集建表并写系统参数（重复执行幂等）。"""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'tenant.db').as_posix()}"
    await base_shared_db.prepare_tenant_async(url, model_modules=["bms_core.models.job"])
    first = await _count_scalar(url, "SELECT COUNT(*) FROM sys_config")
    await base_shared_db.prepare_tenant_async(url)
    assert first > 0
    assert await _count_scalar(url, "SELECT COUNT(*) FROM sys_config") == first


def test_prepare_tenant_uses_known_domains(tmp_path: Path) -> None:
    """`prepare_tenant` 同步入口：`domains` 缺省取本仓已知域（建表 + 参数种子）。"""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'tenant.db').as_posix()}"
    base_shared_db.prepare_tenant(url)
    assert _count(url, "SELECT COUNT(*) FROM sys_config") > 0


def test_tenant_metadata_with_empty_domains() -> None:
    """空域集合：只建基础设施表（不把平台库表建进租户库）。"""
    ensure_model_metadata()
    metadata = base_shared_db.tenant_metadata(())
    names = set(cast("Any", metadata.tables).keys())
    assert names
    assert "sys_tenant" not in names


def test_tenant_metadata_with_explicit_domains() -> None:
    """显式域集合：只取该域的租户库表。"""
    ensure_model_metadata()
    metadata = base_shared_db.tenant_metadata(("tenant",))
    names = set(cast("Any", metadata.tables).keys())
    assert names
    assert "sys_tenant" not in names


def test_tenant_metadata_falls_back_on_layout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """域派生抛 `ConfigError`：回落全模型并集（不静默少建表）。"""
    from bms_core.core.exceptions import ConfigError
    from bms_core.models.base import Base

    def _raise(_domains: object, _datasource: object) -> object:
        raise ConfigError("布局缺失")

    monkeypatch.setattr(base_shared_db, "domains_metadata", _raise)
    assert base_shared_db.tenant_metadata() is Base.metadata


async def test_align_seed_tenant_ids_empty_is_noop(tmp_path: Path) -> None:
    """对齐入口传空序列 / 未登记编码：不执行任何写入（幂等入口可安全传空）。"""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'platform.db').as_posix()}"
    await base_shared_db.prepare_platform_async(url, seed_tenant_ids=())
    await base_shared_db.align_seed_tenant_ids(url, ())
    await base_shared_db.align_seed_tenant_ids(url, (("ghost", 9999),))
    assert await _count_scalar(url, "SELECT COUNT(*) FROM sys_tenant") == 0


async def _count_scalar(url: str, statement: str) -> int:
    """异步取单值（异步用例内不能再 `asyncio.run`）。

    Args:
        url: 连接串。
        statement: 单值 SQL。

    Returns:
        int: 标量值。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int((await connection.execute(text(statement))).scalar_one())
    finally:
        await engine.dispose()


def _count(url: str, statement: str) -> int:
    """同步取单值（同步用例）。

    Args:
        url: 连接串。
        statement: 单值 SQL。

    Returns:
        int: 标量值。
    """
    return asyncio.run(_count_scalar(url, statement))


async def _rows_async(url: str, statement: str) -> ConcurrentStableList[ConcurrentStableList[Any]]:
    """异步执行只读多行查询（异步用例内用）。

    Args:
        url: 连接串。
        statement: SQL 文本。

    Returns:
        ConcurrentStableList[ConcurrentStableList[Any]]: 结果行（每行为单元格列表）。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(statement))
            rows: ConcurrentStableList[ConcurrentStableList[Any]] = ConcurrentStableList()
            for row in result:
                cells: ConcurrentStableList[Any] = ConcurrentStableList()
                for cell in row:
                    cells.add(cell)
                rows.add(cells)
            return rows
    finally:
        await engine.dispose()


def _query(url: str, statement: str) -> ConcurrentStableList[ConcurrentStableList[Any]]:
    """同步执行只读多行查询。

    Args:
        url: 连接串。
        statement: SQL 文本。

    Returns:
        ConcurrentStableList[ConcurrentStableList[Any]]: 结果行（每行为单元格列表）。
    """

    async def _run() -> ConcurrentStableList[ConcurrentStableList[Any]]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text(statement))
                rows: ConcurrentStableList[ConcurrentStableList[Any]] = ConcurrentStableList()
                for row in result:
                    cells: ConcurrentStableList[Any] = ConcurrentStableList()
                    for cell in row:
                        cells.add(cell)
                    rows.add(cells)
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _table_exists(url: str, table: str) -> bool:
    """表是否已建（只读 `sqlite_master`）。

    Args:
        url: 连接串。
        table: 表名。

    Returns:
        bool: 存在为 True。
    """
    rows = _query(url, f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
    return len(rows) == 1
