"""DB 仓储真实实现测试（Kiwi 1050）：共享平台库验证 CRUD / 作用域 / 软删 / 租户 / 乐观锁 / 分页排序；
keyset 游标见 Kiwi 1078。

运行口径（2026-11-27 重写）：库是会话级共享平台库，写入是 autocommit 且**跨轮次叠加**，故本文件不再
「整表清空 + 精确条数」——那样必须靠跨进程串行（旧版是 `file_lock`，把整份目录拖到 130s+，且锁本身
属自造互斥）。现在每例把自己的读条件限定到**本用例命名空间**（`name like '{ns.prefix}%'` 的数据范围），
`count` / `list` / `list_page` / `list_cursor` 都经作用域过滤，断言仍是精确条数，但只数自己造的行；
不清理、不串行、不碰他人数据。

范围由 `FakeScope` 注入（`DataScope.read_predicate` 返回条件列表），与实际运行时的数据权限走同一条
翻译路径——顺带把作用域翻译分支压到每例上。乐观锁并发用例需要两个真实会话并提交，数据落
`test_db_lock_item`（无人做整表断言），结束时物理删自己那一行。
"""

from collections.abc import AsyncIterator
from functools import partial
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import BigInteger, Connection, Integer, String, Table, UniqueConstraint, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import current_user_id, reset_tenant_context, set_tenant_context
from bms_core.core.exceptions import ConcurrentConflictError, ConfigError, ParamError
from bms_core.db.tenant import TenantContext
from bms_core.models.base import BaseModel
from bms_core.permission.cache import current_permission_cache_store, reset_permission_cache_store
from bms_core.repositories.base_db_repository import (
    BaseDbRepository,
    _coerce_member,  # pyright: ignore[reportPrivateUsage]
    _coerce_value,  # pyright: ignore[reportPrivateUsage]
    _python_type,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.schemas.cursor import encode_cursor
from bms_core.schemas.pagination import BaseCursorQuery, BasePageQuery
from bms_core.schemas.sorting import SortDirection, SortSpec
from bms_core.scope.base import DataScope, ScopeCondition
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session


class DbItem(BaseModel):
    """测试模型：软删除 + 复合唯一 + 可排序字段。"""

    __tablename__ = "test_db_item"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_test_db_item_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LockItem(BaseModel):
    """测试模型：乐观锁并发用例专用表。

    该用例需要两个**真实**会话并真实提交（回滚会话无法模拟并发提交）；单库叠加下别的用例并不对
    这张表做整表断言，故提交行不会污染谁，用例结束时物理删掉自己写的那行。
    """

    __tablename__ = "test_db_lock_item"

    name: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ScopedNote(BaseModel):
    """测试模型：含 `tenant_id`（同库多租户维度）。"""

    __tablename__ = "test_scoped_note"

    title: Mapped[str] = mapped_column(String(32))
    tenant_id: Mapped[int] = mapped_column(BigInteger)


class DbItemRepository(BaseDbRepository[DbItem]):
    """测试仓储：默认软删 + 排序白名单。"""

    model = DbItem
    sortable_fields = ConcurrentStableSet({"name", "rank"})


class HardDeleteItemRepository(BaseDbRepository[DbItem]):
    """测试仓储：关闭软删（`delete` 物理删）。"""

    model = DbItem
    soft_delete_enabled = False


class LockItemRepository(BaseDbRepository[LockItem]):
    """测试仓储：乐观锁并发用例（默认软删）。"""

    model = LockItem


class HardDeleteLockItemRepository(BaseDbRepository[LockItem]):
    """测试仓储：乐观锁并发用例的收尾清理（关闭软删，物理删自己写入的行）。"""

    model = LockItem
    soft_delete_enabled = False


class NoteRepository(BaseDbRepository[ScopedNote]):
    """测试仓储：租户维度模型（写侧注入 / 读侧过滤）。"""

    model = ScopedNote
    tenant_scoped = True

    def tenant_payload(
        self, values: ConcurrentStableDict[str, object], *, creating: bool
    ) -> ConcurrentStableDict[str, object]:
        """暴露租户写入口径（测试用）。

        Args:
            values: 待写入字段值。
            creating: 是否创建。

        Returns:
            ConcurrentStableDict[str, object]: 注入租户后的字段值。
        """
        return self._apply_tenant_scope(values, creating=creating)


class BrokenScopedRepository(BaseDbRepository[DbItem]):
    """错误声明：`tenant_scoped=True` 但模型无 `tenant_id` 列（应快速失败）。"""

    model = DbItem
    tenant_scoped = True


class FakeScope(DataScope):
    """测试数据范围：固定读条件（写恒定允许）。"""

    def __init__(self, predicate: object) -> None:
        """初始化。

        Args:
            predicate: 读条件（`ScopeCondition` 或其列表）。
        """
        self._predicate = predicate

    def read_predicate(self) -> object:
        """返回固定条件。"""
        return self._predicate

    def allow_write(
        self,
        values: ConcurrentStableDict[str, object],
        *,
        scope_columns: ConcurrentStableDict[str, str] | None = None,
    ) -> bool:
        """写恒定允许（本用例只验证读侧翻译）。"""
        del values, scope_columns
        return True


def _name(prefix: str, leaf: str) -> str:
    """本用例命名空间下的行名 / 标题（`{prefix}_{leaf}`，长度远小于列上限）。

    Args:
        prefix: 命名空间前缀。
        leaf: 叶子段。

    Returns:
        str: 带前缀的名称。
    """
    return f"{prefix}_{leaf}"


def _own(prefix: str, column: str = "name") -> ScopeCondition:
    """本用例命名空间的读条件（`like` 传裸前缀）。

    `like` 在作用域翻译里是**转义后的子串匹配**（内部会把 `%` / `_` 转义并两侧补通配），故这里给
    裸前缀，实际谓词是「包含 `{prefix}`」；前缀定长且随机，包含即等价于属于本用例。

    Args:
        prefix: 命名空间前缀。
        column: 过滤列（`name` 或租户模型的 `title`）。

    Returns:
        ScopeCondition: 读到本用例行。
    """
    return ScopeCondition(column, "like", prefix)


def _scope_to(repo: BaseDbRepository[Any], *conditions: ScopeCondition) -> None:
    """把仓储的读条件限定到本用例（可叠加调用方给的条件）。

    Args:
        repo: 测试仓储。
        conditions: 读条件（首个通常是 `_own(...)`）。
    """
    repo._apply_data_scope(FakeScope(ConcurrentStableList(conditions)))  # pyright: ignore[reportPrivateUsage]


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表（共享库上只补本文件需要的表，不删表）。"""
    table.create(connection, checkfirst=True)


@pytest.fixture
async def engine(shared_platform_engine: AsyncEngine) -> AsyncEngine:
    """共享平台库引擎：幂等建本文件的三张测试表（不建库、不删表）。"""
    async with shared_platform_engine.begin() as connection:
        for table in (
            cast("Table", DbItem.__table__),
            cast("Table", LockItem.__table__),
            cast("Table", ScopedNote.__table__),
        ):
            await connection.run_sync(partial(_create_table, table))
    return shared_platform_engine


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """异步会话工厂（同库多会话，供并发用例）。"""
    yield async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """写会话：操作级写门 + autocommit（隔离靠每例的命名空间读条件，不清理）。"""
    async with write_session(engine) as session:
        yield session


def _demo_tenant(tenant_id: int) -> TenantContext:
    """构造测试租户上下文。

    Args:
        tenant_id: 租户主键。

    Returns:
        TenantContext: 租户上下文。
    """
    return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=tenant_id)


@pytest.mark.kiwi_id(1050)
async def test_crud_roundtrip_and_audit(session: AsyncSession, ns: Namespace) -> None:
    """create 落库（雪花 ID / 审计 / 版本）→ get / list / count / exists → update 版本自增。"""
    prefix = ns.prefix
    token = current_user_id.set(7)
    try:
        repo = DbItemRepository(session)
        _scope_to(repo, _own(prefix))
        item = await repo.create(name=_name(prefix, "甲"), rank=1)
        assert item.id > 0
        assert item.created_by == 7 and item.updated_by == 7
        assert item.created_at is not None and item.version == 1
        assert await repo.count() == 1
        assert await repo.exists(item.id) is True
        assert await repo.exists(item.id + 1) is False

        fetched = await repo.get(item.id)
        assert fetched is not None and fetched.name == _name(prefix, "甲")
        updated = await repo.update(item.id, name=_name(prefix, "乙"), rank=2)
        assert updated is not None and updated.name == _name(prefix, "乙") and updated.version == 2
        assert [row.name for row in await repo.list()] == [_name(prefix, "乙")]
        assert await repo.update(999_999, name=_name(prefix, "丙")) is None
    finally:
        current_user_id.reset(token)


@pytest.mark.kiwi_id(1050)
async def test_atomic_insert_if_absent_and_update_where(session: AsyncSession, ns: Namespace) -> None:
    """原子写原语：同键只插一行；覆盖不带版本谓词、版本仍自增。"""
    prefix = ns.prefix
    target = _name(prefix, "原子")
    repo = DbItemRepository(session)
    _scope_to(repo, _own(prefix))
    match: ConcurrentStableList[Any] = ConcurrentStableList((DbItem.name == target,))
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict({"name": target, "rank": 3})

    assert await repo.insert_if_absent(values, match=match) is True
    assert await repo.insert_if_absent(values, match=match) is False, "同键已存在必须跳过，不能插第二行"
    assert await repo.count() == 1
    row = (await repo.list())[0]
    assert row.version == 1 and row.created_at is not None

    token = current_user_id.set(7)
    try:
        changed = await repo.update_where(
            ConcurrentStableList((DbItem.id == row.id,)),
            values=ConcurrentStableDict({"rank": 9}),
        )
    finally:
        current_user_id.reset(token)
    assert changed == 1
    item_id = row.id
    session.expire_all()
    fetched = await repo.get(item_id)
    assert fetched is not None and fetched.rank == 9
    assert fetched.version == 2, "原子覆盖必须让乐观锁版本自增"
    assert fetched.updated_by == 7

    missing = await repo.update_where(
        ConcurrentStableList((DbItem.id == 999_999,)),
        values=ConcurrentStableDict({"rank": 1}),
    )
    assert missing == 0


@pytest.mark.kiwi_id(1050)
async def test_atomic_write_rejects_unknown_and_system_fields(session: AsyncSession) -> None:
    """原子写白名单：未知列与 id / 审计 / version / deleted_at 一律 ConfigError。"""
    repo = DbItemRepository(session)
    match: ConcurrentStableList[Any] = ConcurrentStableList((DbItem.name == "x",))
    with pytest.raises(ConfigError):
        await repo.insert_if_absent(ConcurrentStableDict({"ghost": 1}), match=match)
    with pytest.raises(ConfigError):
        await repo.insert_if_absent(ConcurrentStableDict({"name": "x", "version": 5}), match=match)
    with pytest.raises(ConfigError):
        await repo.update_where(ConcurrentStableList((DbItem.id == 1,)), values=ConcurrentStableDict({"ghost": 1}))
    with pytest.raises(ConfigError):
        await repo.update_where(
            ConcurrentStableList((DbItem.id == 1,)),
            values=ConcurrentStableDict({"name": "x", "deleted_at": None}),
        )


@pytest.mark.kiwi_id(1050)
async def test_atomic_write_supports_foreign_model(session: AsyncSession, ns: Namespace) -> None:
    """多表共用仓储：`model=` 让校验与作用域落到目标表，而不是仓储声明的 `model`。"""
    target = _name(ns.prefix, "他表")
    repo = DbItemRepository(session)
    match: ConcurrentStableList[Any] = ConcurrentStableList((LockItem.name == target,))

    assert await repo.insert_if_absent(ConcurrentStableDict({"name": target}), match=match, model=LockItem) is True
    assert await repo.insert_if_absent(ConcurrentStableDict({"name": target}), match=match, model=LockItem) is False
    changed = await repo.update_where(
        match,
        values=ConcurrentStableDict({"rank": 2}),
        model=LockItem,
    )
    assert changed == 1
    with pytest.raises(ConfigError):
        await repo.insert_if_absent(ConcurrentStableDict({"ghost": 1}), match=match, model=LockItem)


@pytest.mark.kiwi_id(1050)
async def test_soft_delete_where_marks_rows_and_is_idempotent(session: AsyncSession, ns: Namespace) -> None:
    """原子软删：命中行置 `deleted_at`、版本自增；再删同一行返回 0（并发幂等）。"""
    prefix = ns.prefix
    target = _name(prefix, "软删")
    repo = DbItemRepository(session)
    _scope_to(repo, _own(prefix))
    await repo.insert_if_absent(
        ConcurrentStableDict({"name": target}),
        match=ConcurrentStableList((DbItem.name == target,)),
    )
    row = (await repo.list())[0]
    match: ConcurrentStableList[Any] = ConcurrentStableList((DbItem.id == row.id,))
    item_id = row.id
    version_before = row.version

    assert await repo.soft_delete_where(match, model=DbItem) == 1
    assert await repo.soft_delete_where(match) == 0
    session.expire_all()
    assert await repo.get(item_id) is None
    deleted = (
        await session.execute(select(DbItem).where(DbItem.id == item_id).execution_options(populate_existing=True))
    ).scalar_one()
    assert deleted.deleted_at is not None
    assert deleted.version == version_before + 1


@pytest.mark.kiwi_id(1050)
async def test_write_whitelist_rejects_unknown_and_internal_fields(session: AsyncSession) -> None:
    """写入白名单：未知键与 id / 审计 / version / deleted_at 一律 ConfigError。"""
    repo = DbItemRepository(session)
    with pytest.raises(ConfigError):
        await repo.create(ghost=1)
    with pytest.raises(ConfigError):
        await repo.create(name="x", version=5)
    with pytest.raises(ConfigError):
        await repo.create(name="x", created_by=7)
    with pytest.raises(ConfigError):
        await repo.create(name="x", deleted_at=None)
    with pytest.raises(ConfigError):
        await repo.update(1, ghost=1)


@pytest.mark.kiwi_id(1050)
async def test_scope_operator_translation(session: AsyncSession, ns: Namespace) -> None:
    """11 种作用域操作符统一翻译为 SQL WHERE（空 `in` 恒假）；计数限定在本用例行内。"""
    prefix = ns.prefix
    repo = DbItemRepository(session)
    await repo.create(name=_name(prefix, "alpha"), rank=2)

    cases: ConcurrentStableList[tuple[ConcurrentStableList[ScopeCondition], int]] = ConcurrentStableList(
        [
            (ConcurrentStableList([_own(prefix), ScopeCondition("name", "eq", _name(prefix, "alpha"))]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("name", "ne", _name(prefix, "beta"))]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "in", [1, 2])]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "in", ConcurrentStableSet([1, 2]))]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "in", [])]), 0),
            (ConcurrentStableList([_own(prefix), ScopeCondition("name", "like", "lph")]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "gt", 1)]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "gte", 2)]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "lt", 3)]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "lte", 2)]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "between", (1, 3))]), 1),
            (ConcurrentStableList([_own(prefix), ScopeCondition("rank", "is_null", None)]), 0),
            (ConcurrentStableList([_own(prefix), ScopeCondition("name", "is_not_null", None)]), 1),
        ]
    )
    for conditions, expected in cases:
        repo._apply_data_scope(FakeScope(conditions))  # pyright: ignore[reportPrivateUsage]
        assert await repo.count() == expected, conditions


@pytest.mark.kiwi_id(1050)
async def test_scope_condition_errors(session: AsyncSession, ns: Namespace) -> None:
    """作用域条件非法：字段不存在 / 操作符不支持 / 值形态非法，一律 ConfigError。"""
    repo = DbItemRepository(session)
    await repo.create(name=_name(ns.prefix, "alpha"), rank=2)

    _scope_to(repo, _own(ns.prefix), ScopeCondition("ghost", "eq", 1))
    with pytest.raises(ConfigError):
        await repo.count()

    _scope_to(repo, _own(ns.prefix), ScopeCondition("name", "regex", "x"))
    with pytest.raises(ConfigError):
        await repo.count()

    for condition in (
        ScopeCondition("rank", "in", 1),
        ScopeCondition("rank", "in", "12"),
        ScopeCondition("name", "like", 1),
        ScopeCondition("rank", "between", (1,)),
        ScopeCondition("rank", "between", 1),
    ):
        _scope_to(repo, _own(ns.prefix), condition)
        with pytest.raises(ConfigError):
            await repo.count()


class MappedItemRepository(DbItemRepository):
    """声明数据源映射的测试仓储（`mdm_dept` → `rank` 列）。"""

    scope_columns: ConcurrentStableDict[str, str] = ConcurrentStableDict({"mdm_dept": "rank"})


@pytest.mark.kiwi_id(2324)
async def test_data_source_condition_translates_with_type_coercion(session: AsyncSession, ns: Namespace) -> None:
    """数据源维度条件：按 `scope_columns` 翻译列，集合值 / 区间值按列类型归一（`"2"` → `2`）。"""
    prefix = ns.prefix
    mapped = MappedItemRepository(session)
    await mapped.create(name=_name(prefix, "alpha"), rank=2)

    _scope_to(mapped, _own(prefix), ScopeCondition("", "in", ["2", "3"], "mdm_dept"))
    assert await mapped.count() == 1

    _scope_to(mapped, _own(prefix), ScopeCondition("", "between", ("1", "3"), "mdm_dept"))
    assert await mapped.count() == 1

    unmapped = DbItemRepository(session)
    _scope_to(unmapped, _own(prefix), ScopeCondition("", "in", ["2"], "mdm_dept"))
    assert await unmapped.count() == 0


@pytest.mark.kiwi_id(2324)
async def test_condition_value_coercion_failure_denies_all(session: AsyncSession, ns: Namespace) -> None:
    """集合值无法按列类型归一：该条件译永假（查不到数据）+ 非法规则计数。"""
    reset_permission_cache_store()
    prefix = ns.prefix
    repo = MappedItemRepository(session)
    await repo.create(name=_name(prefix, "alpha"), rank=2)
    _scope_to(repo, _own(prefix), ScopeCondition("", "in", ["x"], "mdm_dept"))
    assert await repo.count() == 0
    assert current_permission_cache_store().stats()["invalid_rule_rejections"] == 1


class _NoPythonType(UserDefinedType[object]):
    """无 `python_type` 的自定义列类型（覆盖「类型不可判」分支）。"""

    def get_col_spec(self, **kw: object) -> str:
        """DDL 片段（用例不建表，仅占位）。

        Args:
            kw: 方言参数（忽略）。

        Returns:
            str: 列类型名。
        """
        del kw
        return "TEXT"


def test_coercion_helpers_cover_all_type_branches() -> None:
    """类型归一：整型 / 浮点 / 字符串 / 不可判类型与转换失败分支。"""
    assert _coerce_member(None, int) == (None, True)
    assert _coerce_member(True, int) == (True, True)
    assert _coerce_member(1, int) == (1, True)
    assert _coerce_member("1", int) == (1, True)
    assert _coerce_member("x", int) == ("x", False)
    assert _coerce_member(1, float) == (1.0, True)
    assert _coerce_member("1.5", float) == (1.5, True)
    assert _coerce_member("x", float) == ("x", False)
    assert _coerce_member("s", str) == ("s", True)
    assert _coerce_member(1, str) == ("1", True)
    assert _coerce_member(1, None) == (1, True)
    assert _coerce_member(1, dict) == (1, True)

    rank_column = cast("Any", DbItem.rank)
    name_column = cast("Any", DbItem.name)
    assert _coerce_value(rank_column, "like", "1%") == ("1%", True)
    assert _coerce_value(rank_column, "in", 5) == (5, True)
    members, ok = _coerce_value(rank_column, "in", ["1", "2"])
    assert ok is True and list(cast("Any", members)) == [1, 2]
    assert _coerce_value(rank_column, "in", ["x"]) == (["x"], False)
    assert _coerce_value(rank_column, "between", 5) == (5, True)
    assert _coerce_value(rank_column, "between", ("1",)) == (("1",), True)
    assert _coerce_value(rank_column, "between", ("1", "3")) == ((1, 3), True)
    assert _coerce_value(rank_column, "between", ("x", "3")) == (("x", "3"), False)
    assert _coerce_value(name_column, "eq", "alpha") == ("alpha", True)

    no_type_column: Any = SimpleNamespace(type=_NoPythonType())
    assert _python_type(no_type_column) is None
    raw_members, raw_ok = _coerce_value(no_type_column, "in", ["a"])
    assert raw_ok is True and list(cast("Any", raw_members)) == ["a"]
    assert _python_type(cast("Any", DbItem.rank)) is int


@pytest.mark.kiwi_id(1050)
async def test_soft_delete_restore_and_unique_reuse(session: AsyncSession, ns: Namespace) -> None:
    """软删后不可见、唯一键释放复用；恢复后重新可见。"""
    prefix = ns.prefix
    target = _name(prefix, "dup")
    repo = DbItemRepository(session)
    _scope_to(repo, _own(prefix))
    item = await repo.create(name=target)
    assert await repo.soft_delete(item.id) is True
    assert await repo.get(item.id) is None
    assert await repo.exists(item.id) is False
    assert await repo.count() == 0
    assert await repo.soft_delete(item.id) is False

    second = await repo.create(name=target)
    assert second.id != item.id

    assert await repo.soft_delete(second.id) is True
    stale = (await session.execute(select(DbItem).where(DbItem.id == item.id))).scalar_one()
    stale.restore()
    await session.flush()
    assert await repo.get(item.id) is not None
    assert await repo.get(second.id) is None


@pytest.mark.kiwi_id(1050)
async def test_delete_switch_and_hard_delete(session: AsyncSession, ns: Namespace) -> None:
    """delete 默认软删 / 关闭软删时物理删；hard_delete 可穿透软删过滤清理残留。"""
    prefix = ns.prefix
    soft_repo = DbItemRepository(session)
    soft = await soft_repo.create(name=_name(prefix, "a"))
    assert await soft_repo.delete(soft.id) is True
    assert await soft_repo.get(soft.id) is None

    hard_repo = HardDeleteItemRepository(session)
    other = await hard_repo.create(name=_name(prefix, "b"))
    assert await hard_repo.delete(other.id) is True
    raw = (await session.execute(select(DbItem).where(DbItem.id == other.id))).scalar_one_or_none()
    assert raw is None
    assert await hard_repo.delete(999_999) is False

    assert await hard_repo.hard_delete(soft.id) is True
    purged = (await session.execute(select(DbItem).where(DbItem.id == soft.id))).scalar_one_or_none()
    assert purged is None
    assert await hard_repo.hard_delete(999_999) is False


@pytest.mark.kiwi_id(1050)
async def test_tenant_write_and_read_scope(session: AsyncSession, ns: Namespace) -> None:
    """租户写侧注入 / 禁改；读侧强制过滤；跨租户不可见。"""
    prefix = ns.prefix
    token = set_tenant_context(_demo_tenant(7))
    try:
        repo = NoteRepository(session)
        _scope_to(repo, _own(prefix, "title"))
        note = await repo.create(title=_name(prefix, "n7"))
        assert note.tenant_id == 7
        same = await repo.create(title=_name(prefix, "n7b"), tenant_id=7)
        assert same.tenant_id == 7
        with pytest.raises(ConfigError):
            await repo.create(title=_name(prefix, "x"), tenant_id=8)

        assert await repo.update(note.id, title=_name(prefix, "n7c")) is not None
        with pytest.raises(ConfigError):
            await repo.update(note.id, tenant_id=8)

        token_other = set_tenant_context(_demo_tenant(8))
        try:
            other = await repo.create(title=_name(prefix, "n8"))
            assert other.tenant_id == 8
        finally:
            reset_tenant_context(token_other)

        assert await repo.count() == 2
        assert await repo.get(other.id) is None
        assert await repo.exists(other.id) is False
        assert await repo.update(other.id, title=_name(prefix, "x")) is None
        assert [row.title for row in await repo.list()] == [_name(prefix, "n7c"), _name(prefix, "n7b")]
    finally:
        reset_tenant_context(token)


@pytest.mark.kiwi_id(1050)
async def test_tenant_scope_edge_branches(session: AsyncSession) -> None:
    """租户分支：上下文无主键不注入；声明与模型不符快速失败。"""
    repo = NoteRepository(session)
    assert repo.tenant_payload(ConcurrentStableDict({"title": "x"}), creating=True) == {"title": "x"}

    token = set_tenant_context(_demo_tenant(7))
    try:
        broken = BrokenScopedRepository(session)
        with pytest.raises(ConfigError):
            await broken.create(name="x")
        with pytest.raises(ConfigError):
            await broken.count()
    finally:
        reset_tenant_context(token)


@pytest.mark.kiwi_id(1050)
async def test_optimistic_lock_conflict(session_factory: async_sessionmaker[AsyncSession], ns: Namespace) -> None:
    """并发旧版本更新 flush 触发 StaleDataError，仓储转 ConcurrentConflictError（409）。

    本用例需要两个**真实**会话（回滚会话无法模拟并发提交），故数据会落盘：写入 `test_db_lock_item`
    ——一张只服务本用例的表；名称用命名空间前缀，结束时物理删掉自己写入的行。
    """
    name = ns.code("lock")
    async with session_factory() as first, session_factory() as second:
        first_repo = LockItemRepository(first)
        created = await first_repo.create(name=name)
        await first.commit()

        second_repo = LockItemRepository(second)
        stale = await second_repo.get(created.id)
        assert stale is not None and stale.version == 1
        assert await first_repo.update(created.id, name=f"{name}-first") is not None
        await first.commit()
        with pytest.raises(ConcurrentConflictError):
            await second_repo.update(created.id, name=f"{name}-second")

    async with session_factory() as cleanup:
        assert await HardDeleteLockItemRepository(cleanup).hard_delete(created.id) is True
        await cleanup.commit()


@pytest.mark.kiwi_id(1050)
async def test_pagination_and_sort(session: AsyncSession, ns: Namespace) -> None:
    """分页 `LIMIT/OFFSET` + 白名单排序 + 默认 id 升序 + 未知排序字段忽略（只在本用例行内取页）。"""
    prefix = ns.prefix
    repo = DbItemRepository(session)
    _scope_to(repo, _own(prefix))
    await repo.create(name=_name(prefix, "a"), rank=2)
    await repo.create(name=_name(prefix, "b"), rank=1)
    await repo.create(name=_name(prefix, "c"), rank=3)

    assert [row.name for row in await repo.list()] == [_name(prefix, leaf) for leaf in ("a", "b", "c")]
    page = await repo.list_page(BasePageQuery(page=1, size=2, order_by="rank", order=ConcurrentStableList(["desc"])))
    assert [row.name for row in page] == [_name(prefix, leaf) for leaf in ("c", "a")]
    page2 = await repo.list_page(BasePageQuery(page=2, size=2, order_by="rank", order=ConcurrentStableList(["desc"])))
    assert [row.name for row in page2] == [_name(prefix, "b")]

    ignored = await repo.list(
        sort=ConcurrentStableList([SortSpec(field="ghost"), SortSpec(field="name", direction=SortDirection.DESC)])
    )
    assert [row.name for row in ignored] == [_name(prefix, leaf) for leaf in ("c", "b", "a")]


@pytest.mark.kiwi_id(1078)
async def test_cursor_keyset_pagination_with_nulls(session: AsyncSession, ns: Namespace) -> None:
    """DB 侧 keyset 游标：NULL 恒末位、多键与升 / 降序下逐页取完与全量排序一致（不漏不重）。"""
    prefix = ns.prefix
    repo = DbItemRepository(session)
    _scope_to(repo, _own(prefix))
    for leaf, rank in (("a", 2), ("b", 1), ("c", None), ("d", 1), ("e", 3)):
        await repo.create(name=_name(prefix, leaf), rank=rank)

    for order in ("asc", "desc"):
        sort = ConcurrentStableList(
            [SortSpec(field="rank", direction=SortDirection.ASC if order == "asc" else SortDirection.DESC)]
        )
        expected = [row.name for row in await repo.list(sort=sort)]
        assert expected[-1] == _name(prefix, "c"), "NULL 恒排末位"

        collected: ConcurrentStableList[str] = ConcurrentStableList()
        cursor: str | None = None
        for _ in range(10):
            query = BaseCursorQuery(limit=2, order_by="rank", order=ConcurrentStableList([order]), cursor=cursor)
            batch = await repo.list_cursor(query)
            collected.update(row.name for row in batch)
            cursor = repo.build_cursor(query, batch)
            if cursor is None:
                break
        assert collected == expected


@pytest.mark.kiwi_id(1078)
async def test_cursor_rejects_invalid_and_mismatched(session: AsyncSession, ns: Namespace) -> None:
    """DB 侧游标校验：非法令牌 / 规格不一致 → `ParamError`（不静默回落首页）。"""
    repo = DbItemRepository(session)
    await repo.create(name=_name(ns.prefix, "a"), rank=1)

    with pytest.raises(ParamError):
        await repo.list_cursor(BaseCursorQuery(limit=1, cursor="not-a-cursor"))

    token = encode_cursor(
        ConcurrentStableList([SortSpec(field="rank", direction=SortDirection.ASC)]), ConcurrentStableList([1]), 1
    )
    with pytest.raises(ParamError):
        await repo.list_cursor(
            BaseCursorQuery(limit=1, order_by="name", order=ConcurrentStableList(["asc"]), cursor=token)
        )


@pytest.mark.kiwi_id(1078)
async def test_db_sort_orders_nulls_last_in_compiled_sql(session: AsyncSession) -> None:
    """ORDER BY 编译：NULL 位次用 `rank IS NULL` 排序键显式表达（不出现 `NULLS FIRST/LAST` 字面量）。"""
    repo = DbItemRepository(session)
    sort = ConcurrentStableList([SortSpec(field="rank", direction=SortDirection.DESC)])
    statement = repo._apply_sort(repo._select(), sort)  # pyright: ignore[reportPrivateUsage]
    sql = str(statement.compile(dialect=sqlite.dialect()))
    assert "rank IS NULL" in sql
    assert "id ASC" in sql
    assert "NULLS LAST" not in sql.upper() and "NULLS FIRST" not in sql.upper()


@pytest.mark.kiwi_id(2324)
async def test_tenant_condition_absent_without_context(session: AsyncSession) -> None:
    """租户维度仓储：上下文无租户主键时不注入租户条件（仅物理库隔离兜底）。"""
    token = set_tenant_context(TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=None))
    try:
        repo = NoteRepository(session)
        assert repo._tenant_condition() is None  # pyright: ignore[reportPrivateUsage]
    finally:
        reset_tenant_context(token)
