"""手动锁定（`manual`）用例（Kiwi 2211，03_07）。

覆盖：写 manual 行 + `locked_until` 远期哨兵 + `expire_at=NULL` + `locked_by=操作者`；已生效锁幂等返回既有；
目标用户不存在抛 `NotFoundError`（10002）。

服务层直连共享租户库：`sys_user` / `sys_account_lock` 属 platform 服务租户库（`bms_platform_{code}`），
单库化后落共享租户库；造数带用例命名空间，断言按本人用户过滤，不依赖「库内只有本用例数据」。
"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import NotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.user import LOCK_TYPE_MANUAL
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.account_lock import MANUAL_LOCK_SENTINEL, AccountLockService
from tests_support.shared_access import shared_write


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
async def test_lock_manual_writes_and_is_idempotent(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """写 manual 锁并置远期哨兵；重复锁定幂等返回既有、不新增。"""
    async with shared_write(shared_tenant_engine) as session:
        user = await UserRepository(session).create(username=ns.code("u"), password_hash="x", name="U")
        await session.commit()
        service = _service(session)

        lock = await service.lock_manual(user.id, reason="违规处置", actor=99, now=datetime(2026, 10, 14, 12, 0, 0))
        assert lock.lock_type == LOCK_TYPE_MANUAL and lock.reason == "违规处置"
        assert lock.locked_by == 99 and lock.expire_at is None and lock.unlock_at is None

        # 重复锁定：已有生效锁 → 幂等返回既有、不新增（只统计本人用户，他人锁不参与）
        again = await service.lock_manual(user.id, reason="重复", actor=100)
        assert again.id == lock.id
        assert await AccountLockRepository(session).count_filtered(user_id=user.id) == 1

        stored = await UserRepository(session).get_by_id(user.id)
        assert stored is not None and stored.locked_until == MANUAL_LOCK_SENTINEL


@pytest.mark.kiwi_id(2211)
async def test_lock_manual_missing_user(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """目标用户不存在 → `NotFoundError`（10002 / 404）。"""
    missing = int(ns.prefix[2:], 16) * 100 + 99
    async with shared_write(shared_tenant_engine) as session:
        with pytest.raises(NotFoundError) as excinfo:
            await _service(session).lock_manual(missing, actor=1)
        assert excinfo.value.code == 10002
