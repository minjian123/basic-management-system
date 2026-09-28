"""锁定记录列表与详情用例（Kiwi 2211，03_07）。

覆盖：`user_id` / `lock_type` / `active`（生效 / 非生效 / 全部）/ 锁定时间区间筛选 + 分页；
详情含已解锁记录；记录不存在抛 `AccountLockNotFoundError`（30007）。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import AccountLockNotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_org.models.account_lock import (
    LOCK_TYPE_FAIL_LIMIT,
    LOCK_TYPE_INACTIVE,
    LOCK_TYPE_MANUAL,
    UNLOCK_MODE_MANUAL,
)
from bms_org.models.user import SysUser
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.services.account_lock import AccountLockService

_NOW = datetime(2026, 10, 14, 12, 0, 0)


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


def _service(session: AsyncSession) -> AccountLockService:
    """构造账号锁定服务。

    Args:
        session: 会话。

    Returns:
        AccountLockService: 账号锁定服务。
    """
    return AccountLockService(
        UserRepository(session), AccountLockRepository(session), DbUnitOfWork(session), NullConfigSource()
    )


def _page(page: int = 1, size: int = 20) -> BasePageQuery:
    """构造分页请求。

    Args:
        page: 页码。
        size: 每页条数。

    Returns:
        BasePageQuery: 分页请求。
    """
    return BasePageQuery(page=page, size=size)


async def _seed(session: AsyncSession) -> tuple[int, int, int, int]:
    """播种两账号与四条锁记录（生效 / 非生效各两条）。

    Args:
        session: 会话。

    Returns:
        tuple[int, int, int, int]: (生效 fail_limit id, 已解锁 manual id, 生效 inactive id, 已到期 fail_limit id)。
    """
    users = UserRepository(session)
    u1 = await users.create(username="u1", password_hash="x", name="U1")
    u2 = await users.create(username="u2", password_hash="x", name="U2")
    locks = AccountLockRepository(session)
    active_fail = await locks.create(
        user_id=u1.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="生效",
        locked_at=_NOW - timedelta(minutes=5),
        expire_at=_NOW + timedelta(minutes=10),
    )
    unlocked_manual = await locks.create(
        user_id=u1.id,
        lock_type=LOCK_TYPE_MANUAL,
        reason="已解锁",
        locked_at=_NOW - timedelta(days=2),
        unlock_at=_NOW - timedelta(days=1),
        unlock_by=7,
        unlock_mode=UNLOCK_MODE_MANUAL,
    )
    active_inactive = await locks.create(
        user_id=u2.id,
        lock_type=LOCK_TYPE_INACTIVE,
        reason="生效",
        locked_at=_NOW - timedelta(days=200),
    )
    expired_fail = await locks.create(
        user_id=u2.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="已到期",
        locked_at=_NOW - timedelta(days=1),
        expire_at=_NOW - timedelta(hours=1),
    )
    await session.commit()
    return active_fail.id, unlocked_manual.id, active_inactive.id, expired_fail.id


@pytest.mark.kiwi_id(2211)
async def test_list_filters_and_pagination() -> None:
    """active / lock_type / user_id / 时间区间筛选与分页。"""
    session, engine = await _session()
    await _seed(session)
    service = _service(session)

    all_rows, total = await service.list_locks(_page(), now=_NOW)
    assert total == 4 and len(all_rows) == 4

    active_rows, active_total = await service.list_locks(_page(), active=True, now=_NOW)
    assert active_total == 2 and {row.lock_type for row in active_rows} == {LOCK_TYPE_FAIL_LIMIT, LOCK_TYPE_INACTIVE}

    inactive_rows, inactive_total = await service.list_locks(_page(), active=False, now=_NOW)
    assert inactive_total == 2 and any(row.unlock_at is not None for row in inactive_rows)

    manual_rows, manual_total = await service.list_locks(_page(), lock_type=LOCK_TYPE_MANUAL, now=_NOW)
    assert manual_total == 1 and manual_rows[0].lock_type == LOCK_TYPE_MANUAL

    by_user, by_user_total = await service.list_locks(_page(), user_id=all_rows[0].user_id, now=_NOW)
    assert by_user_total == 2 and all(row.user_id == all_rows[0].user_id for row in by_user)

    _ranged, ranged_total = await service.list_locks(
        _page(), locked_from=_NOW - timedelta(days=3), locked_to=_NOW, now=_NOW
    )
    assert ranged_total == 3

    first_page, _ = await service.list_locks(_page(page=1, size=2), now=_NOW)
    second_page, _ = await service.list_locks(_page(page=2, size=2), now=_NOW)
    assert len(first_page) == 2 and len(second_page) == 2
    assert {row.id for row in first_page}.isdisjoint({row.id for row in second_page})
    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_detail_includes_unlocked_and_missing() -> None:
    """详情含已解锁记录；不存在 → 30007。"""
    session, engine = await _session()
    _, unlocked_id, _, _ = await _seed(session)
    service = _service(session)

    record = await service.detail(unlocked_id)
    assert record.unlock_at is not None and record.unlock_mode == UNLOCK_MODE_MANUAL

    with pytest.raises(AccountLockNotFoundError) as excinfo:
        await service.detail(9999)
    assert excinfo.value.code == 30007
    await engine.dispose()
