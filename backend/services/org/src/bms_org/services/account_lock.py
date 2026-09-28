"""组织主数据服务 services 层：账号锁定服务（三型锁定写入 / 解锁 / 列表 / 详情）。

- `AccountLockService.scan_inactive`：按 `account.inactive_lock_days`（缺省 180）扫描 `sys_user`，
  命中即置 `locked_until` 远期哨兵并写 `sys_account_lock`（`inactive` 型，`expire_at=NULL`）；幂等。
- `lock_manual`：管理员手动锁定（`manual` 型，`expire_at=NULL`；已生效锁幂等返回既有）。
- `unlock`：手动解锁（清 `locked_until` / `failed_count`，回填 `unlock_at` / `unlock_by` / `unlock_mode`）。
- `list_locks` / `detail`：锁定记录列表与详情。
- 定时触发（Celery）归阶段八；`fail_limit` 型由 `CredentialService.apply_login_state` 同事务写入。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bms_core.config.base import BaseConfigSource
from bms_core.core.base import BaseObject
from bms_core.core.exceptions import AccountLockNotFoundError, NotFoundError
from bms_core.core.logging import get_logger
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.password.default import resolve_inactive_lock_days
from bms_core.schemas.pagination import BasePageQuery
from bms_org.models.account_lock import (
    LOCK_TYPE_INACTIVE,
    LOCK_TYPE_MANUAL,
    UNLOCK_MODE_MANUAL,
    SysAccountLock,
)
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.schemas.account_lock import InactiveScanResult

INACTIVE_LOCK_SENTINEL = datetime(9999, 12, 31, 0, 0, 0)
"""`inactive` / `manual` 型锁定复用 `sys_user.locked_until` 的远期哨兵（须手动解锁）。"""

MANUAL_LOCK_SENTINEL = INACTIVE_LOCK_SENTINEL
"""`manual` 型锁定远期哨兵（与 `inactive` 同值，语义别名）。"""

INACTIVE_LOCK_REASON = "长期未登录自动锁定"
"""`inactive` 型锁定原因文案。"""

MANUAL_LOCK_REASON = "管理员手动锁定"
"""`manual` 型锁定默认原因文案。"""

_LOGGER = get_logger("bms")


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class AccountLockService(BaseObject):
    """账号锁定服务：三型锁定写入、手动解锁与锁定记录查询。"""

    def __init__(
        self,
        users: UserRepository,
        locks: AccountLockRepository,
        uow: UnitOfWork,
        config: BaseConfigSource,
    ) -> None:
        """初始化。

        Args:
            users: 用户仓储。
            locks: 账号锁定记录仓储。
            uow: 工作单元（写事务边界）。
            config: 系统参数取数（读 `account.inactive_lock_days`）。
        """
        self._users = users
        self._locks = locks
        self._uow = uow
        self._config = config

    async def scan_inactive(self, *, now: datetime | None = None) -> InactiveScanResult:
        """扫描并锁定长期未登录账号（含从未登录账号；幂等）。

        Args:
            now: 当前时间（UTC naive）；None 取当前 UTC（便于测试注入）。

        Returns:
            InactiveScanResult: 扫描概要（`scanned` 候选数 / `locked` 本次锁定数）。
        """
        days = await resolve_inactive_lock_days(self._config)
        current = now or _utc_now()
        threshold = current - timedelta(days=days)
        async with self._uow.begin():
            candidates = await self._users.list_inactive(threshold, now=current)
            locked = 0
            for user in candidates:
                if await self._locks.get_active_by_user(user.id, now=current) is not None:
                    continue
                await self._users.update(user.id, locked_until=INACTIVE_LOCK_SENTINEL)
                await self._locks.create(
                    user_id=user.id,
                    lock_type=LOCK_TYPE_INACTIVE,
                    reason=INACTIVE_LOCK_REASON,
                    locked_at=current,
                )
                locked += 1
            return InactiveScanResult(scanned=len(candidates), locked=locked)

    async def lock_manual(
        self,
        user_id: int,
        *,
        reason: str = "",
        actor: int | None = None,
        now: datetime | None = None,
    ) -> SysAccountLock:
        """手动锁定账号（`manual` 型；已生效锁幂等返回既有）。

        Args:
            user_id: 用户主键。
            reason: 锁定原因（空取默认文案）。
            actor: 操作人主键（可为 None）。
            now: 当前时间（UTC naive）；None 取当前 UTC。

        Returns:
            SysAccountLock: 生效锁定记录（新建或既有）。

        Raises:
            NotFoundError: 目标用户不存在 / 已软删（10002 / 404）。
        """
        current = now or _utc_now()
        async with self._uow.begin():
            user = await self._users.get_by_id(user_id)
            if user is None:
                raise NotFoundError("用户不存在")
            existing = await self._locks.get_active_by_user(user_id, now=current)
            if existing is not None:
                return existing
            await self._users.update(user.id, locked_until=MANUAL_LOCK_SENTINEL)
            lock = await self._locks.create(
                user_id=user_id,
                lock_type=LOCK_TYPE_MANUAL,
                reason=reason or MANUAL_LOCK_REASON,
                locked_at=current,
                locked_by=actor,
            )
            _LOGGER.info("account.lock", lock_id=lock.id, user_id=user_id, lock_type=LOCK_TYPE_MANUAL, actor=actor)
            return lock

    async def unlock(self, lock_id: int, *, actor: int | None = None, now: datetime | None = None) -> SysAccountLock:
        """手动解锁（清账号锁定状态并回填解锁信息）。

        Args:
            lock_id: 锁定记录主键。
            actor: 操作人主键（可为 None）。
            now: 当前时间（UTC naive）；None 取当前 UTC。

        Returns:
            SysAccountLock: 解锁后的锁定记录。

        Raises:
            AccountLockNotFoundError: 锁定记录不存在或已解锁（30007，业务失败）。
        """
        current = now or _utc_now()
        async with self._uow.begin():
            lock = await self._locks.get(lock_id)
            if lock is None or lock.unlock_at is not None:
                raise AccountLockNotFoundError()
            user = await self._users.get_by_id(lock.user_id)
            if user is not None:
                await self._users.update(user.id, locked_until=None, failed_count=0)
            updated = await self._locks.update(
                lock.id,
                unlock_at=current,
                unlock_by=actor,
                unlock_mode=UNLOCK_MODE_MANUAL,
            )
            assert updated is not None  # 作用域内已取行，更新必命中
            _LOGGER.info("account.unlock", lock_id=lock.id, user_id=lock.user_id, actor=actor)
            return updated

    async def list_locks(
        self,
        query: BasePageQuery,
        *,
        user_id: int | None = None,
        lock_type: str | None = None,
        active: bool | None = None,
        locked_from: datetime | None = None,
        locked_to: datetime | None = None,
        now: datetime | None = None,
    ) -> tuple[list[SysAccountLock], int]:
        """锁定记录筛选分页查询。

        Args:
            query: 页码分页请求。
            user_id: 用户主键（精确）。
            lock_type: 锁定类型（精确）。
            active: 是否生效中（True / False / None）。
            locked_from: 锁定时间下界（UTC，闭区间）。
            locked_to: 锁定时间上界（UTC，闭区间）。
            now: 当前时间（UTC naive；活跃判定用）。

        Returns:
            tuple[list[SysAccountLock], int]: (当前页记录, 总数)。
        """
        items = await self._locks.list_filtered(
            query,
            user_id=user_id,
            lock_type=lock_type,
            active=active,
            locked_from=locked_from,
            locked_to=locked_to,
            now=now,
        )
        total = await self._locks.count_filtered(
            user_id=user_id,
            lock_type=lock_type,
            active=active,
            locked_from=locked_from,
            locked_to=locked_to,
            now=now,
        )
        return items, total

    async def detail(self, lock_id: int) -> SysAccountLock:
        """锁定记录详情（含已解锁）。

        Args:
            lock_id: 锁定记录主键。

        Returns:
            SysAccountLock: 锁定记录。

        Raises:
            AccountLockNotFoundError: 锁定记录不存在（30007，业务失败）。
        """
        lock = await self._locks.get(lock_id)
        if lock is None:
            raise AccountLockNotFoundError()
        return lock
