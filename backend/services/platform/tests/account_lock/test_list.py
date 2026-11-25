"""锁定记录列表与详情用例（Kiwi 2211，03_07）。

覆盖：`user_id` / `lock_type` / `active`（生效 / 非生效 / 全部）/ 锁定时间区间筛选 + 分页；
详情含已解锁记录；记录不存在抛 `AccountLockNotFoundError`（30007）。

服务层直连共享租户库（`sys_user` / `sys_account_lock` 属 platform 服务租户库）：造数带用例
命名空间；全部断言按**本人用户**过滤，另一账号仅作「他人数据」对照，验证 `user_id` 过滤生效。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import AccountLockNotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.user import (
    LOCK_TYPE_FAIL_LIMIT,
    LOCK_TYPE_INACTIVE,
    LOCK_TYPE_MANUAL,
    UNLOCK_MODE_MANUAL,
)
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.account_lock import AccountLockService
from tests_support.shared_access import shared_write

_NOW = datetime(2026, 10, 14, 12, 0, 0)


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


async def _seed(session: AsyncSession, ns: Namespace) -> tuple[int, int, int, int, int, int]:
    """播种两账号：主账号四条锁（生效 / 非生效各两条），对照账号两条（供 `get_open_by_user`）。

    Args:
        session: 会话。
        ns: 用例命名空间。

    Returns:
        tuple[int, int, int, int, int, int]: (主账号 id, 对照账号 id, 生效 fail_limit id,
        已解锁 manual id, 生效 inactive id, 已到期 fail_limit id)。
    """
    users = UserRepository(session)
    owner = await users.create(username=ns.code("owner"), password_hash="x", name="O")
    other = await users.create(username=ns.code("other"), password_hash="x", name="X")
    locks = AccountLockRepository(session)
    active_fail = await locks.create(
        user_id=owner.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="生效",
        locked_at=_NOW - timedelta(minutes=5),
        expire_at=_NOW + timedelta(minutes=10),
    )
    unlocked_manual = await locks.create(
        user_id=owner.id,
        lock_type=LOCK_TYPE_MANUAL,
        reason="已解锁",
        locked_at=_NOW - timedelta(days=2),
        unlock_at=_NOW - timedelta(days=1),
        unlock_by=7,
        unlock_mode=UNLOCK_MODE_MANUAL,
    )
    active_inactive = await locks.create(
        user_id=owner.id,
        lock_type=LOCK_TYPE_INACTIVE,
        reason="生效",
        locked_at=_NOW - timedelta(days=200),
    )
    expired_fail = await locks.create(
        user_id=owner.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="已到期",
        locked_at=_NOW - timedelta(days=1),
        expire_at=_NOW - timedelta(hours=1),
    )
    # 对照账号：只用于验证 user_id 过滤与 get_open_by_user 的跨用户隔离
    await locks.create(
        user_id=other.id,
        lock_type=LOCK_TYPE_INACTIVE,
        reason="他人生效",
        locked_at=_NOW - timedelta(days=200),
    )
    await locks.create(
        user_id=other.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="他人已到期",
        locked_at=_NOW - timedelta(days=1),
        expire_at=_NOW - timedelta(hours=1),
    )
    await session.commit()
    return owner.id, other.id, active_fail.id, unlocked_manual.id, active_inactive.id, expired_fail.id


@pytest.mark.kiwi_id(2211)
async def test_list_filters_and_pagination(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """active / lock_type / user_id / 时间区间筛选与分页（一律按本人用户收口）。"""
    async with shared_write(shared_tenant_engine) as session:
        owner, other, *_ = await _seed(session, ns)
        service = _service(session)

        all_rows, total = await service.list_locks(_page(), user_id=owner, now=_NOW)
        assert total == 4 and len(all_rows) == 4

        active_rows, active_total = await service.list_locks(_page(), user_id=owner, active=True, now=_NOW)
        assert active_total == 2 and {row.lock_type for row in active_rows} == {
            LOCK_TYPE_FAIL_LIMIT,
            LOCK_TYPE_INACTIVE,
        }

        inactive_rows, inactive_total = await service.list_locks(_page(), user_id=owner, active=False, now=_NOW)
        assert inactive_total == 2 and any(row.unlock_at is not None for row in inactive_rows)

        manual_rows, manual_total = await service.list_locks(
            _page(), user_id=owner, lock_type=LOCK_TYPE_MANUAL, now=_NOW
        )
        assert manual_total == 1 and manual_rows[0].lock_type == LOCK_TYPE_MANUAL

        # user_id 过滤生效：对照账号只有自己那两条，取不到主账号的行
        other_rows, other_total = await service.list_locks(_page(), user_id=other, now=_NOW)
        assert other_total == 2 and all(row.user_id == other for row in other_rows)

        _ranged, ranged_total = await service.list_locks(
            _page(), user_id=owner, locked_from=_NOW - timedelta(days=3), locked_to=_NOW, now=_NOW
        )
        assert ranged_total == 3

        first_page, _ = await service.list_locks(_page(page=1, size=2), user_id=owner, now=_NOW)
        second_page, _ = await service.list_locks(_page(page=2, size=2), user_id=owner, now=_NOW)
        assert len(first_page) == 2 and len(second_page) == 2
        assert {row.id for row in first_page}.isdisjoint({row.id for row in second_page})


@pytest.mark.kiwi_id(2211)
async def test_detail_includes_unlocked_and_missing(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """详情含已解锁记录；不存在 → 30007。"""
    async with shared_write(shared_tenant_engine) as session:
        _, _, _, unlocked_id, _, _ = await _seed(session, ns)
        service = _service(session)

        record = await service.detail(unlocked_id)
        assert record.unlock_at is not None and record.unlock_mode == UNLOCK_MODE_MANUAL

        with pytest.raises(AccountLockNotFoundError) as excinfo:
            await service.detail(int(ns.prefix[2:], 16) * 100 + 99)
        assert excinfo.value.code == 30007


@pytest.mark.kiwi_id(2211)
async def test_get_open_by_user_without_lock_type(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """仓储：`lock_type` 缺省（不过滤类型）取最近一条未解锁记录；带类型时按类型过滤。"""
    async with shared_write(shared_tenant_engine) as session:
        owner, other, active_fail_id, _, active_inactive_id, _ = await _seed(session, ns)
        locks = AccountLockRepository(session)

        # 主账号：生效 fail_limit（-5 分钟）+ 已解锁 manual → 缺省类型取生效那条
        any_open = await locks.get_open_by_user(owner)
        assert any_open is not None and any_open.id == active_fail_id

        # 对照账号：生效 inactive（-200 天）+ 已到期未闭锁 fail_limit（-1 天）→ 取 locked_at 最新
        newest = await locks.get_open_by_user(other)
        assert newest is not None and newest.unlock_at is None and newest.id != active_inactive_id

        typed = await locks.get_open_by_user(other, lock_type=LOCK_TYPE_INACTIVE)
        assert typed is not None and typed.id != active_fail_id
        assert await locks.get_open_by_user(int(ns.prefix[2:], 16) * 100 + 99) is None
