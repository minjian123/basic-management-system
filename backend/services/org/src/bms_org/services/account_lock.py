"""组织主数据服务 services 层：账号锁定服务（不活跃扫描写锁；扩展归 03_07）。

- `AccountLockService.scan_inactive`：按 `account.inactive_lock_days`（缺省 180）扫描 `sys_user`，
  命中即置 `locked_until` 远期哨兵并写 `sys_account_lock`（`inactive` 型）；幂等（重复扫描不新增）。
- 定时触发（Celery）归阶段八；本任务提供**服务方法 + 手动触发端点**。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bms_core.config.base import BaseConfigSource
from bms_core.core.base import BaseObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.password.default import resolve_inactive_lock_days
from bms_org.models.account_lock import LOCK_TYPE_INACTIVE
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.schemas.account_lock import InactiveScanResult

INACTIVE_LOCK_SENTINEL = datetime(9999, 12, 31, 0, 0, 0)
"""`inactive` 型锁定复用 `sys_user.locked_until` 的远期哨兵（登录即被既有锁定链拒绝，手动解锁清空）。"""

INACTIVE_LOCK_REASON = "长期未登录自动锁定"
"""`inactive` 型锁定原因文案。"""


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class AccountLockService(BaseObject):
    """账号锁定服务：不活跃账号扫描与锁定记录写入。"""

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
                if await self._locks.get_active_by_user(user.id) is not None:
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
