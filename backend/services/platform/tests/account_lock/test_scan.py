"""180 天不活跃扫描用例（Kiwi 2209，03_05）。

覆盖：含从未登录账号的候选口径；写 `sys_account_lock`（inactive 型）与 `sys_user.locked_until` 远期哨兵；
停用 / 已锁定 / 活跃账号排除；重复扫描幂等；`account.inactive_lock_days` 按租户覆盖。

服务层直连共享租户库（`sys_user` / `sys_account_lock` 属 platform 服务租户库）：扫描本身是整表
口径，库里必有他人行，故计数只作下界、结论断言落在**本次造的账号**上（按命名空间用户名收口）。
"""

from datetime import datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.config.base import BaseConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.user import LOCK_TYPE_INACTIVE, SysUser
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.account_lock import INACTIVE_LOCK_SENTINEL, AccountLockService
from tests_support.shared_access import shared_write

_NOW = datetime(2026, 9, 27, 12, 0, 0)


class _MappingSource(BaseConfigSource):
    """内存取数替身（仅返回预置键值）。"""

    def __init__(self, values: ConcurrentStableDict[str, object] | None = None) -> None:
        self._values = dict(values or {})

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """返回预置映射子集。

        Args:
            keys: 参数键序列（插入序）。

        Returns:
            ConcurrentStableDict[str, str]: 命中键 → 值（插入序）。
        """
        return ConcurrentStableDict({key: cast("str", self._values[key]) for key in keys if key in self._values})


