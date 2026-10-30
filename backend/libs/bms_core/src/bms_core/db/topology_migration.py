"""租户拓扑迁移的搬运与对账内核（07C `04_02`）：按业务域表集跨库复制 + 四类对账。

口径（详细设计 §3.3 / §3.4 / §3.8）：

- **表集单一来源**：搬迁表集 = `services/table_registry.series_tables(domain, datasource)`（与清单 / 建表同源），
  基础设施表（发件箱三表）每库一份、不随域搬迁，故不进搬迁表集；
- **幂等**：目标侧按主键 `DELETE` + `INSERT`（跨方言无统一 UPSERT 语法），同一批重跑结果一致；
- **分页**：按**单列主键**游标（`pk > 上一批末值`）分批；复合主键不支持（按首列游标会跨批漏行，`ConfigError`）；
- **断点**：进度按「表 → 已完成的最后一批主键值 + 是否完成」记到 JSON 文件，`--resume` 从该值之后续跑；
- **对账四类**：行数 / 主键覆盖（源−目标与目标−源）/ 抽样内容比对 / 关键业务断言；
- **方言**：异步驱动走 `AsyncConnection.run_sync`，仅同步方言（达梦）走同步连接 + 线程池；
  SQL 逻辑只有一份（`_*_sync` 纯函数），两种连接只是薄适配。
"""

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Connection, MetaData, Select, Table, create_engine, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.sync import is_sync_only_url

__all__ = [
    "SAMPLE_SIZE",
    "TABLE_BATCH_SIZE",
    "AssertionResult",
    "AsyncTableGateway",
    "BusinessAssertion",
    "CopyReport",
    "MigrationProgress",
    "SyncTableGateway",
    "TableCopyResult",
    "TableTarget",
    "TableVerifyResult",
    "VerifyReport",
    "copy_tables",
    "count_rows",
    "table_targets",
    "verify_tables",
]

TABLE_BATCH_SIZE = 500
"""单批复制行数（主键游标分页；同时受目标方言绑定变量上限约束，500 对 SQLite 的 999 上限安全）。"""

SAMPLE_SIZE = 200
"""单表抽样比对条数上限（按行号等距抽样，覆盖首尾与中段）。"""


@dataclass(frozen=True)
class TableTarget(BaseValueObject):
    """单张搬迁表（表名 + 主键列序）。"""

    name: str
    """表名。"""

    primary_key: ConcurrentStableFrozenList[str]
    """主键列（顺序同表定义）；复制与对账只用首列作游标，故要求单列。"""


@dataclass(frozen=True)
class TableCopyResult(BaseValueObject):
    """单表复制结果（行数 + 断点起点 + 失败原因）。"""

    table: str
    """表名。"""

    copied: int
    """本次复制行数（断点续跑时只计续跑部分）。"""

    resumed: bool
    """是否从断点续跑（True 表示前面已有批次完成）。"""

    skipped: bool
    """是否整表跳过（上次已标记完成）。"""

    error: str = ""
    """失败原因（空串表示成功）。"""


@dataclass(frozen=True)
class CopyReport(BaseValueObject):
    """复制结果汇总（逐表一行；任一行有 error 即判定未通过）。"""

    tables: ConcurrentStableList[TableCopyResult]
    """逐表结果（按表集顺序）。"""

    @property
    def total_rows(self) -> int:
        """复制总行数。

        Returns:
            int: 各表复制行数之和。
        """
        return sum(result.copied for result in self.tables)

    @property
    def failed(self) -> ConcurrentStableList[TableCopyResult]:
        """失败的表。

        Returns:
            ConcurrentStableList[TableCopyResult]: 有 error 的逐表结果。
        """
        return ConcurrentStableList(result for result in self.tables if result.error)

    @property
    def passed(self) -> bool:
        """是否全部成功。

        Returns:
            bool: 无失败表为 True。
        """
        return not self.failed


