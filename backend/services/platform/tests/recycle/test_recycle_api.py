"""回收站接口：5 端点成功路径 / 失败 / 权限 / 幂等。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.audit.null import NullAuditCapturer
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ParamError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.idempotency.base import DEFAULT_IDEMPOTENCY_TTL, IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.dashboard import SysDashboardCard, SysDashboardCardI18n, SysDashboardTemplate
from bms_core.models.platform.form_design import SysFieldExt, SysFieldExtI18n, SysFormFieldAttr, SysFormLayout
from bms_core.models.platform.help import (
    SysHelpArticle,
    SysHelpArticleI18n,
    SysHelpArticleTarget,
    SysHelpCategory,
    SysHelpFeedback,
    SysHelpPackage,
)
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.recycle import SysRecycleLog
from bms_core.models.platform.role import SysRole
from bms_core.models.platform.user import SysUser, SysUserExtension
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.recycle.api import recycle as recycle_api
from bms_platform.domains.recycle.schemas.recycle import RecycleRestoreRequest

pytestmark = [
    pytest.mark.kiwi_id(2530),
    pytest.mark.own_db("回收站接口用例需按纳管表子集独立建表，验证分页 / 恢复 / 幂等，不污染共享库"),
]

_NOW = datetime(2026, 11, 18, 12, 0, 0)
_TABLES = (
    SysUser.__table__,
    SysUserExtension.__table__,
    SysRole.__table__,
    SysIcon.__table__,
    SysIconI18n.__table__,
    SysHelpCategory.__table__,
    SysHelpArticle.__table__,
    SysHelpArticleI18n.__table__,
    SysHelpArticleTarget.__table__,
    SysHelpFeedback.__table__,
    SysHelpPackage.__table__,
    SysDashboardCard.__table__,
    SysDashboardCardI18n.__table__,
    SysDashboardTemplate.__table__,
    SysFormLayout.__table__,
    SysFormFieldAttr.__table__,
    SysFieldExt.__table__,
    SysFieldExtI18n.__table__,
    SysRecycleLog.__table__,
    SysOutbox.__table__,
)


class MemoryIdempotency(IdempotencyStore):
    """测试替身：内存幂等键（首次 True + 结果复用）。"""

    plugin_name: str = "recycle_memory_idem"

    def __init__(self) -> None:
        """初始化（空键集）。"""
        self.seen: ConcurrentStableDict[str, IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableDict()

    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        """前置去重。"""
        del ttl
        return key not in self.seen

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果。"""
        return self.seen.get(key)

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> None:
        """写首次结果。"""
        del ttl
        self.seen.set(key, payload)

    async def release(self, key: str) -> None:
        """释放键（测试替身直接删除）。"""
        self.seen.pop(key, None)


