"""180 天不活跃扫描用例（Kiwi 2209，03_05）。

覆盖：含从未登录账号的候选口径；写 `sys_account_lock`（inactive 型）与 `sys_user.locked_until` 远期哨兵；
停用 / 已锁定 / 活跃账号排除；重复扫描幂等；`account.inactive_lock_days` 按租户覆盖。
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.base import BaseConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_org.models.account_lock import LOCK_TYPE_INACTIVE
from bms_org.models.user import SysUser
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.services.account_lock import INACTIVE_LOCK_SENTINEL, AccountLockService

_NOW = datetime(2026, 9, 27, 12, 0, 0)


class _MappingSource(BaseConfigSource):
    """内存取数替身（仅返回预置键值）。"""

    def __init__(self, values: Mapping[str, object] | None = None) -> None:
        self._values = dict(values or {})

    async def get_many(self, keys: Sequence[str]) -> Mapping[str, str]:
        """返回预置映射子集。

        Args:
            keys: 参数键序列。

        Returns:
            Mapping[str, str]: 命中键 → 值。
        """
        return {key: cast("str", self._values[key]) for key in keys if key in self._values}


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话（`sys_user` + `sys_account_lock`）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


async def _seed_user(
    session: AsyncSession,
    username: str,
    *,
    last_login_at: datetime | None,
    created_at: datetime,
    status: str = "enabled",
    locked_until: datetime | None = None,
) -> SysUser:
    """插入用户并覆盖 `created_at`（模拟建号时间）。

    Args:
        session: 会话。
        username: 账号。
        last_login_at: 最近登录时间（None=从未登录）。
        created_at: 建号时间。
        status: 状态。
        locked_until: 锁定到期。

    Returns:
        SysUser: 用户记录。
    """
    repo = UserRepository(session)
    user = await repo.create(
        username=username,
        password_hash="x",
        name=username,
        status=status,
        last_login_at=last_login_at,
        locked_until=locked_until,
    )
    user.created_at = created_at
    await session.commit()
    return user


def _service(session: AsyncSession, config: BaseConfigSource | None = None) -> AccountLockService:
    """构造账号锁定服务（临时会话）。

    Args:
        session: 会话。
        config: 参数取数（缺省 Null → 180 天）。

    Returns:
        AccountLockService: 账号锁定服务。
    """
    return AccountLockService(
        UserRepository(session),
        AccountLockRepository(session),
        DbUnitOfWork(session),
        config or NullConfigSource(),
    )


@pytest.mark.kiwi_id(2209)
async def test_scan_locks_inactive_and_never_logged_in() -> None:
    """命中：长期未登录与从未登录（按建号时间）账号被锁定并写 inactive 锁。"""
    session, engine = await _session()
    fresh = await _seed_user(session, "fresh", last_login_at=_NOW - timedelta(days=1), created_at=_NOW)
    stale = await _seed_user(
        session, "stale", last_login_at=_NOW - timedelta(days=200), created_at=_NOW - timedelta(days=300)
    )
    never = await _seed_user(session, "never", last_login_at=None, created_at=_NOW - timedelta(days=200))

    report = await _service(session).scan_inactive(now=_NOW)
    assert report.scanned == 2 and report.locked == 2

    user_repo = UserRepository(session)
    assert await user_repo.get_by_id(fresh.id) is not None
    assert (await user_repo.get_by_username("fresh")).locked_until is None  # type: ignore[union-attr]
    assert (await user_repo.get_by_username("stale")).locked_until == INACTIVE_LOCK_SENTINEL  # type: ignore[union-attr]
    assert (await user_repo.get_by_username("never")).locked_until == INACTIVE_LOCK_SENTINEL  # type: ignore[union-attr]
    assert fresh.id != stale.id and never.id != stale.id

    lock = await AccountLockRepository(session).get_active_by_user(stale.id)
    assert lock is not None and lock.lock_type == LOCK_TYPE_INACTIVE and lock.locked_at == _NOW
    assert lock.expire_at is None and lock.unlock_at is None
    await engine.dispose()


@pytest.mark.kiwi_id(2209)
async def test_scan_excludes_disabled_and_locked_and_is_idempotent() -> None:
    """排除：停用 / 已锁定；重复扫描幂等（不新增锁记录）。"""
    session, engine = await _session()
    disabled = await _seed_user(
        session, "disabled", last_login_at=None, created_at=_NOW - timedelta(days=400), status="disabled"
    )
    locked = await _seed_user(
        session,
        "locked",
        last_login_at=None,
        created_at=_NOW - timedelta(days=400),
        locked_until=INACTIVE_LOCK_SENTINEL,
    )
    victim = await _seed_user(session, "victim", last_login_at=None, created_at=_NOW - timedelta(days=200))

    first = await _service(session).scan_inactive(now=_NOW)
    assert first.scanned == 1 and first.locked == 1

    second = await _service(session).scan_inactive(now=_NOW)
    assert second.scanned == 0 and second.locked == 0

    assert disabled.id != locked.id != victim.id
    assert (await AccountLockRepository(session).get_active_by_user(victim.id)) is not None
    await engine.dispose()


@pytest.mark.kiwi_id(2209)
async def test_scan_respects_inactive_lock_days_override() -> None:
    """按租户覆盖 `account.inactive_lock_days`（30 天阈值命中更近的账号）。"""
    session, engine = await _session()
    await _seed_user(session, "u", last_login_at=_NOW - timedelta(days=40), created_at=_NOW - timedelta(days=90))

    default_report = await _service(session).scan_inactive(now=_NOW)
    assert default_report.locked == 0  # 默认 180 天不命中

    override = _service(session, _MappingSource({"account.inactive_lock_days": "30"}))
    assert (await override.scan_inactive(now=_NOW)).locked == 1
    await engine.dispose()


@pytest.mark.kiwi_id(2209)
async def test_scan_skips_users_with_active_lock_record() -> None:
    """已存在活跃锁记录（`unlock_at IS NULL`）的账号跳过，不重复置锁 / 写记录。"""
    session, engine = await _session()
    user = await _seed_user(session, "pending", last_login_at=None, created_at=_NOW - timedelta(days=300))
    await AccountLockRepository(session).create(
        user_id=user.id,
        lock_type=LOCK_TYPE_INACTIVE,
        reason="既有锁",
        locked_at=_NOW - timedelta(days=1),
    )
    await session.commit()

    report = await _service(session).scan_inactive(now=_NOW)
    assert report.scanned == 1 and report.locked == 0
    assert (await UserRepository(session).get_by_username("pending")).locked_until is None  # type: ignore[union-attr]
    await engine.dispose()