@dataclass(frozen=True)
class TableVerifyResult(BaseValueObject):
    """单表对账结果（行数 / 主键覆盖 / 抽样比对）。"""

    table: str
    """表名。"""

    exists: bool
    """目标库是否存在该表。"""

    source_rows: int
    """源库行数。"""

    target_rows: int
    """目标库行数（表不存在时为 0）。"""

    missing: int
    """源有目标无的主键数（应为 0）。"""

    extra: int
    """目标有源无的主键数（切换后新库写入时可能非 0，须书面说明）。"""

    sampled: int
    """抽样比对条数。"""

    mismatched: ConcurrentStableList[str]
    """抽样不一致的主键（文本形态，便于日志检索）。"""

    @property
    def ok(self) -> bool:
        """单表是否通过（表存在 + 行数相等 + 主键覆盖 + 抽样一致）。

        Returns:
            bool: 通过为 True。
        """
        return self.exists and self.source_rows == self.target_rows and not self.missing and not self.mismatched


@dataclass(frozen=True)
class BusinessAssertion(BaseValueObject):
    """关键业务断言（同一 SQL 在源库与目标库各取一个标量比对）。"""

    name: str
    """断言名（报告与日志用）。"""

    sql: str
    """标量查询语句（两侧各执行一次）。"""

    tolerance: int = 0
    """数值型允许差额（非数值按字符串相等判定）。"""


@dataclass(frozen=True)
class AssertionResult(BaseValueObject):
    """单条业务断言结果。"""

    name: str
    """断言名。"""

    source: str
    """源库取值（文本形态）。"""

    target: str
    """目标库取值（文本形态）。"""

    ok: bool
    """是否一致。"""


@dataclass(frozen=True)
class VerifyReport(BaseValueObject):
    """对账报告（逐表结果 + 业务断言）。"""

    tables: ConcurrentStableList[TableVerifyResult]
    """逐表结果。"""

    assertions: ConcurrentStableList[AssertionResult]
    """业务断言结果（未配置时为空）。"""

    @property
    def failed_tables(self) -> ConcurrentStableList[TableVerifyResult]:
        """未通过的表。

        Returns:
            ConcurrentStableList[TableVerifyResult]: 未通过的单表结果。
        """
        return ConcurrentStableList(result for result in self.tables if not result.ok)

    @property
    def passed(self) -> bool:
        """是否全部通过（P4 全绿才允许 P5）。

        Returns:
            bool: 逐表通过且断言全过为 True。
        """
        return not self.failed_tables and all(item.ok for item in self.assertions)


def _empty_entries() -> ConcurrentStableDict[str, ConcurrentStableDict[str, object]]:
    """空进度表（`field` 工厂需带类型参数，避免字段类型退化为 Unknown）。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableDict[str, object]]: 空映射。
    """
    return ConcurrentStableDict()


