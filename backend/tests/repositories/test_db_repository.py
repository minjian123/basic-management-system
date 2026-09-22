"""DB 仓储真实实现测试（Kiwi 1050）：SQLite 真库验证 CRUD / 作用域 / 软删 / 租户 / 乐观锁 / 分页排序。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import BigInteger, Integer, String, Table, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from app.core.context import current_user_id, reset_tenant_context, set_tenant_context
from app.core.exceptions import ConcurrentConflictError, ConfigError
from app.db.tenant import TenantContext
from app.models.base import BaseModel
from app.repositories.base_db_repository import BaseDbRepository
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.schemas.sorting import SortDirection, SortSpec
from app.scope.base import DataScope, ScopeCondition


class DbItem(BaseModel):
    """测试模型：软删除 + 复合唯一 + 可排序字段。"""

    __tablename__ = "test_db_item"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_test_db_item_name_deleted_at"),)

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
    sortable_fields = frozenset({"name", "rank"})

    def apply_scope(self, scope: DataScope | None) -> None:
        """暴露数据范围注入钩子（测试用）。

        Args:
            scope: 数据范围契约；None 表示清除。
        """
        self._apply_data_scope(scope)


class HardDeleteItemRepository(BaseDbRepository[DbItem]):
    """测试仓储：关闭软删（`delete` 物理删）。"""

    model = DbItem
    soft_delete_enabled = False


class NoteRepository(BaseDbRepository[ScopedNote]):
    """测试仓储：租户维度模型（写侧注入 / 读侧过滤）。"""

    model = ScopedNote
    tenant_scoped = True

    def tenant_payload(self, values: dict[str, object], *, creating: bool) -> dict[str, object]:
        """暴露租户写入口径（测试用）。

        Args:
            values: 待写入字段值。
            creating: 是否创建。

        Returns:
            dict[str, object]: 注入租户后的字段值。
        """
        return self._apply_tenant_scope(values, creating=creating)


class BrokenScopedRepository(BaseDbRepository[DbItem]):
    """错误声明：`tenant_scoped=True` 但模型无 `tenant_id` 列（应快速失败）。"""

    model = DbItem
    tenant_scoped = True


class FakeScope(DataScope):
    """测试数据范围：固定读条件（写恒定允许）。"""

    def __init__(self, predicate: object) -> None:
        self._predicate = predicate

    def read_predicate(self) -> object:
        """返回固定条件。"""
        return self._predicate

    def allow_write(self, values: dict[str, object]) -> bool:
        """写恒定允许（本用例只验证读侧翻译）。"""
        return True


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """SQLite 真库引擎：仅建测试两表。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'repo.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast("Table", DbItem.__table__).create)
        await connection.run_sync(cast("Table", ScopedNote.__table__).create)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """异步会话工厂（同库多会话，供并发用例）。"""
    yield async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """默认异步会话。"""
    async with session_factory() as session:
        yield session


def _demo_tenant(tenant_id: int) -> TenantContext:
    """构造测试租户上下文。

    Args:
        tenant_id: 租户主键。

    Returns:
        TenantContext: 租户上下文。
    """
    return TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户", tenant_id=tenant_id)


