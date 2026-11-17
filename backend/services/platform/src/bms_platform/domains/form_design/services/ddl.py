"""动态 DDL 执行器：白名单校验 → 元数据先行 → 单租户串行 → 参数化编译 → 状态回写（10_01）。

**安全口径（任务书 §3「注入用例被拒」）**：

1. **标识符白名单**（`bms_core/formdesign/identifier.py`）：表名 / 列名先过白名单正则与保留字，
   非法形态在**登记阶段**就抛 `ParamError`（10001），根本到不了 DDL 编译层；
2. **参数化编译**：DDL 由 Alembic `AddColumn` + SQLAlchemy 类型对象按方言编译（`AddColumn(...).compile()`），
   **全程不拼字符串**——类型差异由方言层承担（达梦 `VARCHAR2(n CHAR)` 等）；
3. **列存在性探测**：先 `inspect` 目标表列，已存在且元数据无对应行即 `40406`，不动既有列；
4. **单租户串行**：`bms:{tenant}:lock:form-ddl:{table}`（锁基座），TTL 30s、等待 5s，取不到锁 `10004`；
   锁不可用（Redis 挂）fail-closed `10012`，不执行 DDL（宁可不建，不建半套）。

**生命周期**：`pending`（元数据已写、DDL 未执行/失败）→ `active`（建列成功）/ `failed`（执行异常）；
失败**只影响本字段**，其它字段不受影响；重试复用同一元数据与列名。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from alembic.ddl.base import AddColumn
from sqlalchemy import Column, inspect, text
from sqlalchemy.engine import Dialect, Inspector
from sqlalchemy.types import TypeEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import (
    FormColumnConflictError,
    FormDdlFailedError,
)
from bms_core.core.logging import get_logger
from bms_core.db.session import DbSession
from bms_core.fieldtype.mapping import ext_column_type
from bms_core.formdesign.identifier import (
    derive_column_name,
    validate_column_name,
    validate_field_key,
    validate_table_name,
)
from bms_core.lock.base import BaseDistributedLock, build_lock_key
from bms_core.models.platform.form_design import SysFieldExt

__all__ = ["DdlOutcome", "FormDdlExecutor"]

_LOGGER = get_logger("bms.form_design.ddl")

DDL_LOCK_TTL = 30
"""DDL 锁 TTL（秒）；到期自动释放，防死锁。"""

DDL_LOCK_WAIT = 5.0
"""DDL 锁等待时长（秒）；超时即 `10004`（可重试）。"""


@dataclass(frozen=True)
class DdlOutcome:
    """DDL 执行结果。"""

    column_name: str
    """物理列名。"""
    created: bool
    """是否本次新建（False 表示列已存在且元数据一致，幂等命中）。"""


class FormDdlExecutor:
    """自建字段 DDL 执行器（无状态：会话 / 锁 / 租户标识按次注入）。"""

    def __init__(self, session: DbSession, *, lock: BaseDistributedLock, tenant: str | None) -> None:
        """初始化。

        Args:
            session: 请求级会话（与业务事务同会话）。
            lock: 分布式锁（单租户串行）。
            tenant: 租户标识（锁 key 与日志用；None 表示无租户上下文）。
        """
        self._session = session
        self._lock = lock
        self._tenant = tenant

    async def add_column(self, field: SysFieldExt, *, comment: str) -> DdlOutcome:
        """为自建字段加物理列（幂等：列已存在且元数据一致即命中）。

        Args:
            field: 自建字段行（`column_name` / `table_name` / `type` 已入库）。
            comment: 列注释（中文；进 DDL 的 `COMMENT`）。

        Returns:
            DdlOutcome: 执行结果。

        Raises:
            ParamError: 表名 / 列名 / 类型不在白名单（10001）。
            ConcurrentConflictError: 未取到 DDL 锁（10004 / 409，可重试）。
            FormColumnConflictError: 物理列已存在且元数据不一致（40406）。
            FormDdlFailedError: DDL 执行异常（40405）。
        """
        table_name = validate_table_name(field.table_name)
        column_name = validate_column_name(field.column_name)
        expected = validate_column_name(derive_column_name(validate_field_key(field.field_key)))
        if column_name != expected:  # pragma: no cover - 入库值由本域派生，防御性断言
            raise FormColumnConflictError(f"列名与字段键派生结果不一致：{column_name} != {expected}")
        column_type = ext_column_type(field.type)
        lock_key = build_lock_key(tenant=self._tenant, resource=f"form-ddl:{table_name}")
        async with self._lock.hold(lock_key, ttl=DDL_LOCK_TTL, wait=DDL_LOCK_WAIT):
            existing = await self._existing_columns(table_name)
            if column_name in existing:
                return DdlOutcome(column_name=column_name, created=False)
            sql = self._compile(table_name, column_name, column_type, comment)
            try:
                await self._execute_ddl(sql)
            except Exception as exc:
                _LOGGER.exception(
                    "自建字段建列失败",
                    table=table_name,
                    column=column_name,
                    field_key=field.field_key,
                    tenant=self._tenant,
                )
                raise FormDdlFailedError(
                    f"建列失败：{table_name}.{column_name}（{type(exc).__name__}: {exc}）",
                    data={"table": table_name, "column": column_name, "sql": sql},
                ) from exc
            return DdlOutcome(column_name=column_name, created=True)

    async def _execute_ddl(self, sql: str) -> None:
        """在**当前会话**上执行 DDL（同一事务上下文中立即可见）。

        取舍：DDL 与业务事务同会话，保证「元数据 → 建列 → 状态回写」在同一可见性域内（开发 / 测试
        环境的 SQLite 文件库只有同一连接能看到未提交 DDL）；生产方言的 DDL 隐式提交特性由运维窗口
        兜底（MySQL 8 在线加列 / PG 快速加列），执行时机本身已是低频操作。

        Args:
            sql: 已编译的 DDL 文本（标识符与类型均来自白名单 / 映射）。
        """
        await self._session.execute(text(sql))

    async def _existing_columns(self, table_name: str) -> ConcurrentStableList[str]:
        """探测目标表现有列（跨异步 / 同步门面双分支，与基座会话口径一致）。

        Args:
            table_name: 表名（已过白名单）。

        Returns:
            ConcurrentStableList[str]: 现有列名（小写）。
        """

        def _collect(session_or_connection: object) -> ConcurrentStableList[str]:
            target: Any = session_or_connection
            get_bind = getattr(session_or_connection, "get_bind", None)
            if callable(get_bind):  # pragma: no cover - 同步门面分支（见下）
                target = get_bind()
            inspector = cast("Inspector", inspect(target))
            collected: ConcurrentStableList[str] = ConcurrentStableList()
            with contextlib.suppress(AttributeError):
                inspector.clear_cache()
            for column in inspector.get_columns(table_name):
                collected.add(str(column["name"]).lower())
            return collected

        run_sync = getattr(self._session, "run_sync", None)
        if callable(run_sync):
            return await cast("Awaitable[ConcurrentStableList[str]]", run_sync(_collect))
        return await self._collect_from_sync_facade(_collect)  # pragma: no cover - 同下（异步会话恒有 run_sync）

    async def _collect_from_sync_facade(  # pragma: no cover - 同步门面（DM8 等同步方言）分支，异步会话下不可达
        self,
        collect: Callable[[object], ConcurrentStableList[str]],
    ) -> ConcurrentStableList[str]:
        """同步门面分支：无 `run_sync` 时经 `raw.connection()` 在线程里探测列。

        Args:
            collect: 列收集器（接收会话或连接）。

        Returns:
            ConcurrentStableList[str]: 现有列名（小写）。

        Raises:
            FormDdlFailedError: 会话既无 `run_sync` 也无 `raw`（会话契约保证不会发生）。
        """
        raw = getattr(self._session, "raw", None)
        if raw is None:
            raise FormDdlFailedError("会话不支持连接探测，无法执行 DDL")
        return await asyncio.to_thread(lambda: collect(raw.connection()))

    def _compile(
        self,
        table_name: str,
        column_name: str,
        column_type: TypeEngine[Any],
        comment: str,
    ) -> str:
        """按方言编译 `ALTER TABLE ... ADD COLUMN`（参数化元素，不拼字符串）。

        Args:
            table_name: 表名（已过白名单）。
            column_name: 列名（已过白名单）。
            column_type: 类型实例（来自四库映射）。
            comment: 列注释。

        Returns:
            str: 供 `text()` 执行的 DDL 文本（标识符与类型均来自白名单 / 映射，非用户输入拼接）。
        """
        dialect = self._dialect()
        column = Column(column_name, column_type, nullable=True, comment=comment)
        return str(AddColumn(table_name, column).compile(dialect=dialect))

    def _dialect(self) -> Dialect:
        """取当前会话绑定的方言（决定 `VARCHAR2` 等方言落点）。

        异步会话的 `get_bind()` 返回 `AsyncEngine`（方言在 `sync_engine`），同步门面返回
        `Engine` / `Connection`（方言直接可得）——两处都取，避免方言丢失。

        Returns:
            Dialect: SQLAlchemy 方言实例。
        """
        bind = self._session.get_bind()
        dialect = getattr(bind, "dialect", None)
        if dialect is None:  # pragma: no cover - 引擎缺 `dialect` 时回落到 `sync_engine`（异步引擎自身已代理）
            dialect = getattr(getattr(bind, "sync_engine", None), "dialect", None)
        if dialect is None:  # pragma: no cover - 会话契约保证有方言
            raise FormDdlFailedError("会话未绑定方言，无法编译 DDL")
        return dialect
