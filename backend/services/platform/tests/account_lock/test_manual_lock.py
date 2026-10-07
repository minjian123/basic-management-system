"""手动锁定（`manual`）用例（Kiwi 2211，03_07）。

覆盖：写 manual 行 + `locked_until` 远期哨兵 + `expire_at=NULL` + `locked_by=操作者`；已生效锁幂等返回既有；
目标用户不存在抛 `NotFoundError`（10002）。
"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import NotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_platform.models.user import LOCK_TYPE_MANUAL, SysUser
from bms_platform.repositories.account_lock import AccountLockRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.services.account_lock import MANUAL_LOCK_SENTINEL, AccountLockService


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


def _service(session: AsyncSession) -> AccountLockService:
    """构造账号锁定服务（Null 参数取数）。

    Args:
        session: 会话。

    Returns:
        AccountLockService: 账号锁定服务。
    """
    return AccountLockService(
        UserRepository(session), AccountLockRepository(session), DbUnitOfWork(session), NullConfigSource()
    )


@pytest.mark.kiwi_id(2211)
async def test_lock_manual_writes_and_is_idempotent() -> None:
    """写 manual 锁并置远期哨兵；重复锁定幂等返回既有、不新增。"""
    session, engine = await _session()
    user = await UserRepository(session).create(username="u", password_hash="x", name="U")
    await session.commit()
    user_id = user.id
    service = _service(session)

    lock = await service.lock_manual(user_id, reason="违规处置", actor=99, now=datetime(2026, 10, 14, 12, 0, 0))
    assert lock.lock_type == LOCK_TYPE_MANUAL and lock.reason == "违规处置"
    assert lock.locked_by == 99 and lock.expire_at is None and lock.unlock_at is None

    # 重复锁定：已有生效锁 → 幂等返回既有、不新增
    again = await service.lock_manual(user_id, reason="重复", actor=100)
    assert again.id == lock.id
    assert await AccountLockRepository(session).count_filtered() == 1

    stored = await UserRepository(session).get_by_id(user_id)
    assert stored is not None and stored.locked_until == MANUAL_LOCK_SENTINEL
    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_lock_manual_missing_user() -> None:
    """目标用户不存在 → `NotFoundError`（10002 / 404）。"""
    session, engine = await _session()
    with pytest.raises(NotFoundError) as excinfo:
        await _service(session).lock_manual(9999, actor=1)
    assert excinfo.value.code == 10002
    await engine.dispose()
