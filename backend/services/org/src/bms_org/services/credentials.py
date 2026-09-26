"""组织主数据服务 services 层：内部凭据服务（校验 / 重哈希 / 改密 / 登录态写回）。

供 identity 登录链路与账号治理（域三）经服务间契约调用；租户由服务 JWT `tenant` claim 经全局租户中间件解析，
本服务只操作当前租户库的 `sys_user`。写路径统一在单次事务内完成（读 + 写同一事务，避免自动开启事务与显式
事务冲突）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.db.unit_of_work import UnitOfWork
from bms_core.security.base import BasePasswordHasher
from bms_core.services.base_service import BaseService
from bms_org.models.user import SysUser
from bms_org.repositories.user import UserRepository
from bms_org.schemas.credentials import (
    CredentialUserSummary,
    CredentialVerifyResult,
    LoginStateResult,
    UpdatePasswordResult,
)


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class CredentialService(BaseService[SysUser]):
    """内部凭据服务：口令校验、参数升级重哈希、密码更新与登录态写回。"""

    def __init__(self, repository: UserRepository, hasher: BasePasswordHasher, uow: UnitOfWork) -> None:
        """初始化。

        Args:
            repository: 用户仓储。
            hasher: 口令哈希实现（PBKDF2）。
            uow: 工作单元（写事务边界）。
        """
        super().__init__(repository)
        self._uow = uow
        self._hasher = hasher

    async def verify(self, account: str, password: str) -> CredentialVerifyResult:
        """校验账号口令（命中且参数过期时同事务内重算回写）。

        Args:
            account: 登录账号。
            password: 口令明文。

        Returns:
            CredentialVerifyResult: 校验结果（`found` / `valid` / `locked` / `status` / `rehashed` / `user`）。
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
            return CredentialVerifyResult(
                found=True,
                valid=valid,
                locked=locked,
                status=user.status,
                rehashed=rehashed,
                user=CredentialUserSummary(
                    id=user.id,
                    username=user.username,
                    name=user.name,
                    locale=user.locale,
                    timezone=user.timezone,
                    pwd_changed_at=user.pwd_changed_at,
                ),
            )

    async def update_password(self, account: str, new_password: str, *, keep_history: int = 5) -> UpdatePasswordResult:
        """更新账号密码（新哈希 + 变更时间 + 历史密码保留近 N 条）。

        Args:
            account: 登录账号。
            new_password: 新口令明文。
            keep_history: 保留历史密码条数。

        Returns:
            UpdatePasswordResult: 更新结果（账号不存在为 False）。
        """
        async with self._uow.begin():
            user = await self._repo().get_by_username(account)
            if user is None:
                return UpdatePasswordResult(updated=False)
            history = parse_password_history(user.pwd_history)
            history.append(user.password_hash)
            history = history[-keep_history:] if keep_history > 0 else []
            await self._repo().update(
                user.id,
                password_hash=self._hasher.hash(new_password),
                pwd_changed_at=_utc_now(),
                pwd_history=json.dumps(history, ensure_ascii=False),
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
            lock_seconds: 锁定时长（秒；>0 且失败时写 `locked_until`）。

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
                return LoginStateResult(failed_count=0, locked_until=None, last_login_at=now)
            count = user.failed_count if failed_count is None else failed_count
            locked_until = (
                now + timedelta(seconds=lock_seconds) if lock_seconds and lock_seconds > 0 else user.locked_until
            )
            await self._repo().update(user.id, failed_count=count, locked_until=locked_until)
            return LoginStateResult(failed_count=count, locked_until=locked_until, last_login_at=user.last_login_at)

    def _repo(self) -> UserRepository:
        """取用户仓储（泛型收窄）。

        Returns:
            UserRepository: 用户仓储。
        """
        repository = self._repository
        assert isinstance(repository, UserRepository)
        return repository


def parse_password_history(raw: str | None) -> list[str]:
    """解析历史密码 JSON（脏值按空列表）。

    Args:
        raw: `pwd_history` 原始值。

    Returns:
        list[str]: 历史哈希列表。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in cast("list[object]", parsed) if isinstance(item, str)]