@pytest.fixture
async def platform_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """独立 SQLite 库（回收站纳管表）。"""
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recycle_api.db'}")
    async with engine.begin() as connection:
        for table in _TABLES:
            await connection.run_sync(cast("Table", table).create, checkfirst=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _reset(session: AsyncSession) -> None:
    """结束隐式只读事务（直调路由时模拟每请求独立会话）。"""
    if session.in_transaction():
        await session.rollback()


async def _seed_article(session: AsyncSession, title: str, *, deleted: bool) -> SysHelpArticle:
    """造一篇文章（可软删）。"""
    category = SysHelpCategory(parent_id=0, name=f"分类-{title}", sort=1)
    session.add(category)
    await session.flush()
    article = SysHelpArticle(category_id=int(category.id), title=title)
    session.add(article)
    await session.flush()
    if deleted:
        article.deleted_at = _NOW
    await session.commit()
    return article


async def test_authenticated_without_permission_is_forbidden(client: AsyncClient) -> None:
    """未授予 recycle:* 的已登录用户：403。"""
    response = await client.get("/api/v1/recycle/modules")
    assert response.status_code == 403


async def test_module_item_detail_and_cleanup_routes(platform_session: AsyncSession) -> None:
    """模块 / 列表 / 详情 / 清理记录四个只读端点。"""
    article = await _seed_article(platform_session, "接口文章", deleted=True)
    article_id = int(article.id)
    log = SysRecycleLog(
        batch_key="recycle:20261118043000:abcd1234",
        table_name="sys_help_article",
        status="success",
        retention_days=30,
        cutoff_at=_NOW,
        deleted_count=1,
        started_at=_NOW,
        finished_at=_NOW,
    )
    platform_session.add(log)
    await platform_session.commit()
    uow = DbUnitOfWork(platform_session)
    modules = await recycle_api.list_modules(uow)
    assert modules.code == 0
    data = modules.data
    assert data is not None
    assert any(module.module_key == "help" for module in data.items)
    await _reset(platform_session)
    items = await recycle_api.list_items(uow, BasePageQuery(), "sys_help_article")
    assert items.data is not None
    assert items.data.total == 1
    assert items.data.list[0].title == "接口文章"
    await _reset(platform_session)
    detail = await recycle_api.get_item(uow, "sys_help_article", article_id)
    assert detail.data is not None
    assert detail.data.fields["标题"] == "接口文章"
    await _reset(platform_session)
    cleanups = await recycle_api.list_cleanups(uow, BasePageQuery())
    assert cleanups.data is not None
    assert cleanups.data.total == 1
    assert cleanups.data.list[0].batch_key == "recycle:20261118043000:abcd1234"


async def test_cleanups_filters_and_validation(platform_session: AsyncSession) -> None:
    """清理记录筛选生效；状态非法 / 时间范围颠倒按 10001 拒绝。"""
    platform_session.add_all(
        (
            SysRecycleLog(
                batch_key="recycle:run-a",
                table_name="sys_help_article",
                status="success",
                retention_days=30,
                cutoff_at=_NOW,
                deleted_count=2,
                started_at=_NOW,
            ),
            SysRecycleLog(
                batch_key="recycle:run-b",
                table_name="sys_role",
                status="failed",
                retention_days=30,
                cutoff_at=_NOW,
                deleted_count=0,
                started_at=_NOW - timedelta(days=1),
            ),
        )
    )
    await platform_session.commit()
    uow = DbUnitOfWork(platform_session)
    only_success = await recycle_api.list_cleanups(uow, BasePageQuery(), status="success")
    assert only_success.data is not None
    assert only_success.data.total == 1
    await _reset(platform_session)
    only_table = await recycle_api.list_cleanups(uow, BasePageQuery(), table_name="sys_role")
    assert only_table.data is not None
    assert only_table.data.total == 1
    await _reset(platform_session)
    ranged = await recycle_api.list_cleanups(uow, BasePageQuery(), started_from=_NOW)
    assert ranged.data is not None
    assert ranged.data.total == 1
    await _reset(platform_session)
    upper = await recycle_api.list_cleanups(uow, BasePageQuery(), started_to=_NOW - timedelta(hours=1))
    assert upper.data is not None
    assert upper.data.total == 1
    await _reset(platform_session)
    with pytest.raises(ParamError):
        await recycle_api.list_cleanups(uow, BasePageQuery(), status="unknown")
    await _reset(platform_session)
    with pytest.raises(ParamError):
        await recycle_api.list_cleanups(
            uow,
            BasePageQuery(),
            started_from=_NOW,
            started_to=_NOW - timedelta(days=1),
        )


async def test_detail_missing_record(platform_session: AsyncSession) -> None:
    """详情不存在按 95001 拒绝。"""
    uow = DbUnitOfWork(platform_session)
    with pytest.raises(Exception) as exc:
        await recycle_api.get_item(uow, "sys_help_article", 999999999)
    assert getattr(exc.value, "code", None) == 95001


class _LostIdempotency(MemoryIdempotency):
    """测试替身：键已存在但结果丢失（走「继续执行」分支）。"""

    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        del key, ttl
        return False

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        del key
        return None


async def test_restore_route_lost_idempotency_result(platform_session: AsyncSession) -> None:
    """幂等键已占用但结果丢失时继续执行恢复。"""
    article = await _seed_article(platform_session, "幂等丢失文章", deleted=True)
    article_id = int(article.id)
    uow = DbUnitOfWork(platform_session)
    result = await recycle_api.restore_item(
        RecycleRestoreRequest(table="sys_help_article", id=article_id),
        uow,
        _LostIdempotency(),
        None,
        NullAuditCapturer(),
        MemoryCacheRegion(domain="generic"),
        "lost-key",
    )
    assert result.data is not None
    assert result.data.restored is True


async def test_restore_route_without_idempotency_key(platform_session: AsyncSession) -> None:
    """不带幂等键的普通恢复成功。"""
    article = await _seed_article(platform_session, "无幂等键文章", deleted=True)
    article_id = int(article.id)
    uow = DbUnitOfWork(platform_session)
    result = await recycle_api.restore_item(
        RecycleRestoreRequest(table="sys_help_article", id=article_id),
        uow,
        MemoryIdempotency(),
        None,
        NullAuditCapturer(),
        MemoryCacheRegion(domain="generic"),
        None,
    )
    assert result.data is not None
    assert result.data.restored is True


async def test_restore_route_and_idempotency(platform_session: AsyncSession) -> None:
    """恢复端点：清空删除态；同幂等键第二次返回首次结果。"""
    article = await _seed_article(platform_session, "待恢复接口文章", deleted=True)
    article_id = int(article.id)
    uow = DbUnitOfWork(platform_session)
    idempotency = MemoryIdempotency()
    cache = MemoryCacheRegion(domain="generic")
    request = RecycleRestoreRequest(table="sys_help_article", id=article_id)
    first = await recycle_api.restore_item(request, uow, idempotency, None, NullAuditCapturer(), cache, "restore-key-1")
    assert first.data is not None
    assert first.data.restored is True
    await _reset(platform_session)
    second = await recycle_api.restore_item(
        request, uow, idempotency, None, NullAuditCapturer(), cache, "restore-key-1"
    )
    assert second.data is not None
    assert second.data.restored is True
    await platform_session.refresh(article)
    assert article.deleted_at is None


async def test_restore_route_conflict_and_unsupported(platform_session: AsyncSession) -> None:
    """冲突 / 隐藏子表走业务错误码。"""
    live = SysUser(username="bob", name="在用", password_hash="x", status="enabled")
    deleted = SysUser(username="bob", name="已删", password_hash="x", status="enabled")
    platform_session.add_all((live, deleted))
    await platform_session.flush()
    deleted_id = int(deleted.id)
    deleted.deleted_at = _NOW
    await platform_session.commit()
    uow = DbUnitOfWork(platform_session)
    idempotency = MemoryIdempotency()
    cache = MemoryCacheRegion(domain="generic")
    with pytest.raises(Exception) as exc:
        await recycle_api.restore_item(
            RecycleRestoreRequest(table="sys_user", id=deleted_id),
            uow,
            idempotency,
            None,
            NullAuditCapturer(),
            cache,
            None,
        )
    assert getattr(exc.value, "code", None) == 95002
    await _reset(platform_session)
    with pytest.raises(Exception) as hidden:
        await recycle_api.restore_item(
            RecycleRestoreRequest(table="sys_help_article_i18n", id=deleted_id),
            uow,
            idempotency,
            None,
            NullAuditCapturer(),
            cache,
            None,
        )
    assert getattr(hidden.value, "code", None) == 95004
