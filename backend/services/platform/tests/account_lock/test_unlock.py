"""手动解锁用例（Kiwi 2211，03_07）。

覆盖：解锁清 `locked_until` / `failed_count` 并回填 `unlock_at` / `unlock_by` / `unlock_mode=manual`；
重复解锁与记录不存在抛 `AccountLockNotFoundError`（30007）；并发解锁经乐观锁抛 `ConcurrentConflictError`（10004）。

服务层直连共享租户库（`sys_user` / `sys_account_lock` 属 platform 服务租户库）：造数带用例
命名空间；会话一律由门代理引擎建（`shared_write` / `shared_tenant_engine`），**不豁免读写门**。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import AccountLockNotFoundError, ConcurrentConflictError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.user import LOCK_TYPE_MANUAL, UNLOCK_MODE_MANUAL
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.account_lock import MANUAL_LOCK_SENTINEL, AccountLockService
from tests_support.shared_access import shared_write

_LOCKED_AT = datetime(2026, 10, 14, 12, 0, 0)


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


@asynccontextmanager
async def _two_sessions(engine: AsyncEngine) -> AsyncGenerator[tuple[AsyncSession, AsyncSession]]:
    """在共享租户库上开两个**门代理**会话（并发乐观锁用例用）。

    引擎是门代理（`shared_tenant_engine`），`shared_write` 开出的会话每次操作自行取写门、
    写完即放，因此两个会话可以共存、不整段持锁、不需要任何豁免。乐观锁冲突由「A 的身份
    映射持旧 version」触发，与门是否串行无关。

    Args:
        engine: 共享租户库引擎（门代理）。

    Yields:
        tuple[AsyncSession, AsyncSession]: (会话 A, 会话 B)。
    """
    async with shared_write(engine) as session_a, shared_write(engine) as session_b:
        yield session_a, session_b


@pytest.mark.kiwi_id(2211)
async def test_unlock_restores_account_and_marks(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """解锁清账号锁定状态并回填解锁信息。"""
    async with shared_write(shared_tenant_engine) as session:
        user = await UserRepository(session).create(
            username=ns.code("u"), password_hash="x", name="U", locked_until=MANUAL_LOCK_SENTINEL, failed_count=5
        )
        lock = await AccountLockRepository(session).create(
            user_id=user.id, lock_type=LOCK_TYPE_MANUAL, reason="r", locked_at=_LOCKED_AT, locked_by=9
        )
        await session.commit()

        unlocked = await _service(session).unlock(lock.id, actor=7, now=datetime(2026, 10, 14, 13, 0, 0))
        assert unlocked.unlock_at == datetime(2026, 10, 14, 13, 0, 0)
        assert unlocked.unlock_by == 7 and unlocked.unlock_mode == UNLOCK_MODE_MANUAL

        stored = await UserRepository(session).get_by_id(user.id)
        assert stored is not None and stored.locked_until is None and stored.failed_count == 0


@pytest.mark.kiwi_id(2211)
async def test_unlock_repeat_and_missing_raise_30007(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """重复解锁已解锁记录 / 记录不存在 → `AccountLockNotFoundError`（30007）。"""
    missing_lock = int(ns.prefix[2:], 16) * 100 + 97
    async with shared_write(shared_tenant_engine) as session:
        user = await UserRepository(session).create(username=ns.code("u"), password_hash="x", name="U")
        lock = await AccountLockRepository(session).create(
            user_id=user.id, lock_type=LOCK_TYPE_MANUAL, reason="r", locked_at=_LOCKED_AT
        )
        await session.commit()
        service = _service(session)

        await service.unlock(lock.id, actor=1)
        with pytest.raises(AccountLockNotFoundError) as repeated:
            await service.unlock(lock.id, actor=1)
        assert repeated.value.code == 30007

        with pytest.raises(AccountLockNotFoundError) as missing:
            await service.unlock(missing_lock, actor=1)
        assert missing.value.code == 30007


@pytest.mark.kiwi_id(2211)
async def test_unlock_skips_missing_account(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """目标账号已不存在（历史脏数据）：只闭锁记录、跳过账号状态写回，不抛错。"""
    orphan_user = int(ns.prefix[2:], 16) * 100 + 98
    async with shared_write(shared_tenant_engine) as session:
        lock = await AccountLockRepository(session).create(
            user_id=orphan_user, lock_type=LOCK_TYPE_MANUAL, reason="r", locked_at=_LOCKED_AT
        )
        await session.commit()

        unlocked = await _service(session).unlock(lock.id, actor=3, now=datetime(2026, 10, 14, 13, 0, 0))
        assert unlocked.unlock_at == datetime(2026, 10, 14, 13, 0, 0)
        assert unlocked.unlock_mode == UNLOCK_MODE_MANUAL and unlocked.unlock_by == 3


@pytest.mark.kiwi_id(2211)
async def test_unlock_concurrent_optimistic_conflict(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """并发解锁：后到者乐观锁冲突 → `ConcurrentConflictError`（10004）。"""
    async with _two_sessions(shared_tenant_engine) as (session_a, session_b):
        user = await UserRepository(session_a).create(username=ns.code("c"), password_hash="x", name="C")
        lock = await AccountLockRepository(session_a).create(
            user_id=user.id, lock_type=LOCK_TYPE_MANUAL, reason="r", locked_at=_LOCKED_AT
        )
        await session_a.commit()

        # A 载入锁（version=1）后提交（保留身份映射快照）
        loaded = await AccountLockRepository(session_a).get(lock.id)
        assert loaded is not None
        await session_a.commit()

        # B 并发解锁（version → 2）
        await AccountLockRepository(session_b).update(
            lock.id, unlock_at=datetime(2026, 10, 14, 13, 0, 0), unlock_mode=UNLOCK_MODE_MANUAL
        )
        await session_b.commit()

        with pytest.raises(ConcurrentConflictError) as excinfo:
            await _service(session_a).unlock(lock.id, actor=7)
        assert excinfo.value.code == 10004
        await session_a.rollback()
