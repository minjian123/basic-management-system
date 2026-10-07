"""平台服务 services 层：内部凭据服务（校验 / 重哈希 / 改密 / 登录态写回）。

供 identity 登录链路与账号治理（域三）经服务间契约调用；租户由服务 JWT `tenant` claim 经全局租户中间件解析，
本服务只操作当前租户库的 `sys_user`。写路径统一在单次事务内完成（读 + 写同一事务，避免自动开启事务与显式
事务冲突）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.password.base import BasePasswordPolicy
from bms_core.password.null import NullPasswordPolicy
from bms_core.security.base import BasePasswordHasher
from bms_core.services.base_service import BaseService
from bms_platform.models.user import LOCK_TYPE_FAIL_LIMIT, UNLOCK_MODE_AUTO, SysUser
from bms_platform.repositories.account_lock import AccountLockRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.credentials import (
    CredentialUserSummary,
    CredentialVerifyResult,
    LoginStateResult,
    UpdatePasswordResult,
)

FAIL_LIMIT_REASON = "登录失败达阈值自动锁定"
"""`fail_limit` 型锁定原因文案。"""

_LOGGER = get_logger("bms")


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class CredentialService(BaseService[SysUser]):
    """内部凭据服务：口令校验、参数升级重哈希、密码更新与登录态写回。"""

    def __init__(
        self,
        repository: UserRepository,
        hasher: BasePasswordHasher,
        uow: UnitOfWork,
        policy: BasePasswordPolicy | None = None,
        locks: AccountLockRepository | None = None,
    ) -> None:
        """初始化。

        Args:
            repository: 用户仓储。
            hasher: 口令哈希实现（PBKDF2）。
            uow: 工作单元（写事务边界）。
            policy: 密码策略（复杂度 / 有效期 / 历史；缺省 `NullPasswordPolicy` 恒定通过，向后兼容）。
            locks: 账号锁定记录仓储（登录态写回时写 `fail_limit` 锁；缺省 None 跳过，向后兼容）。
        """
        super().__init__(repository)
        self._uow = uow
        self._hasher = hasher
        self._policy = policy or NullPasswordPolicy()
        self._locks = locks

    async def verify(self, account: str, password: str) -> CredentialVerifyResult:
        """校验账号口令（命中且参数过期时同事务内重算回写；超有效期置强制改密标志）。

        Args:
            account: 登录账号。
            password: 口令明文。

        Returns:
            CredentialVerifyResult: 校验结果（`found` / `valid` / `locked` / `status` / `rehashed` /
            `pwd_reset_required` / `user`）。
        """
        async with self._uow.begin():
            user = await self._repo().get_by_username(account)
            if user is None:
                return CredentialVerifyResult(found=False, valid=False, locked=False, status="")
            locked = user.locked_until is not None and user.locked_until > _utc_now()
            valid = self._hasher.verify(password, user.password_hash)
            rehashed = False
            if valid and self._hasher.needs_rehash(user.password_hash):
                await self._repo().update(user.id, password_hash=self._hasher.hash(password))
                rehashed = True
            pwd_reset_required = user.pwd_reset_required
            if (
                valid
                and not pwd_reset_required
                and user.pwd_changed_at is not None
                and await self._policy.expired(user.pwd_changed_at)
            ):
                await self._repo().update(user.id, pwd_reset_required=True)
                pwd_reset_required = True
            return CredentialVerifyResult(
                found=True,
                valid=valid,
                locked=locked,
                status=user.status,
                rehashed=rehashed,
                pwd_reset_required=pwd_reset_required,
                user=CredentialUserSummary(
                    id=user.id,
                    username=user.username,
                    name=user.name,
                    locale=user.locale,
                    timezone=user.timezone,
                    pwd_changed_at=user.pwd_changed_at,
                ),
            )

    async def update_password(
        self, account: str, new_password: str, *, keep_history: int | None = None
    ) -> UpdatePasswordResult:
        """更新账号密码（先过密码策略：复杂度 + 历史重复；写新哈希 + 变更时间 + 历史 + 清强制改密标志）。

        Args:
            account: 登录账号。
            new_password: 新口令明文。
            keep_history: 保留历史密码条数；None 取策略 `history_count`。

        Returns:
            UpdatePasswordResult: 更新结果（`updated` / `reason` / `violations`）。
        """
        async with self._uow.begin():
            user = await self._repo().get_by_username(account)
            if user is None:
                return UpdatePasswordResult(updated=False, reason="not_found")
            violations = await self._policy.validate(new_password, username=user.username)
            if violations:
                return UpdatePasswordResult(
                    updated=False, reason="policy_violation", violations=ConcurrentStableList(violations)
                )
            history = parse_password_history(user.pwd_history)
            if await self._policy.reused(new_password, history=ConcurrentStableList([user.password_hash, *history])):
                return UpdatePasswordResult(updated=False, reason="history_reused")
            keep = keep_history if keep_history is not None else await self._policy.history_count()
            history.add(user.password_hash)
            history = history[-keep:] if keep > 0 else ConcurrentStableList()
            await self._repo().update(
                user.id,
                password_hash=self._hasher.hash(new_password),
                pwd_changed_at=_utc_now(),
                pwd_history=json.dumps(list(history), ensure_ascii=False),
                pwd_reset_required=False,
            )
            return UpdatePasswordResult(updated=True)

    async def apply_login_state(
        self,
        account: str,
        *,
        success: bool,
        failed_count: int | None = None,
        lock_seconds: int | None = None,
    ) -> LoginStateResult:
        """写回登录态：成功清零并记录登录时间；失败累计并在阈值命中时锁定。

        Args:
            account: 登录账号。
            success: 本次登录是否成功。
            failed_count: 失败计数（登录侧 Redis 计数结果；成功时忽略）。
            lock_seconds: 锁定时长（秒；>0 且失败时写 `locked_until` 并落 `fail_limit` 锁）。

        Returns:
            LoginStateResult: 当前失败计数 / 锁定到期 / 最近登录时间。
        """
        async with self._uow.begin():
            user = await self._repo().get_by_username(account)
            if user is None:
                return LoginStateResult(failed_count=0)
            now = _utc_now()
            if success:
                await self._repo().update(user.id, failed_count=0, locked_until=None, last_login_at=now)
                await self._close_expired_fail_limit(user.id, now)
                return LoginStateResult(failed_count=0, locked_until=None, last_login_at=now)
            count = user.failed_count if failed_count is None else failed_count
            locked_until = (
                now + timedelta(seconds=lock_seconds) if lock_seconds and lock_seconds > 0 else user.locked_until
            )
            await self._repo().update(user.id, failed_count=count, locked_until=locked_until)
            if lock_seconds and lock_seconds > 0:
                await self._write_fail_limit_lock(user.id, now=now, lock_seconds=lock_seconds)
            return LoginStateResult(failed_count=count, locked_until=locked_until, last_login_at=user.last_login_at)

    async def _write_fail_limit_lock(self, user_id: int, *, now: datetime, lock_seconds: int) -> None:
        """写 `fail_limit` 锁定记录（已有生效锁则幂等跳过）。

        Args:
            user_id: 用户主键。
            now: 当前时间（UTC naive）。
            lock_seconds: 锁定时长（秒）。
        """
        if self._locks is None:
            return
        if await self._locks.get_active_by_user(user_id, now=now) is not None:
            return
        lock = await self._locks.create(
            user_id=user_id,
            lock_type=LOCK_TYPE_FAIL_LIMIT,
            reason=FAIL_LIMIT_REASON,
            locked_at=now,
            expire_at=now + timedelta(seconds=lock_seconds),
        )
        _LOGGER.info("account.lock", lock_id=lock.id, user_id=user_id, lock_type=LOCK_TYPE_FAIL_LIMIT)

    async def _close_expired_fail_limit(self, user_id: int, now: datetime) -> None:
        """登录成功写回时关闭已到期的 `fail_limit` 锁记录（自动解锁留痕）。

        Args:
            user_id: 用户主键。
            now: 当前时间（UTC naive）。
        """
        if self._locks is None:
            return
        lock = await self._locks.get_open_by_user(user_id, lock_type=LOCK_TYPE_FAIL_LIMIT)
        if lock is None or lock.expire_at is None or lock.expire_at > now:
            return
        await self._locks.update(
            lock.id,
            unlock_at=lock.expire_at,
            unlock_by=None,
            unlock_mode=UNLOCK_MODE_AUTO,
        )
        _LOGGER.info("account.lock.auto", lock_id=lock.id, user_id=user_id)

    def _repo(self) -> UserRepository:
        """取用户仓储（泛型收窄）。

        Returns:
            UserRepository: 用户仓储。
        """
        repository = self._repository
        assert isinstance(repository, UserRepository)
        return repository


def parse_password_history(raw: str | None) -> ConcurrentStableList[str]:
    """解析历史密码 JSON（脏值按空列表）。

    Args:
        raw: `pwd_history` 原始值。

    Returns:
        ConcurrentStableList[str]: 历史哈希列表。
    """
    if not raw:
        return ConcurrentStableList()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ConcurrentStableList()
    if not isinstance(parsed, list):
        return ConcurrentStableList()
    return ConcurrentStableList(item for item in cast("list[object]", parsed) if isinstance(item, str))