@pytest.mark.kiwi_id(1050)
async def test_crud_roundtrip_and_audit(session: AsyncSession) -> None:
    """create 落库（雪花 ID / 审计 / 版本）→ get / list / count / exists → update 版本自增。"""
    token = current_user_id.set(7)
    try:
        repo = DbItemRepository(session)
        item = await repo.create(name="甲", rank=1)
        assert item.id > 0
        assert item.created_by == 7 and item.updated_by == 7
        assert item.created_at is not None and item.version == 1
        assert await repo.count() == 1
        assert await repo.exists(item.id) is True
        assert await repo.exists(item.id + 1) is False

        fetched = await repo.get(item.id)
        assert fetched is not None and fetched.name == "甲"
        updated = await repo.update(item.id, name="乙", rank=2)
        assert updated is not None and updated.name == "乙" and updated.version == 2
        assert [row.name for row in await repo.list()] == ["乙"]
        assert await repo.update(999_999, name="丙") is None
    finally:
        current_user_id.reset(token)


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
async def test_scope_operator_translation(session: AsyncSession) -> None:
    """11 种作用域操作符统一翻译为 SQL WHERE（空 `in` 恒假）。"""
    repo = DbItemRepository(session)
    await repo.create(name="alpha", rank=2)

    cases: list[tuple[list[ScopeCondition], int]] = [
        ([ScopeCondition("name", "eq", "alpha")], 1),
        ([ScopeCondition("name", "ne", "beta")], 1),
        ([ScopeCondition("rank", "in", [1, 2])], 1),
        ([ScopeCondition("rank", "in", [])], 0),
        ([ScopeCondition("name", "like", "lph")], 1),
        ([ScopeCondition("rank", "gt", 1)], 1),
        ([ScopeCondition("rank", "gte", 2)], 1),
        ([ScopeCondition("rank", "lt", 3)], 1),
        ([ScopeCondition("rank", "lte", 2)], 1),
        ([ScopeCondition("rank", "between", (1, 3))], 1),
        ([ScopeCondition("rank", "is_null", None)], 0),
        ([ScopeCondition("name", "is_not_null", None)], 1),
    ]
    for conditions, expected in cases:
        repo.apply_scope(FakeScope(conditions))
        assert await repo.count() == expected, conditions


@pytest.mark.kiwi_id(1050)
async def test_scope_condition_errors(session: AsyncSession) -> None:
    """作用域条件非法：字段不存在 / 操作符不支持 / 值形态非法，一律 ConfigError。"""
    repo = DbItemRepository(session)
    await repo.create(name="alpha", rank=2)

    repo.apply_scope(FakeScope(ScopeCondition("ghost", "eq", 1)))
    with pytest.raises(ConfigError):
        await repo.count()

    repo.apply_scope(FakeScope(ScopeCondition("name", "regex", "x")))
    with pytest.raises(ConfigError):
        await repo.count()

    for condition in (
        ScopeCondition("rank", "in", 1),
        ScopeCondition("name", "like", 1),
        ScopeCondition("rank", "between", (1,)),
        ScopeCondition("rank", "between", 1),
    ):
        repo.apply_scope(FakeScope(condition))
        with pytest.raises(ConfigError):
            await repo.count()


@pytest.mark.kiwi_id(1050)
async def test_soft_delete_restore_and_unique_reuse(session: AsyncSession) -> None:
    """软删后不可见、唯一键释放复用；恢复后重新可见。"""
    repo = DbItemRepository(session)
    item = await repo.create(name="dup")
    assert await repo.soft_delete(item.id) is True
    assert await repo.get(item.id) is None
    assert await repo.exists(item.id) is False
    assert await repo.count() == 0
    assert await repo.soft_delete(item.id) is False

    second = await repo.create(name="dup")
    assert second.id != item.id

    assert await repo.soft_delete(second.id) is True
    stale = (await session.execute(select(DbItem).where(DbItem.id == item.id))).scalar_one()
    stale.restore()
    await session.flush()
    assert await repo.get(item.id) is not None
    assert await repo.get(second.id) is None


@pytest.mark.kiwi_id(1050)
async def test_delete_switch_and_hard_delete(session: AsyncSession) -> None:
    """delete 默认软删 / 关闭软删时物理删；hard_delete 可穿透软删过滤清理残留。"""
    soft_repo = DbItemRepository(session)
    soft = await soft_repo.create(name="a")
    assert await soft_repo.delete(soft.id) is True
    assert await soft_repo.get(soft.id) is None

    hard_repo = HardDeleteItemRepository(session)
    other = await hard_repo.create(name="b")
    assert await hard_repo.delete(other.id) is True
    raw = (await session.execute(select(DbItem).where(DbItem.id == other.id))).scalar_one_or_none()
    assert raw is None
    assert await hard_repo.delete(999_999) is False

    assert await hard_repo.hard_delete(soft.id) is True
    purged = (await session.execute(select(DbItem).where(DbItem.id == soft.id))).scalar_one_or_none()
    assert purged is None
    assert await hard_repo.hard_delete(999_999) is False