@dataclass
class MigrationProgress:
    """文件型迁移进度（断点续跑 + 审计留痕的最小载体；落库见设计 §7 开放项 2）。"""

    path: Path
    """进度文件路径（JSON）。"""

    entries: ConcurrentStableDict[str, ConcurrentStableDict[str, object]] = field(default_factory=_empty_entries)
    """逐表进度：表名 → `{cursor, done}`。"""

    @classmethod
    def load(cls, path: Path) -> MigrationProgress:
        """读进度文件（不存在按空进度处理）。

        Args:
            path: 进度文件路径。

        Returns:
            MigrationProgress: 进度对象。

        Raises:
            ConfigError: 文件存在但内容不是预期结构。
        """
        if not path.is_file():
            return cls(path=path)
        raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
        if not isinstance(raw, dict):
            raise ConfigError(f"迁移进度文件结构非法：{path}")
        tables = cast("dict[str, object]", raw).get("tables")
        if not isinstance(tables, dict):
            raise ConfigError(f"迁移进度文件结构非法：{path}")
        entries: ConcurrentStableDict[str, ConcurrentStableDict[str, object]] = ConcurrentStableDict()
        for name, payload in cast("dict[str, object]", tables).items():
            if not isinstance(payload, dict):
                raise ConfigError(f"迁移进度文件条目非法：{name}")
            entries.set(name, ConcurrentStableDict(cast("dict[str, object]", payload)))
        return cls(path=path, entries=entries)

    def save(self) -> None:
        """落盘（父目录按需创建）。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tables": {name: dict(value) for name, value in self.entries.items()}}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def cursor(self, table: str) -> object | None:
        """取该表已完成的最后一批主键值。

        Args:
            table: 表名。

        Returns:
            object | None: 主键值（未记录为 None）。
        """
        entry = self.entries.get(table)
        return None if entry is None else entry.get("cursor")

    def completed(self, table: str) -> bool:
        """该表是否已复制完成。

        Args:
            table: 表名。

        Returns:
            bool: 已完成 True。
        """
        entry = self.entries.get(table)
        return bool(entry is not None and entry.get("done"))

    def mark(self, table: str, *, cursor: object | None = None, done: bool = False) -> None:
        """记录该表进度（内存；`save` 才落盘）。

        Args:
            table: 表名。
            cursor: 已完成区间末值（单列主键值）。
            done: 是否整表完成。
        """
        entry: ConcurrentStableDict[str, object] | None = self.entries.get(table)
        if entry is None:
            entry = ConcurrentStableDict[str, object]()
            self.entries.set(table, entry)
        entry.set("cursor", _json_safe(cursor))
        entry.set("done", done)


class TableGateway(ABC):
    """表级读写门面（异步连接与同步连接各一实现，SQL 逻辑只有一份）。"""

    @abstractmethod
    async def exists(self, table: Table) -> bool:
        """目标库是否存在该表。

        Args:
            table: 表定义。

        Returns:
            bool: 存在 True。
        """

    @abstractmethod
    async def count(self, table: Table) -> int:
        """表行数。

        Args:
            table: 表定义。

        Returns:
            int: 行数。
        """

    @abstractmethod
    async def page(
        self, table: Table, column: str, after: object | None, limit: int
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按游标列取一页（`column > after` 升序）。

        Args:
            table: 表定义。
            column: 游标列名。
            after: 上一页末值（None 表示从头）。
            limit: 单页上限。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
        """

    @abstractmethod
    async def fetch(
        self, table: Table, column: str, values: ConcurrentStableList[object]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按列取值集合取行（`column IN values`）。

        Args:
            table: 表定义。
            column: 过滤列名。
            values: 取值集合。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
        """

    @abstractmethod
    async def upsert(
        self, table: Table, column: str, rows: ConcurrentStableList[ConcurrentStableDict[str, object]]
    ) -> None:
        """按主键列删旧插新（一批一事务）。

        Args:
            table: 表定义。
            column: 主键列名。
            rows: 待写入行。
        """

    @abstractmethod
    async def scalar(self, sql: str) -> object:
        """执行标量查询。

        Args:
            sql: 查询语句。

        Returns:
            object: 首行首列值。
        """


class AsyncTableGateway(TableGateway):
    """异步连接实现（`aiosqlite` / `aiomysql` / `asyncpg`）。"""

    def __init__(self, connection: AsyncConnection) -> None:
        """初始化。

        Args:
            connection: 异步连接。
        """
        self._connection = connection

    async def exists(self, table: Table) -> bool:
        """目标库是否存在该表。

        Args:
            table: 表定义。

        Returns:
            bool: 存在 True。
        """
        return await self._connection.run_sync(_exists_sync, table)

    async def count(self, table: Table) -> int:
        """表行数。

        Args:
            table: 表定义。

        Returns:
            int: 行数。
        """
        return await self._connection.run_sync(_count_sync, table)

    async def page(
        self, table: Table, column: str, after: object | None, limit: int
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按游标列取一页（`column > after` 升序）。

        Args:
            table: 表定义。
            column: 游标列名。
            after: 上一页末值（None 表示从头）。
            limit: 单页上限。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
        """
        return await self._connection.run_sync(_page_sync, table, column, after, limit)

    async def fetch(
        self, table: Table, column: str, values: ConcurrentStableList[object]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按列取值集合取行（`column IN values`）。

        Args:
            table: 表定义。
            column: 过滤列名。
            values: 取值集合。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
        """
        return await self._connection.run_sync(_fetch_sync, table, column, values)

    async def upsert(
        self, table: Table, column: str, rows: ConcurrentStableList[ConcurrentStableDict[str, object]]
    ) -> None:
        """按主键列删旧插新（一批一事务）。

        Args:
            table: 表定义。
            column: 主键列名。
            rows: 待写入行。
        """
        await self._connection.run_sync(_upsert_sync, table, column, rows)
        await self._connection.commit()

    async def scalar(self, sql: str) -> object:
        """执行标量查询。

        Args:
            sql: 查询语句。

        Returns:
            object: 首行首列值。
        """
        return await self._connection.run_sync(_scalar_sync, sql)


class SyncTableGateway(TableGateway):
    """同步连接实现（达梦等无异步方言驱动的库；调用方已在线程池内，故就地阻塞）。"""

    def __init__(self, connection: Connection) -> None:
        """初始化。

        Args:
            connection: 同步连接。
        """
        self._connection = connection

    async def exists(self, table: Table) -> bool:
        """目标库是否存在该表。

        Args:
            table: 表定义。

        Returns:
            bool: 存在 True。
        """
        return _exists_sync(self._connection, table)

    async def count(self, table: Table) -> int:
        """表行数。

        Args:
            table: 表定义。

        Returns:
            int: 行数。
        """
        return _count_sync(self._connection, table)

    async def page(
        self, table: Table, column: str, after: object | None, limit: int
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按游标列取一页（`column > after` 升序）。

        Args:
            table: 表定义。
            column: 游标列名。
            after: 上一页末值（None 表示从头）。
            limit: 单页上限。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
        """
        return _page_sync(self._connection, table, column, after, limit)

    async def fetch(
        self, table: Table, column: str, values: ConcurrentStableList[object]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按列取值集合取行（`column IN values`）。

        Args:
            table: 表定义。
            column: 过滤列名。
            values: 取值集合。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
        """
        return _fetch_sync(self._connection, table, column, values)

    async def upsert(
        self, table: Table, column: str, rows: ConcurrentStableList[ConcurrentStableDict[str, object]]
    ) -> None:
        """按主键列删旧插新（一批一事务）。

        Args:
            table: 表定义。
            column: 主键列名。
            rows: 待写入行。
        """
        _upsert_sync(self._connection, table, column, rows)
        self._connection.commit()

    async def scalar(self, sql: str) -> object:
        """执行标量查询。

        Args:
            sql: 查询语句。

        Returns:
            object: 首行首列值。
        """
        return _scalar_sync(self._connection, sql)


type SingleBody[ResultT] = Callable[[TableGateway, MetaData], Awaitable[ResultT]]
"""单库执行体签名。"""

type PairBody[ResultT] = Callable[[TableGateway, TableGateway], Awaitable[ResultT]]
"""双库执行体签名。"""


def table_targets(metadata: MetaData) -> ConcurrentStableList[TableTarget]:
    """取搬迁表集（按外键依赖序，父表在前）。

    Args:
        metadata: 搬迁表集的元数据。

    Returns:
        ConcurrentStableList[TableTarget]: 表目标（顺序即复制顺序）。

    Raises:
        ConfigError: 存在无主键表（无法按主键幂等写入）。
    """
    targets: ConcurrentStableList[TableTarget] = ConcurrentStableList()
    for table in metadata.sorted_tables:
        primary_key = ConcurrentStableFrozenList(column.name for column in table.primary_key.columns)
        if not primary_key:
            raise ConfigError(f"表 {table.name} 没有主键，无法按主键搬迁（请先补主键或改为人工迁移）")
        targets.add(TableTarget(name=table.name, primary_key=primary_key))
    return targets


async def count_rows(url: str, metadata: MetaData) -> ConcurrentStableDict[str, int]:
    """逐表统计行数（P1 数据量评估用；表不存在记 0）。

    Args:
        url: 连接串（含密码；禁止写入日志）。
        metadata: 表集元数据。

    Returns:
        ConcurrentStableDict[str, int]: 表名 → 行数。
    """
    return await _with_gateway(url, metadata, _count_all)


async def copy_tables(
    source_url: str,
    target_url: str,
    metadata: MetaData,
    *,
    batch_size: int = TABLE_BATCH_SIZE,
    progress: MigrationProgress | None = None,
    rate_limit_seconds: float = 0.0,
) -> CopyReport:
    """按表逐批复制到目标库（幂等；可断点续跑；失败即截断）。

    Args:
        source_url: 源库连接串（含密码；禁止写入日志）。
        target_url: 目标库连接串（含密码；禁止写入日志）。
        metadata: 搬迁表集元数据。
        batch_size: 单批行数。
        progress: 进度文件（None 表示不记断点）。
        rate_limit_seconds: 每批之间的休眠秒数（限速，避免压垮源库）。

    Returns:
        CopyReport: 逐表结果（含失败原因与截断位置）。
    """
    targets = table_targets(metadata)
    return await _with_gateways(
        source_url,
        target_url,
        lambda source, target: _copy_loop(
            source,
            target,
            metadata,
            targets=targets,
            batch_size=batch_size,
            progress=progress,
            rate_limit_seconds=rate_limit_seconds,
        ),
    )


async def verify_tables(
    source_url: str,
    target_url: str,
    metadata: MetaData,
    *,
    batch_size: int = TABLE_BATCH_SIZE,
    sample_size: int = SAMPLE_SIZE,
    assertions: ConcurrentStableList[BusinessAssertion] | None = None,
) -> VerifyReport:
    """执行四类对账（行数 / 主键覆盖 / 抽样内容 / 业务断言）。

    Args:
        source_url: 源库连接串（含密码；禁止写入日志）。
        target_url: 目标库连接串（含密码；禁止写入日志）。
        metadata: 搬迁表集元数据。
        batch_size: 单批行数。
        sample_size: 单表抽样条数上限。
        assertions: 业务断言（None 表示不做第 4 类）。

    Returns:
        VerifyReport: 对账报告。
    """
    targets = table_targets(metadata)
    return await _with_gateways(
        source_url,
        target_url,
        lambda source, target: _verify_loop(
            source,
            target,
            metadata,
            targets=targets,
            batch_size=batch_size,
            sample_size=sample_size,
            assertions=ConcurrentStableList(assertions or ()),
        ),
    )


async def _copy_loop(
    source: TableGateway,
    target: TableGateway,
    metadata: MetaData,
    *,
    targets: ConcurrentStableList[TableTarget],
    batch_size: int,
    progress: MigrationProgress | None,
    rate_limit_seconds: float,
) -> CopyReport:
    """逐表逐批复制（单表失败即截断后续表；已复制批次保留，重跑幂等）。

    Args:
        source: 源库门面。
        target: 目标库门面。
        metadata: 表集元数据。
        targets: 表目标。
        batch_size: 单批行数。
        progress: 进度文件。
        rate_limit_seconds: 每批休眠秒数。

    Returns:
        CopyReport: 逐表结果。
    """
    results: ConcurrentStableList[TableCopyResult] = ConcurrentStableList()
    for target_table in targets:
        table = metadata.tables[target_table.name]
        column = _cursor_column(target_table)
        if progress is not None and progress.completed(target_table.name):
            results.add(TableCopyResult(table=target_table.name, copied=0, resumed=True, skipped=True))
            continue
        after = progress.cursor(target_table.name) if progress is not None else None
        resumed = after is not None
        copied = 0
        try:
            while True:
                rows = await source.page(table, column, after, batch_size)
                if not rows:
                    break
                await target.upsert(table, column, rows)
                copied += len(rows)
                after = rows[-1][column]
                if progress is not None:
                    progress.mark(target_table.name, cursor=after)
                    progress.save()
                if rate_limit_seconds:
                    await asyncio.sleep(rate_limit_seconds)
        except Exception as exc:  # 单批失败：截断后续表，保留已复制批次（重跑幂等）
            results.add(
                TableCopyResult(
                    table=target_table.name,
                    copied=copied,
                    resumed=resumed,
                    skipped=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            break
        if progress is not None:
            progress.mark(target_table.name, cursor=after, done=True)
            progress.save()
        results.add(TableCopyResult(table=target_table.name, copied=copied, resumed=resumed, skipped=False))
    return CopyReport(tables=results)


async def _verify_loop(
    source: TableGateway,
    target: TableGateway,
    metadata: MetaData,
    *,
    targets: ConcurrentStableList[TableTarget],
    batch_size: int,
    sample_size: int,
    assertions: ConcurrentStableList[BusinessAssertion],
) -> VerifyReport:
    """逐表对账 + 业务断言。

    Args:
        source: 源库门面。
        target: 目标库门面。
        metadata: 表集元数据。
        targets: 表目标。
        batch_size: 单批行数。
        sample_size: 单表抽样条数上限。
        assertions: 业务断言。

    Returns:
        VerifyReport: 对账报告。
    """
    tables: ConcurrentStableList[TableVerifyResult] = ConcurrentStableList()
    for target_table in targets:
        tables.add(
            await _verify_table(
                source,
                target,
                metadata.tables[target_table.name],
                target_table,
                batch_size=batch_size,
                sample_size=sample_size,
            )
        )
    results: ConcurrentStableList[AssertionResult] = ConcurrentStableList()
    for assertion in assertions:
        source_value = await source.scalar(assertion.sql)
        target_value = await target.scalar(assertion.sql)
        results.add(
            AssertionResult(
                name=assertion.name,
                source=_text(source_value),
                target=_text(target_value),
                ok=_assertion_ok(source_value, target_value, assertion.tolerance),
            )
        )
    return VerifyReport(tables=tables, assertions=results)


async def _verify_table(
    source: TableGateway,
    target: TableGateway,
    table: Table,
    target_table: TableTarget,
    *,
    batch_size: int,
    sample_size: int,
) -> TableVerifyResult:
    """单表对账（不存在即失败；行数 / 主键覆盖 / 抽样内容）。

    Args:
        source: 源库门面。
        target: 目标库门面。
        table: 表定义。
        target_table: 表目标（游标列）。
        batch_size: 单批行数。
        sample_size: 抽样条数上限。

    Returns:
        TableVerifyResult: 单表结果。
    """
    column = _cursor_column(target_table)
    exists = await target.exists(table)
    source_rows = await source.count(table)
    if not exists:
        return TableVerifyResult(
            table=target_table.name,
            exists=False,
            source_rows=source_rows,
            target_rows=0,
            missing=source_rows,
            extra=0,
            sampled=0,
            mismatched=ConcurrentStableList(),
        )
    target_rows = await target.count(table)
    stride = max(1, source_rows // sample_size) if sample_size and source_rows else 0
    missing = 0
    sampled = 0
    mismatched: ConcurrentStableList[str] = ConcurrentStableList()
    after: object | None = None
    index = 0
    while True:
        rows = await source.page(table, column, after, batch_size)
        if not rows:
            break
        keys = ConcurrentStableList(row[column] for row in rows)
        present = ConcurrentStableSet(row[column] for row in await target.fetch(table, column, keys))
        missing += sum(1 for key in keys if key not in present)
        for offset, row in enumerate(rows):
            if not stride or (index + offset) % stride or sampled >= sample_size:
                continue
            sampled += 1
            counterpart = await target.fetch(table, column, ConcurrentStableList([row[column]]))
            if not counterpart or _content(counterpart[0]) != _content(row):
                mismatched.add(_text(row[column]))
        index += len(rows)
        after = keys[-1]
    extra = await _count_extra(source, target, table, column, batch_size)
    return TableVerifyResult(
        table=target_table.name,
        exists=True,
        source_rows=source_rows,
        target_rows=target_rows,
        missing=missing,
        extra=extra,
        sampled=sampled,
        mismatched=mismatched,
    )


async def _count_extra(source: TableGateway, target: TableGateway, table: Table, column: str, batch_size: int) -> int:
    """统计「目标有源无」的主键数（切换后新库写入、或迁移范围外数据的信号）。

    Args:
        source: 源库门面。
        target: 目标库门面。
        table: 表定义。
        column: 主键列名。
        batch_size: 单批行数。

    Returns:
        int: 多出的主键数。
    """
    extra = 0
    after: object | None = None
    while True:
        rows = await target.page(table, column, after, batch_size)
        if not rows:
            break
        keys = ConcurrentStableList(row[column] for row in rows)
        present = ConcurrentStableSet(row[column] for row in await source.fetch(table, column, keys))
        extra += sum(1 for key in keys if key not in present)
        after = keys[-1]
    return extra


async def _count_all(gateway: TableGateway, metadata: MetaData) -> ConcurrentStableDict[str, int]:
    """逐表统计行数（表不存在记 0）。

    Args:
        gateway: 库门面。
        metadata: 表集元数据。

    Returns:
        ConcurrentStableDict[str, int]: 表名 → 行数。
    """
    counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for name, table in metadata.tables.items():
        counts.set(name, await gateway.count(table) if await gateway.exists(table) else 0)
    return counts


async def _with_gateway[ResultT](url: str, metadata: MetaData, body: SingleBody[ResultT]) -> ResultT:
    """在单个库上执行协程体（按方言选异步 / 同步连接）。

    Args:
        url: 连接串（含密码；禁止写入日志）。
        metadata: 表集元数据。
        body: 协程函数（入参为门面与元数据）。

    Returns:
        ResultT: 协程体返回值。
    """
    if is_sync_only_url(url):
        return await asyncio.to_thread(_run_sync_single, url, metadata, body)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await body(AsyncTableGateway(connection), metadata)
    finally:
        await engine.dispose()


async def _with_gateways[ResultT](source_url: str, target_url: str, body: PairBody[ResultT]) -> ResultT:
    """在源库与目标库上执行协程体（按方言选异步 / 同步连接）。

    Args:
        source_url: 源库连接串（含密码；禁止写入日志）。
        target_url: 目标库连接串（含密码；禁止写入日志）。
        body: 协程函数（入参为源 / 目标门面）。

    Returns:
        ResultT: 协程体返回值。
    """
    if is_sync_only_url(source_url) or is_sync_only_url(target_url):
        return await asyncio.to_thread(_run_sync_pair, source_url, target_url, body)
    source_engine = create_async_engine(source_url, poolclass=NullPool)
    target_engine = create_async_engine(target_url, poolclass=NullPool)
    try:
        async with source_engine.connect() as source, target_engine.connect() as target:
            return await body(AsyncTableGateway(source), AsyncTableGateway(target))
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


def _run_sync_single[ResultT](url: str, metadata: MetaData, body: SingleBody[ResultT]) -> ResultT:
    """同步方言单库执行（线程池内跑独立事件循环）。

    Args:
        url: 连接串（含密码；禁止写入日志）。
        metadata: 表集元数据。
        body: 协程函数。

    Returns:
        ResultT: 协程体返回值。
    """
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return asyncio.run(body(SyncTableGateway(connection), metadata))
    finally:
        engine.dispose()


def _run_sync_pair[ResultT](source_url: str, target_url: str, body: PairBody[ResultT]) -> ResultT:
    """同步方言双库执行（线程池内跑独立事件循环）。

    Args:
        source_url: 源库连接串（含密码；禁止写入日志）。
        target_url: 目标库连接串（含密码；禁止写入日志）。
        body: 协程函数。

    Returns:
        ResultT: 协程体返回值。
    """
    source_engine = create_engine(source_url, poolclass=NullPool)
    target_engine = create_engine(target_url, poolclass=NullPool)
    try:
        with source_engine.connect() as source, target_engine.connect() as target:
            return asyncio.run(body(SyncTableGateway(source), SyncTableGateway(target)))
    finally:
        source_engine.dispose()
        target_engine.dispose()


def _cursor_column(target_table: TableTarget) -> str:
    """取游标列（单列主键）。

    Args:
        target_table: 表目标。

    Returns:
        str: 主键列名。

    Raises:
        ConfigError: 复合主键（按首列游标会跨批漏行）。
    """
    if len(target_table.primary_key) != 1:
        raise ConfigError(
            f"表 {target_table.name} 为复合主键（{'/'.join(target_table.primary_key)}），"
            "按首列游标会跨批漏行；请先补单列主键或改为人工迁移"
        )
    return target_table.primary_key[0]


def _select_page(table: Table, column: str, after: object | None, limit: int) -> Select[Any]:
    """构造「按游标列升序取一页」的查询。

    Args:
        table: 表定义。
        column: 游标列名。
        after: 上一页末值（None 表示从头）。
        limit: 单页上限。

    Returns:
        Select[Any]: 查询语句。
    """
    statement = select(table).order_by(table.c[column]).limit(limit)
    return statement if after is None else statement.where(table.c[column] > after)


def _rows(table: Table, result: Any) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """查询结果 → 逐行字典（列名 → 值，保表定义列序）。

    Args:
        table: 表定义。
        result: 查询结果行序列。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
    """
    names = ConcurrentStableList(column.name for column in table.columns)
    return ConcurrentStableList(ConcurrentStableDict(dict(zip(names, tuple(row), strict=True))) for row in result)


def _exists_sync(connection: Connection, table: Table) -> bool:
    """目标库是否存在该表（同步）。

    Args:
        connection: 同步连接。
        table: 表定义。

    Returns:
        bool: 存在 True。
    """
    return inspect(connection).has_table(table.name)


def _count_sync(connection: Connection, table: Table) -> int:
    """表行数（同步）。

    Args:
        connection: 同步连接。
        table: 表定义。

    Returns:
        int: 行数。
    """
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _page_sync(
    connection: Connection, table: Table, column: str, after: object | None, limit: int
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """按游标列取一页（同步）。

    Args:
        connection: 同步连接。
        table: 表定义。
        column: 游标列名。
        after: 上一页末值（None 表示从头）。
        limit: 单页上限。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
    """
    return _rows(table, connection.execute(_select_page(table, column, after, limit)).all())


def _fetch_sync(
    connection: Connection, table: Table, column: str, values: ConcurrentStableList[object]
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """按列取值集合取行（同步）。

    Args:
        connection: 同步连接。
        table: 表定义。
        column: 过滤列名。
        values: 取值集合。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 逐行字典。
    """
    if not values:
        return ConcurrentStableList()
    return _rows(table, connection.execute(select(table).where(table.c[column].in_(values))).all())


def _upsert_sync(
    connection: Connection,
    table: Table,
    column: str,
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
) -> None:
    """按主键列删旧插新（同步；一批一事务，由调用方提交）。

    Args:
        connection: 同步连接。
        table: 表定义。
        column: 主键列名。
        rows: 待写入行。
    """
    if not rows:
        return
    keys = ConcurrentStableList(row[column] for row in rows)
    connection.execute(table.delete().where(table.c[column].in_(keys)))
    connection.execute(table.insert(), [dict(row) for row in rows])


def _scalar_sync(connection: Connection, sql: str) -> object:
    """执行标量查询（同步）。

    Args:
        connection: 同步连接。
        sql: 查询语句。

    Returns:
        object: 首行首列值（无结果为 None）。
    """
    return connection.exec_driver_sql(sql).scalar()


def _content(row: ConcurrentStableDict[str, object]) -> ConcurrentStableList[str]:
    """行内容归一为文本序列（跨方言比对用；避免驱动层类型差异）。

    Args:
        row: 行字典。

    Returns:
        ConcurrentStableList[str]: 逐列文本值。
    """
    return ConcurrentStableList(_text(value) for value in row.values())


def _text(value: object) -> str:
    """取值归一为文本（None 记 `<null>`，与真实空串区分）。

    Args:
        value: 任意取值。

    Returns:
        str: 文本形态。
    """
    return "<null>" if value is None else str(value)


def _assertion_ok(source: object, target: object, tolerance: int) -> bool:
    """判定业务断言两侧取值是否一致（数值按差额、其余按文本）。

    Args:
        source: 源库取值。
        target: 目标库取值。
        tolerance: 数值允许差额。

    Returns:
        bool: 一致为 True。
    """
    source_number = _number(source)
    target_number = _number(target)
    if source_number is not None and target_number is not None:
        return abs(source_number - target_number) <= tolerance
    return _text(source) == _text(target)


def _number(value: object) -> float | None:
    """尝试把取值转为数值（布尔与非数值返回 None）。

    Args:
        value: 任意取值。

    Returns:
        float | None: 数值；不可转时为 None。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _json_safe(value: object) -> object:
    """断点游标归一为 JSON 可表示值（不可表示时丢弃，该表下次从头重跑）。

    Args:
        value: 主键值。

    Returns:
        object: 原值或 None。
    """
    try:
        json.dumps(value)
    except TypeError:
        return None
    return value
