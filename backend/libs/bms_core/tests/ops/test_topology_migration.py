"""拓扑迁移搬运与对账内核用例（07C `04_02`）：复制幂等、断点续传、失败截断、四类对账、进度文件。

用合成表集（不依赖任何业务域模型）锁内核行为；真库（MySQL / PostgreSQL / DM8）路径归部署窗口复验。
Kiwi 用例编号未取得，本轮不登记（见实施记录遗留）。
"""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert

import bms_core.db.topology_migration as kernel
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import ConfigError


def _metadata(*, composite: bool = False, with_key: bool = True) -> MetaData:
    """构造合成表集（父表 + 子表，列覆盖整型主键与文本列）。

    Args:
        composite: 是否把子表主键做成复合主键。
        with_key: 是否给子表主键（False 用于「无主键」反例）。

    Returns:
        MetaData: 表集元数据。
    """
    metadata = MetaData()
    Table(
        "demo_role",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(32), nullable=False),
    )
    key_columns = [Column("id", Integer, primary_key=True)]
    if composite:
        key_columns.append(Column("line", Integer, primary_key=True))
    if with_key:
        Table("demo_role_line", metadata, *key_columns, Column("label", String(32), nullable=False))
    else:
        Table("demo_role_line", metadata, Column("id", Integer), Column("label", String(32), nullable=False))
    return metadata


def _url(path: Path) -> str:
    """把库文件路径转异步 SQLite 连接串。

    Args:
        path: 库文件路径。

    Returns:
        str: 连接串。
    """
    return f"sqlite+aiosqlite:///{path}"


def _always_sync(url: str) -> bool:
    """替身：把所有连接串判为「仅同步方言」（锁同步门面适配层）。

    Args:
        url: 连接串（忽略）。

    Returns:
        bool: 恒 True。
    """
    del url
    return True


def _seed(path: Path, metadata: MetaData, *, roles: int = 3) -> None:
    """建表并写入种子数据（本地同步引擎，模拟源库现状）。

    Args:
        path: 库文件路径。
        metadata: 表集元数据。
        roles: 父表行数。
    """
    engine = create_engine(f"sqlite:///{path}")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                insert(metadata.tables["demo_role"]),
                [{"id": index, "name": f"role-{index}"} for index in range(1, roles + 1)],
            )
            line_rows = {"line": 0} if "line" in metadata.tables["demo_role_line"].columns else {}
            connection.execute(
                insert(metadata.tables["demo_role_line"]),
                [{"id": index, "label": f"line-{index}", **line_rows} for index in range(1, roles + 1)],
            )
    finally:
        engine.dispose()


def _tables(path: Path, metadata: MetaData) -> None:
    """只建表不写数据（目标库初态）。

    Args:
        path: 库文件路径。
        metadata: 表集元数据。
    """
    engine = create_engine(f"sqlite:///{path}")
    try:
        metadata.create_all(engine)
    finally:
        engine.dispose()


def _rows(path: Path, table: str) -> ConcurrentStableList[ConcurrentStableFrozenList[object]]:
    """读某表全部行（断言用）。

    Args:
        path: 库文件路径。
        table: 表名。

    Returns:
        ConcurrentStableList[ConcurrentStableFrozenList[object]]: 逐行（按首列序）。
    """
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as connection:
            return ConcurrentStableList(
                ConcurrentStableFrozenList(row)
                for row in connection.exec_driver_sql(f"SELECT * FROM {table} ORDER BY 1").all()
            )
    finally:
        engine.dispose()


def _pairs(path: Path, table: str) -> ConcurrentStableList[object]:
    """读某表前两列（断言用，避免在签名里出现裸集合）。

    Args:
        path: 库文件路径。
        table: 表名。

    Returns:
        ConcurrentStableList[object]: 前两列元组列表。
    """
    return ConcurrentStableList((row[0], row[1]) for row in _rows(path, table))


async def test_copy_is_idempotent_and_verifies(tmp_path: Path) -> None:
    """复制后行数一致、对账全绿；重复复制不产生重复行（主键删旧插新）。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata)
    _tables(target, metadata)

    first = await kernel.copy_tables(_url(source), _url(target), metadata, batch_size=2)
    assert first.passed and first.total_rows == 6
    assert _rows(target, "demo_role") == _rows(source, "demo_role")

    again = await kernel.copy_tables(_url(source), _url(target), metadata, batch_size=2)
    assert again.passed and again.total_rows == 6
    assert len(_rows(target, "demo_role")) == 3, "重复复制不新增行"

    report = await kernel.verify_tables(_url(source), _url(target), metadata, batch_size=2)
    assert report.passed, report.tables
    assert {item.table for item in report.tables} == {"demo_role", "demo_role_line"}
    assert all(item.source_rows == item.target_rows == 3 for item in report.tables)


async def test_copy_resumes_from_progress(tmp_path: Path) -> None:
    """断点续传：进度记录末值后只搬剩余行；已完成表整表跳过。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata, roles=4)
    _tables(target, metadata)
    progress = kernel.MigrationProgress.load(tmp_path / "progress.json")
    progress.mark("demo_role", cursor=2)
    progress.mark("demo_role_line", done=True)

    report = await kernel.copy_tables(_url(source), _url(target), metadata, batch_size=2, progress=progress)
    assert report.passed
    by_table = {item.table: item for item in report.tables}
    assert by_table["demo_role"].copied == 2, "只搬主键 > 2 的行"
    assert by_table["demo_role"].resumed is True
    assert by_table["demo_role_line"].skipped is True
    assert _pairs(target, "demo_role") == [(3, "role-3"), (4, "role-4")]
    assert progress.completed("demo_role") and progress.completed("demo_role_line")