async def _seed_user(
    session: AsyncSession,
    username: str,
    *,
    last_login_at: datetime | None,
    created_at: datetime,
    status: str = "enabled",
    locked_until: datetime | None = None,
) -> int:
    """插入用户并覆盖 `created_at`（模拟建号时间）。

    Args:
        session: 会话。
        username: 账号。
        last_login_at: 最近登录时间（None=从未登录）。
        created_at: 建号时间。
        status: 状态。
        locked_until: 锁定到期。

    Returns:
        int: 用户主键。
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
    user_id = user.id
    # `created_at` 不在仓储可写白名单：显式 UPDATE 覆盖（不动 version），随后 refresh 让
    # ORM 快照与库内一致，避免后续更新被判乐观锁冲突。
    await session.execute(update(SysUser).where(SysUser.id == user_id).values(created_at=created_at))
    await session.commit()
    await session.refresh(user)
    return user_id


def _service(session: AsyncSession, config: BaseConfigSource | None = None) -> AccountLockService:
    """构造账号锁定服务。

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
async def test_scan_locks_inactive_and_never_logged_in(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """命中：长期未登录与从未登录（按建号时间）账号被锁定并写 inactive 锁。"""
    fresh_name, stale_name, never_name = ns.code("fresh"), ns.code("stale"), ns.code("never")
    async with shared_write(shared_tenant_engine) as session:
        fresh = await _seed_user(session, fresh_name, last_login_at=_NOW - timedelta(days=1), created_at=_NOW)
        stale = await _seed_user(
            session, stale_name, last_login_at=_NOW - timedelta(days=200), created_at=_NOW - timedelta(days=300)
        )
        never = await _seed_user(session, never_name, last_login_at=None, created_at=_NOW - timedelta(days=200))

        # 范围限定到本次造的账号：扫描是全表口径，限定后不再触碰他人行（也就不会与并行 worker 撞版本）
        report = await _service(session).scan_inactive(now=_NOW, user_ids=ConcurrentStableList([stale, never]))
        assert report.scanned == 2 and report.locked == 2
        user_repo = UserRepository(session)

        assert (await user_repo.get_by_username(fresh_name)).locked_until is None  # type: ignore[union-attr]
        assert (await user_repo.get_by_username(stale_name)).locked_until == INACTIVE_LOCK_SENTINEL  # type: ignore[union-attr]
        assert (await user_repo.get_by_username(never_name)).locked_until == INACTIVE_LOCK_SENTINEL  # type: ignore[union-attr]
        assert fresh != stale and never != stale

        lock = await AccountLockRepository(session).get_active_by_user(stale)
        assert lock is not None and lock.lock_type == LOCK_TYPE_INACTIVE and lock.locked_at == _NOW
        assert lock.expire_at is None and lock.unlock_at is None


@pytest.mark.kiwi_id(2209)
async def test_scan_excludes_disabled_and_locked_and_is_idempotent(
    shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """排除：停用 / 已锁定；重复扫描幂等（本次账号的锁记录不再增加）。"""
    disabled_name = ns.code("disabled")
    locked_name = ns.code("locked")
    victim_name = ns.code("victim")
    async with shared_write(shared_tenant_engine) as session:
        disabled = await _seed_user(
            session, disabled_name, last_login_at=None, created_at=_NOW - timedelta(days=400), status="disabled"
        )
        locked = await _seed_user(
            session,
            locked_name,
            last_login_at=None,
            created_at=_NOW - timedelta(days=400),
            locked_until=INACTIVE_LOCK_SENTINEL,
        )
        victim = await _seed_user(session, victim_name, last_login_at=None, created_at=_NOW - timedelta(days=200))

        users = UserRepository(session)
        scope = ConcurrentStableList([disabled, locked, victim])
        first = await _service(session).scan_inactive(now=_NOW, user_ids=scope)
        assert first.scanned == 1 and first.locked == 1
        # 排除项：停用 / 已锁定账号本次不动
        assert (await users.get_by_username(disabled_name)).locked_until is None  # type: ignore[union-attr]
        assert (await users.get_by_username(locked_name)).locked_until == INACTIVE_LOCK_SENTINEL  # type: ignore[union-attr]
        assert disabled != locked != victim
        assert (await AccountLockRepository(session).get_active_by_user(victim)) is not None

        # 幂等：重复扫描不再为本次账号新增锁记录
        before = await AccountLockRepository(session).count_filtered(user_id=victim)
        second = await _service(session).scan_inactive(now=_NOW, user_ids=scope)
        assert second.scanned == 0 and second.locked == 0
        assert await AccountLockRepository(session).count_filtered(user_id=victim) == before


@pytest.mark.kiwi_id(2209)
async def test_scan_respects_inactive_lock_days_override(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """按租户覆盖 `account.inactive_lock_days`（30 天阈值命中更近的账号）。"""
    username = ns.code("u")
    async with shared_write(shared_tenant_engine) as session:
        user = await _seed_user(
            session, username, last_login_at=_NOW - timedelta(days=40), created_at=_NOW - timedelta(days=90)
        )
        users = UserRepository(session)
        scope = ConcurrentStableList([user])

        await _service(session).scan_inactive(now=_NOW, user_ids=scope)
        # 默认 180 天不命中：40 天未登录的账号不动
        assert (await users.get_by_username(username)).locked_until is None  # type: ignore[union-attr]

        override = _service(session, _MappingSource(ConcurrentStableDict({"account.inactive_lock_days": "30"})))
        result = await override.scan_inactive(now=_NOW, user_ids=scope)
        assert result.locked == 1
        assert (await users.get_by_username(username)).locked_until == INACTIVE_LOCK_SENTINEL  # type: ignore[union-attr]


@pytest.mark.kiwi_id(2209)
async def test_scan_skips_users_with_active_lock_record(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """已存在活跃锁记录（`unlock_at IS NULL`）的账号跳过，不重复置锁 / 写记录。"""
    username = ns.code("pending")
    async with shared_write(shared_tenant_engine) as session:
        user = await _seed_user(session, username, last_login_at=None, created_at=_NOW - timedelta(days=300))
        await AccountLockRepository(session).create(
            user_id=user,
            lock_type=LOCK_TYPE_INACTIVE,
            reason="既有锁",
            locked_at=_NOW - timedelta(days=1),
        )
        await session.commit()

        report = await _service(session).scan_inactive(now=_NOW, user_ids=ConcurrentStableList([user]))
        assert report.scanned == 1 and report.locked == 0
        # 结论：本次账号的账号状态未被改（仍有既有锁 → 跳过）
        row = await UserRepository(session).get_by_username(username)
        locks = await AccountLockRepository(session).count_filtered(user_id=user)
        assert row is not None and row.locked_until is None, f"row={row} locks={locks}"
        assert locks == 1, f"既有锁应保留 1 条，实际 {locks} 条"
