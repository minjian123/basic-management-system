"""登录失败锁定（`fail_limit`）用例（Kiwi 2211，03_07）。

覆盖：达阈值写 `sys_account_lock`（`fail_limit` 行 + `expire_at`）；未达阈值不写；已有生效锁幂等跳过；
登录成功写回时关闭已到期的 `fail_limit` 锁（`unlock_mode='auto'` / `unlock_by=NULL`）；未到期不闭。

服务层直连共享租户库：`sys_user` / `sys_account_lock` 属 platform 服务租户库（`bms_platform_{code}`），
单库化后落共享租户库；用户名与用户主键带用例命名空间，断言按本人用户过滤。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.user import LOCK_TYPE_FAIL_LIMIT, UNLOCK_MODE_AUTO
from bms_core.schemas.pagination import BasePageQuery
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.credentials import CredentialService
from tests_support.shared_access import shared_write


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
async def test_fail_limit_written_and_idempotent(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """达阈值写 fail_limit 锁（expire_at=now+窗口）；未达阈值不写；重复命中不新增。"""
    username = ns.code("u")
    async with shared_write(shared_tenant_engine) as session:
        user = await UserRepository(session).create(username=username, password_hash="x", name="U")
        await session.commit()
        locks = AccountLockRepository(session)
        service = _service(session)

        # 未达阈值（lock_seconds=0）不写锁
        await service.apply_login_state(username, success=False, failed_count=3)
        assert await locks.count_filtered(user_id=user.id) == 0
        await session.rollback()  # 结束只读事务，避免与方法内的显式事务冲突

        # 达阈值写 fail_limit 锁
        await service.apply_login_state(username, success=False, failed_count=5, lock_seconds=900)
        rows = await locks.list_filtered(_page(), user_id=user.id)
        assert len(rows) == 1
        lock = rows[0]
        assert lock.lock_type == LOCK_TYPE_FAIL_LIMIT and lock.expire_at is not None
        assert lock.locked_by is None and lock.unlock_at is None
        await session.rollback()

        # 重复命中：已有生效锁 → 幂等跳过
        await service.apply_login_state(username, success=False, failed_count=5, lock_seconds=900)
        assert await locks.count_filtered(user_id=user.id) == 1


@pytest.mark.kiwi_id(2211)
async def test_fail_limit_auto_close_on_expired_success(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """登录成功写回关闭已到期 fail_limit 锁（auto）；未到期不闭。"""
    current = _now()
    expired_name = ns.code("expired")
    future_name = ns.code("future")
    async with shared_write(shared_tenant_engine) as session:
        users = UserRepository(session)
        expired = await users.create(username=expired_name, password_hash="x", name="E")
        future = await users.create(username=future_name, password_hash="x", name="F")
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

        await _service(session).apply_login_state(expired_name, success=True)
        await _service(session).apply_login_state(future_name, success=True)

        expired_lock = await locks.get_open_by_user(expired.id, lock_type=LOCK_TYPE_FAIL_LIMIT)
        future_lock = await locks.get_open_by_user(future.id, lock_type=LOCK_TYPE_FAIL_LIMIT)
        assert future_lock is not None and future_lock.unlock_at is None
        assert expired_lock is None  # 已闭锁（unlock_at 非空 → 不再是未解锁记录）
        closed = await locks.list_filtered(_page(), user_id=expired.id)
        expired_row = next(row for row in closed if row.user_id == expired.id)
        assert expired_row.unlock_at is not None
        assert expired_row.unlock_mode == UNLOCK_MODE_AUTO and expired_row.unlock_by is None


@pytest.mark.kiwi_id(2211)
async def test_fail_limit_skips_without_lock_repo(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """未注入锁定仓储时（向后兼容）只写账号状态、不落锁记录。"""
    async with shared_write(shared_tenant_engine) as session:
        user = await UserRepository(session).create(username=ns.code("u"), password_hash="x", name="U")
        await session.commit()
        service = CredentialService(UserRepository(session), _hasher(), DbUnitOfWork(session))

        state = await service.apply_login_state(ns.code("u"), success=False, failed_count=5, lock_seconds=900)
        assert state.locked_until is not None
        assert await AccountLockRepository(session).count_filtered(user_id=user.id) == 0