async def test_copy_truncates_on_failure(tmp_path: Path) -> None:
    """目标缺表：该表失败即截断后续表，报告含错误且判定未通过。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata)

    report = await kernel.copy_tables(_url(source), _url(target), metadata)
    assert not report.passed
    assert [item.table for item in report.failed] == ["demo_role"], "第一张表失败即截断"
    assert "OperationalError" in report.failed[0].error


async def test_verify_reports_missing_and_mismatch(tmp_path: Path) -> None:
    """对账：缺行计 missing、内容不一致列出差异主键。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata)
    _tables(target, metadata)
    await kernel.copy_tables(_url(source), _url(target), metadata)
    engine = create_engine(f"sqlite:///{target}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM demo_role WHERE id = 3")
            connection.exec_driver_sql("UPDATE demo_role SET name = 'tampered' WHERE id = 1")
    finally:
        engine.dispose()

    report = await kernel.verify_tables(_url(source), _url(target), metadata, sample_size=10)
    role = next(item for item in report.tables if item.table == "demo_role")
    assert role.missing == 1 and role.source_rows == 3 and role.target_rows == 2
    assert "1" in role.mismatched
    assert not report.passed


async def test_verify_reports_extra_and_missing_table(tmp_path: Path) -> None:
    """对账：目标多出行计 extra；目标缺表整体判失败（missing 记全量）。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata)
    _tables(target, metadata)
    await kernel.copy_tables(_url(source), _url(target), metadata)
    engine = create_engine(f"sqlite:///{target}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO demo_role (id, name) VALUES (99, 'extra')")
    finally:
        engine.dispose()
    report = await kernel.verify_tables(_url(source), _url(target), metadata)
    role = next(item for item in report.tables if item.table == "demo_role")
    assert role.extra == 1 and role.missing == 0
    assert not report.passed, "行数不等即不通过"

    empty = tmp_path / "empty.db"
    report_missing = await kernel.verify_tables(_url(source), _url(empty), metadata)
    assert all(not item.exists for item in report_missing.tables)
    assert report_missing.tables[0].missing == report_missing.tables[0].source_rows
    assert not report_missing.passed


async def test_verify_business_assertions(tmp_path: Path) -> None:
    """业务断言：数值按差额、非数值按文本；两侧比对结果进报告。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata)
    _tables(target, metadata)
    await kernel.copy_tables(_url(source), _url(target), metadata)

    assertions = ConcurrentStableList(
        [
            kernel.BusinessAssertion(name="行数", sql="SELECT COUNT(*) FROM demo_role"),
            kernel.BusinessAssertion(name="宽口径", sql="SELECT COUNT(*) FROM demo_role", tolerance=5),
            kernel.BusinessAssertion(name="名称", sql="SELECT name FROM demo_role WHERE id = 1"),
        ]
    )
    report = await kernel.verify_tables(_url(source), _url(target), metadata, assertions=assertions)
    assert [item.ok for item in report.assertions] == [True, True, True]
    assert report.assertions[0].source == "3"

    engine = create_engine(f"sqlite:///{source}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO demo_role (id, name) VALUES (4, 'role-4')")
    finally:
        engine.dispose()
    drifted = await kernel.verify_tables(_url(source), _url(target), metadata, assertions=assertions)
    assert [item.ok for item in drifted.assertions] == [False, True, True], "差 1 行：0 容差失败、5 容差放行"


async def test_count_rows_and_sync_dialect_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """行数统计；仅同步方言走同步门面（以 SQLite 同步连接串锁适配层）。"""
    metadata = _metadata()
    source = tmp_path / "source.db"
    _seed(source, metadata, roles=2)
    counts = await kernel.count_rows(_url(source), metadata)
    assert counts.to_dict() == {"demo_role": 2, "demo_role_line": 2}

    empty = tmp_path / "empty.db"
    assert (await kernel.count_rows(_url(empty), metadata)).to_dict() == {"demo_role": 0, "demo_role_line": 0}

    target = tmp_path / "sync_target.db"
    _tables(target, metadata)
    monkeypatch.setattr(kernel, "is_sync_only_url", _always_sync)
    report = await kernel.copy_tables(f"sqlite:///{source}", f"sqlite:///{target}", metadata)
    assert report.passed and report.total_rows == 4
    assert _rows(target, "demo_role") == _rows(source, "demo_role")
    verified = await kernel.verify_tables(
        f"sqlite:///{source}",
        f"sqlite:///{target}",
        metadata,
        assertions=ConcurrentStableList(
            [
                kernel.BusinessAssertion(name="行数", sql="SELECT COUNT(*) FROM demo_role"),
                kernel.BusinessAssertion(name="文本数值", sql="SELECT '2'"),
                kernel.BusinessAssertion(name="空值", sql="SELECT NULL"),
            ]
        ),
    )
    assert verified.passed, "同步门面的标量查询与数值解析同口径"

    assert (await kernel.count_rows(f"sqlite:///{source}", metadata)).to_dict() == {"demo_role": 2, "demo_role_line": 2}


