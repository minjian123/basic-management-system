"""手动解锁用例（Kiwi 2211，03_07）。

覆盖：解锁清 `locked_until` / `failed_count` 并回填 `unlock_at` / `unlock_by` / `unlock_mode=manual`；
重复解锁与记录不存在抛 `AccountLockNotFoundError`（30007）；并发解锁经乐观锁抛 `ConcurrentConflictError`（10004）。
"""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import AccountLockNotFoundError, ConcurrentConflictError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_org.models.account_lock import LOCK_TYPE_MANUAL, UNLOCK_MODE_MANUAL
from bms_org.models.user import SysUser
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.services.account_lock import MANUAL_LOCK_SENTINEL, AccountLockService

_LOCKED_AT = datetime(2026, 10, 14, 12, 0, 0)


async def _memory_session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时内存 SQLite 会话。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


async def _file_sessions(tmp_path: Path) -> tuple[AsyncSession, AsyncSession, AsyncEngine]:
    """建共享文件的 SQLite 两个会话（用于并发乐观锁用例）。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        tuple[AsyncSession, AsyncSession, AsyncEngine]: (会话 A, 会话 B, 引擎)。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lock.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), factory(), engine


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


@pytest.mark.kiwi_id(2211)
async def test_unlock_restores_account_and_marks() -> None:
    """解锁清账号锁定状态并回填解锁信息。"""
    session, engine = await _memory_session()
    user = await UserRepository(session).create(
        username="u", password_hash="x", name="U", locked_until=MANUAL_LOCK_SENTINEL, failed_count=5
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
    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_unlock_repeat_and_missing_raise_30007() -> None:
    """重复解锁已解锁记录 / 记录不存在 → `AccountLockNotFoundError`（30007）。"""
    session, engine = await _memory_session()
    user = await UserRepository(session).create(username="u", password_hash="x", name="U")
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
        await service.unlock(9999, actor=1)
    assert missing.value.code == 30007
    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_unlock_concurrent_optimistic_conflict(tmp_path: Path) -> None:
    """并发解锁：后到者乐观锁冲突 → `ConcurrentConflictError`（10004）。"""
    session_a, session_b, engine = await _file_sessions(tmp_path)
    user = await UserRepository(session_a).create(username="u", password_hash="x", name="U")
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

    await session_a.close()
    await session_b.close()
    await engine.dispose()
