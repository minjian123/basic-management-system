"""用户完整域服务路径补齐用例（`02_01`）：入参校验 / 保护分支 / 随机口令生成。

补齐 `services/users_admin.py` 经端点不可达的路径（契约层已把字面量收敛，非法状态 /
非法联系方式无法经 HTTP 构造）：状态与联系方式校验、空角色短路、更新联系方式分支、
自身保护分支，以及随机初始密码的重试与失败兜底。
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import InternalError, ParamError, UserProtectedError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.outbox.null import NullOutboxStore
from bms_platform.repositories.account_lock import AccountLockRepository
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.services.users_admin import (
    _GENERATED_PASSWORD_ATTEMPTS,  # pyright: ignore[reportPrivateUsage]
    UserAdminService,
)
from tests.role import helpers


class _Hasher:
    """口令哈希器替身（回显可辨串）。"""

    def hash(self, password: str) -> str:
        """生成可辨哈希串。

        Args:
            password: 口令明文。

        Returns:
            str: 可辨哈希串。
        """
        return f"hash::{password}"


class _Policy:
    """密码策略替身：前 `valid_after` 次校验返回违例，其后放行。"""

    def __init__(self, *, valid_after: int = 0) -> None:
        """初始化。

        Args:
            valid_after: 允许通过之前返回违例的次数。
        """
        self.valid_after = valid_after
        self.calls = 0

    async def validate(self, password: str, *, username: str) -> ConcurrentStableList[str]:
        """校验密码（前若干次恒返回违例）。

        Args:
            password: 口令明文（忽略）。
            username: 登录账号（忽略）。

        Returns:
            ConcurrentStableList[str]: 违例清单（空 = 通过）。
        """
        del password, username
        self.calls += 1
        if self.calls > self.valid_after:
            return ConcurrentStableList()
        return ConcurrentStableList(["weak"])

    async def reused(self, password: str, *, history: ConcurrentStableList[str]) -> bool:
        """历史重复判定（替身恒 False）。

        Args:
            password: 口令明文（忽略）。
            history: 历史哈希（忽略）。

        Returns:
            bool: False。
        """
        del password, history
        return False

    async def history_count(self) -> int:
        """历史保留条数。

        Returns:
            int: 3。
        """
        return 3


class _Sessions:
    """会话失效客户端替身（恒成功）。"""

    async def revoke_user_sessions(self, user_id: int, *, reason: str) -> bool:
        """撤销该用户全部会话（替身恒 True）。

        Args:
            user_id: 用户主键（忽略）。
            reason: 撤销原因（忽略）。

        Returns:
            bool: True。
        """
        del user_id, reason
        return True


def _service(
    target: AsyncSession,
    *,
    policy: Any = None,
    hasher: Any = None,
    sessions: Any = None,
) -> UserAdminService:
    """构造用户完整域服务（替身注入哈希器 / 策略 / 会话客户端）。

    Args:
        target: 会话。
        policy: 密码策略替身。
        hasher: 口令哈希器替身。
        sessions: 会话失效客户端替身。

    Returns:
        UserAdminService: 用户完整域服务。
    """
    hasher_impl: Any = hasher if hasher is not None else _Hasher()
    policy_impl: Any = policy if policy is not None else _Policy()
    sessions_impl: Any = sessions if sessions is not None else _Sessions()
    return UserAdminService(
        target,
        DbUnitOfWork(target),
        UserRepository(target),
        UserRoleRepository(target),
        RoleRepository(target),
        AccountLockRepository(target),
        hasher_impl,
        policy_impl,
        NullOutboxStore(),
        sessions_impl,
    )


async def _seed_user(target: AsyncSession, username: str = "u1") -> int:
    """直插一个启用用户。

    Args:
        target: 会话。
        username: 登录账号。

    Returns:
        int: 用户主键。
    """
    user = await UserRepository(target).create(username=username, password_hash="h", name="用户")
    await target.commit()
    return user.id


async def test_create_user_rejects_invalid_status_and_contact() -> None:
    """新建：状态非法（10001）与联系方式格式非法（10001）在事务前拒绝。"""
    target, engine = await helpers.session()
    service = _service(target)
    with pytest.raises(ParamError):
        await service.create_user(
            username="u1",
            name="U1",
            password=None,
            pwd_reset_required=False,
            email=None,
            phone=None,
            status="bad",
        )
    with pytest.raises(ParamError):
        await service.create_user(
            username="u2",
            name="U2",
            password=None,
            pwd_reset_required=False,
            email="not-an-email",
            phone=None,
            status="enabled",
        )
    await engine.dispose()


async def test_list_user_roles_empty_when_unassigned() -> None:
    """角色查看：用户无直接角色时短路返回空清单。"""
    target, engine = await helpers.session()
    user_id = await _seed_user(target)
    roles = await _service(target).list_user_roles(user_id)
    assert list(roles) == []
    await engine.dispose()


async def test_update_status_rejects_invalid_status() -> None:
    """启停：目标状态非法（10001）在事务前拒绝。"""
    target, engine = await helpers.session()
    user_id = await _seed_user(target)
    with pytest.raises(ParamError):
        await _service(target).update_status(user_id, status="bad")
    await engine.dispose()


async def test_update_status_rejects_self_action() -> None:
    """启停：操作人自身不可停用（30009）。"""
    target, engine = await helpers.session()
    user_id = await _seed_user(target)
    current_user_id.set(user_id)
    try:
        with pytest.raises(UserProtectedError):
            await _service(target).update_status(user_id, status="disabled")
    finally:
        current_user_id.set(None)
    await engine.dispose()


async def test_update_user_sets_name_email_phone() -> None:
    """修改资料：`name` / `email` / `phone` 三者均提供时逐项落库。"""
    target, engine = await helpers.session()
    user_id = await _seed_user(target)
    updated = await _service(target).update_user(
        user_id, name="新名", email="new@example.com", phone="13800000000", version=1
    )
    assert updated.name == "新名"
    assert updated.email == "new@example.com"
    assert updated.phone == "13800000000"

    untouched = await _service(target).update_user(user_id, name=None, email=None, phone=None, version=2)
    assert untouched.name == "新名"
    assert untouched.email == "new@example.com"
    assert untouched.phone == "13800000000"
    await engine.dispose()


async def test_create_user_retries_generated_password() -> None:
    """随机初始密码：前次未过策略时继续生成，直到通过。"""
    target, engine = await helpers.session()
    policy = _Policy(valid_after=1)
    _user, generated = await _service(target, policy=policy).create_user(
        username="gen",
        name="Gen",
        password=None,
        pwd_reset_required=False,
        email=None,
        phone=None,
        status="enabled",
    )
    assert generated is not None
    assert policy.calls == 2
    await engine.dispose()


async def test_create_user_raises_when_generation_always_invalid() -> None:
    """随机初始密码：策略过严时快速失败（10002），不静默降级。"""
    target, engine = await helpers.session()
    policy = _Policy(valid_after=10**6)
    with pytest.raises(InternalError):
        await _service(target, policy=policy).create_user(
            username="gen2",
            name="Gen2",
            password=None,
            pwd_reset_required=False,
            email=None,
            phone=None,
            status="enabled",
        )
    assert policy.calls == _GENERATED_PASSWORD_ATTEMPTS
    await engine.dispose()