def test_table_targets_rejects_table_without_primary_key() -> None:
    """无主键表：无法按主键幂等写入，直接拒绝（不静默降级）。"""
    metadata = _metadata(with_key=False)
    with pytest.raises(ConfigError, match="没有主键"):
        kernel.table_targets(metadata)


async def test_copy_rejects_composite_primary_key(tmp_path: Path) -> None:
    """复合主键：按首列游标会跨批漏行，复制前即拒绝。"""
    metadata = _metadata(composite=True)
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata)
    _tables(target, metadata)
    with pytest.raises(ConfigError, match="复合主键"):
        await kernel.copy_tables(_url(source), _url(target), metadata)


def test_progress_file_roundtrip_and_invalid(tmp_path: Path) -> None:
    """进度文件：落盘可回读；结构非法即报错；游标不可 JSON 表示时丢弃（下次从头重跑）。"""
    path = tmp_path / "progress.json"
    progress = kernel.MigrationProgress.load(path)
    assert progress.cursor("demo_role") is None and not progress.completed("demo_role")
    progress.mark("demo_role", cursor=7)
    progress.save()

    reloaded = kernel.MigrationProgress.load(path)
    assert reloaded.cursor("demo_role") == 7
    assert not reloaded.completed("demo_role")

    reloaded.mark("demo_role", cursor=object(), done=True)
    assert reloaded.cursor("demo_role") is None, "不可序列化的游标丢弃"
    assert reloaded.completed("demo_role")

    broken = tmp_path / "broken.json"
    broken.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="结构非法"):
        kernel.MigrationProgress.load(broken)

    bad_entry = tmp_path / "bad_entry.json"
    bad_entry.write_text('{"tables": {"demo_role": 1}}', encoding="utf-8")
    with pytest.raises(ConfigError, match="条目非法"):
        kernel.MigrationProgress.load(bad_entry)


def test_rate_limit_and_small_sample(tmp_path: Path) -> None:
    """限速与抽样边界：每批休眠、抽样步长 > 1 时跳过非抽样行。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata, roles=3)
    _tables(target, metadata)

    report = asyncio.run(
        kernel.copy_tables(_url(source), _url(target), metadata, batch_size=1, rate_limit_seconds=0.001)
    )
    assert report.passed and report.total_rows == 6

    verified = asyncio.run(kernel.verify_tables(_url(source), _url(target), metadata, sample_size=1))
    assert verified.passed
    assert sum(item.sampled for item in verified.tables) <= 2, "单表抽样上限 1 条"


def test_sync_gateway_edge_cases(tmp_path: Path) -> None:
    """同步门面边界：空取值集合不查、空行集不写、标量查询可用（达梦路径的复用件）。"""
    metadata = _metadata()
    path = tmp_path / "source.db"
    _seed(path, metadata, roles=1)
    table = metadata.tables["demo_role"]
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as connection:
            assert kernel._fetch_sync(connection, table, "id", ConcurrentStableList()) == []  # pyright: ignore[reportPrivateUsage]
            kernel._upsert_sync(connection, table, "id", ConcurrentStableList())  # pyright: ignore[reportPrivateUsage]
            assert kernel._scalar_sync(connection, "SELECT COUNT(*) FROM demo_role") == 1  # pyright: ignore[reportPrivateUsage]
    finally:
        engine.dispose()


def test_progress_rejects_invalid_tables_node(tmp_path: Path) -> None:
    """进度文件结构非法（`tables` 不是映射）即报错。"""
    path = tmp_path / "bad.json"
    path.write_text('{"tables": 1}', encoding="utf-8")
    with pytest.raises(ConfigError, match="结构非法"):
        kernel.MigrationProgress.load(path)


def test_assertion_text_values_are_compared_as_text(tmp_path: Path) -> None:
    """非数值断言按文本比较（覆盖数值解析失败分支）。"""
    metadata = _metadata()
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    _seed(source, metadata, roles=1)
    _tables(target, metadata)
    asyncio.run(kernel.copy_tables(_url(source), _url(target), metadata))
    report = asyncio.run(
        kernel.verify_tables(
            _url(source),
            _url(target),
            metadata,
            assertions=ConcurrentStableList(
                [kernel.BusinessAssertion(name="名称", sql="SELECT name FROM demo_role WHERE id = 1")]
            ),
        )
    )
    assert report.passed
