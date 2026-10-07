"""登录失败锁定（`fail_limit`）用例（Kiwi 2211，03_07）。

覆盖：达阈值写 `sys_account_lock`（`fail_limit` 行 + `expire_at`）；未达阈值不写；已有生效锁幂等跳过；
登录成功写回时关闭已到期的 `fail_limit` 锁（`unlock_mode='auto'` / `unlock_by=NULL`）；未到期不闭。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_platform.models.user import LOCK_TYPE_FAIL_LIMIT, UNLOCK_MODE_AUTO, SysUser
from bms_platform.repositories.account_lock import AccountLockRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.services.credentials import CredentialService


def _now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _page() -> BasePageQuery:
    """构造单页分页请求。

    Returns:
        BasePageQuery: 分页请求。
    """
    return BasePageQuery(page=1, size=20)


def _hasher() -> Pbkdf2PasswordHasher:
    """低迭代 PBKDF2（测试提速）。

    Returns:
        Pbkdf2PasswordHasher: 哈希实现。
    """
    return Pbkdf2PasswordHasher(iterations=100_000)


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话（含 `sys_user` + `sys_account_lock`）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


def _service(session: AsyncSession) -> CredentialService:
    """构造凭据服务（注入锁定仓储）。

    Args:
        session: 会话。

    Returns:
        CredentialService: 凭据服务。
    """
    return CredentialService(
        UserRepository(session),
        _hasher(),
        DbUnitOfWork(session),
        locks=AccountLockRepository(session),
    )


@pytest.mark.kiwi_id(2211)
async def test_fail_limit_written_and_idempotent() -> None:
    """达阈值写 fail_limit 锁（expire_at=now+窗口）；未达阈值不写；重复命中不新增。"""
    session, engine = await _session()
    await UserRepository(session).create(username="u", password_hash="x", name="U")
    await session.commit()
    locks = AccountLockRepository(session)
    service = _service(session)

    # 未达阈值（lock_seconds=0）不写锁
    await service.apply_login_state("u", success=False, failed_count=3)
    assert await locks.count_filtered() == 0
    await session.rollback()  # 结束只读事务，避免与方法内的显式事务冲突

    # 达阈值写 fail_limit 锁
    await service.apply_login_state("u", success=False, failed_count=5, lock_seconds=900)
    rows = await locks.list_filtered(_page())
    assert len(rows) == 1
    lock = rows[0]
    assert lock.lock_type == LOCK_TYPE_FAIL_LIMIT and lock.expire_at is not None
    assert lock.locked_by is None and lock.unlock_at is None
    await session.rollback()

    # 重复命中：已有生效锁 → 幂等跳过
    await service.apply_login_state("u", success=False, failed_count=5, lock_seconds=900)
    assert await locks.count_filtered() == 1
    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_fail_limit_auto_close_on_expired_success() -> None:
    """登录成功写回关闭已到期 fail_limit 锁（auto）；未到期不闭。"""
    session, engine = await _session()
    current = _now()
    users = UserRepository(session)
    expired = await users.create(username="expired", password_hash="x", name="E")
    future = await users.create(username="future", password_hash="x", name="F")
    locks = AccountLockRepository(session)
    await locks.create(
        user_id=expired.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="过期",
        locked_at=current - timedelta(hours=2),
        expire_at=current - timedelta(hours=1),
    )
    await locks.create(
        user_id=future.id,
        lock_type=LOCK_TYPE_FAIL_LIMIT,
        reason="未到期",
        locked_at=current - timedelta(minutes=1),
        expire_at=current + timedelta(minutes=14),
    )
    await session.commit()

    await _service(session).apply_login_state("expired", success=True)
    await _service(session).apply_login_state("future", success=True)

    expired_lock = await locks.get_open_by_user(expired.id, lock_type=LOCK_TYPE_FAIL_LIMIT)
    future_lock = await locks.get_open_by_user(future.id, lock_type=LOCK_TYPE_FAIL_LIMIT)
    assert future_lock is not None and future_lock.unlock_at is None
    assert expired_lock is None  # 已闭锁（unlock_at 非空 → 不再是未解锁记录）
    closed = await locks.list_filtered(_page())
    expired_row = next(row for row in closed if row.user_id == expired.id)
    assert expired_row.unlock_at is not None
    assert expired_row.unlock_mode == UNLOCK_MODE_AUTO and expired_row.unlock_by is None
    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_fail_limit_skips_without_lock_repo() -> None:
    """未注入锁定仓储时（向后兼容）只写账号状态、不落锁记录。"""
    session, engine = await _session()
    await UserRepository(session).create(username="u", password_hash="x", name="U")
    await session.commit()
    service = CredentialService(UserRepository(session), _hasher(), DbUnitOfWork(session))

    state = await service.apply_login_state("u", success=False, failed_count=5, lock_seconds=900)
    assert state.locked_until is not None
    assert await AccountLockRepository(session).count_filtered() == 0
    await engine.dispose()