@pytest.mark.kiwi_id(1050)
async def test_tenant_write_and_read_scope(session: AsyncSession) -> None:
    """租户写侧注入 / 禁改；读侧强制过滤；跨租户不可见。"""
    token = set_tenant_context(_demo_tenant(7))
    try:
        repo = NoteRepository(session)
        note = await repo.create(title="n7")
        assert note.tenant_id == 7
        same = await repo.create(title="n7b", tenant_id=7)
        assert same.tenant_id == 7
        with pytest.raises(ConfigError):
            await repo.create(title="x", tenant_id=8)

        assert await repo.update(note.id, title="n7c") is not None
        with pytest.raises(ConfigError):
            await repo.update(note.id, tenant_id=8)

        token_other = set_tenant_context(_demo_tenant(8))
        try:
            other = await repo.create(title="n8")
            assert other.tenant_id == 8
        finally:
            reset_tenant_context(token_other)

        assert await repo.count() == 2
        assert await repo.get(other.id) is None
        assert await repo.exists(other.id) is False
        assert await repo.update(other.id, title="x") is None
        assert [row.title for row in await repo.list()] == ["n7c", "n7b"]
    finally:
        reset_tenant_context(token)


@pytest.mark.kiwi_id(1050)
async def test_tenant_scope_edge_branches(session: AsyncSession) -> None:
    """租户分支：上下文无主键不注入；声明与模型不符快速失败。"""
    repo = NoteRepository(session)
    assert repo.tenant_payload({"title": "x"}, creating=True) == {"title": "x"}

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
async def test_optimistic_lock_conflict(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """并发旧版本更新 flush 触发 StaleDataError，仓储转 ConcurrentConflictError（409）。"""
    async with session_factory() as first, session_factory() as second:
        first_repo = DbItemRepository(first)
        created = await first_repo.create(name="lock")
        await first.commit()

        second_repo = DbItemRepository(second)
        stale = await second_repo.get(created.id)
        assert stale is not None and stale.version == 1
        assert await first_repo.update(created.id, name="first") is not None
        await first.commit()
        with pytest.raises(ConcurrentConflictError):
            await second_repo.update(created.id, name="second")


@pytest.mark.kiwi_id(1050)
async def test_pagination_and_sort(session: AsyncSession) -> None:
    """分页 LIMIT/OFFSET（页码 / 偏移游标）+ 白名单排序 + 默认 id 升序 + 未知排序字段忽略。"""
    repo = DbItemRepository(session)
    await repo.create(name="a", rank=2)
    await repo.create(name="b", rank=1)
    await repo.create(name="c", rank=3)

    assert [row.name for row in await repo.list()] == ["a", "b", "c"]
    page = await repo.list_page(BasePageQuery(page=1, size=2, order_by="rank", order=["desc"]))
    assert [row.name for row in page] == ["c", "a"]
    page2 = await repo.list_page(BasePageQuery(page=2, size=2, order_by="rank", order=["desc"]))
    assert [row.name for row in page2] == ["b"]

    cursor = await repo.list_cursor(BaseCursorQuery(cursor="1", limit=2))
    assert [row.name for row in cursor] == ["b", "c"]
    first_batch = await repo.list_cursor(BaseCursorQuery(limit=1))
    assert [row.name for row in first_batch] == ["a"]

    ignored = await repo.list(sort=[SortSpec(field="ghost"), SortSpec(field="name", direction=SortDirection.DESC)])
    assert [row.name for row in ignored] == ["c", "b", "a"]
