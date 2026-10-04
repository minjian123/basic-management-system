"""用户↔租户可达关系服务（`sys_user_tenant` 幂等建 / 回收 / 读；11_01）。

- 事务边界：写操作经 `UnitOfWork.begin()` 单次事务（探测 + 写同事务）；
- 幂等：`ensure` 按唯一键命中即复用（`disabled` 则复活）；`revoke` / `revoke_all` 置 `disabled`（幂等）；
- 来源校验：`source` 须在 `TENANT_MEMBERSHIP_SOURCES` 内，否则参数错误（10001）；
- 读路径自愈判据（「自有租户行是否存在（含 disabled）」）由编排实现用
  `list_targets(include_disabled=True)` 判定，本服务只提供读写原语。
"""

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import ParamError, TenantNotFoundError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.tenant.base import TENANT_MEMBERSHIP_SELF_HEAL_SOURCE, TENANT_MEMBERSHIP_SOURCES
from bms_core.tenant.membership import TenantMembershipReport, TenantMembershipTarget
from bms_tenant.repositories.tenant_membership import (
    ACTIVE_MEMBERSHIP_STATUS,
    TenantMembershipRepository,
    to_target,
)

__all__ = ["DISABLED_MEMBERSHIP_STATUS", "SELF_HEAL_SOURCE", "TenantMembershipService"]

DISABLED_MEMBERSHIP_STATUS = "disabled"
"""关系回收状态（保留行、可再启）。"""

SELF_HEAL_SOURCE = TENANT_MEMBERSHIP_SELF_HEAL_SOURCE
"""读路径兜底自愈补建的来源取值（口径源自 `bms_core.tenant.base`）。"""


class TenantMembershipService(BaseFrameworkObject):
    """关系维护服务：建 / 复活 / 回收 / 读 / 对账巡检（仓储与事务边界由调用方注入）。"""

    def __init__(self, repository: TenantMembershipRepository, uow: UnitOfWork) -> None:
        """初始化。

        Args:
            repository: 关系仓储（平台服务库 `sys_user_tenant`）。
            uow: 工作单元（写事务边界）。
        """
        self._repository = repository
        self._uow = uow

    async def reconcile(self, *, tenant_id: int, user_ids: ConcurrentStableList[int]) -> TenantMembershipReport:
        """对账巡检：按给定用户清单比对关系表，输出缺行（无自有租户关系）/ 悬空行。

        调用方提供用户清单（如 org 服务的本租户用户清单）；巡检只读、不落库；缺行由读路径自愈
        或建号路径补齐，悬空行按用户停用 / 删除回收路径处理。

        Args:
            tenant_id: 归属租户主键。
            user_ids: 用户主键清单。

        Returns:
            TenantMembershipReport: 缺行 / 悬空行用户主键。
        """
        rows = await self._repository.list_tenant_rows(tenant_id=tenant_id)
        known: ConcurrentStableSet[int] = ConcurrentStableSet(user_ids)
        self_ids: ConcurrentStableSet[int] = ConcurrentStableSet()
        all_ids: ConcurrentStableSet[int] = ConcurrentStableSet()
        for row in rows:
            all_ids.add(int(row.user_id))
            if row.target_tenant_id == tenant_id and row.status == ACTIVE_MEMBERSHIP_STATUS:
                self_ids.add(int(row.user_id))
        return TenantMembershipReport(
            missing=ConcurrentStableList(item for item in user_ids if item not in self_ids),
            dangling=ConcurrentStableList(item for item in all_ids if item not in known),
        )

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取某用户可访问目标租户集合。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 目标集合。
        """
        return await self._repository.list_targets(
            tenant_id=tenant_id, user_id=user_id, include_disabled=include_disabled
        )

    async def ensure(
        self, *, tenant_id: int, user_id: int, target_tenant_id: int, source: str
    ) -> TenantMembershipTarget:
        """建立 / 复活关系（幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 写入来源（须在取值集合内；仅首次建立时落库）。

        Returns:
            TenantMembershipTarget: 建立 / 复活后的目标条目。

        Raises:
            ParamError: 来源取值非法（10001）。
            TenantNotFoundError: 目标租户不存在（404 / 80001）。
        """
        _validate_source(source)
        async with self._uow.begin():
            row = await self._repository.get(tenant_id=tenant_id, user_id=user_id, target_tenant_id=target_tenant_id)
            if row is None:
                row = await self._repository.create(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    target_tenant_id=target_tenant_id,
                    source=source,
                )
            elif row.status != ACTIVE_MEMBERSHIP_STATUS:
                row = await self._repository.set_status(row, ACTIVE_MEMBERSHIP_STATUS)
            tenant = await self._repository.target_tenant(target_tenant_id)
            if tenant is None:
                raise TenantNotFoundError(f"目标租户不存在：{target_tenant_id}")
            return to_target(row, tenant)

    async def revoke(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> None:
        """回收单个目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
        """
        async with self._uow.begin():
            row = await self._repository.get(tenant_id=tenant_id, user_id=user_id, target_tenant_id=target_tenant_id)
            if row is not None and row.status != DISABLED_MEMBERSHIP_STATUS:
                await self._repository.set_status(row, DISABLED_MEMBERSHIP_STATUS)

    async def revoke_all(self, *, tenant_id: int, user_id: int) -> None:
        """回收该用户全部目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
        """
        async with self._uow.begin():
            for row in await self._repository.list_rows(tenant_id=tenant_id, user_id=user_id):
                if row.status != DISABLED_MEMBERSHIP_STATUS:
                    await self._repository.set_status(row, DISABLED_MEMBERSHIP_STATUS)


def _validate_source(source: str) -> None:
    """校验写入来源取值。

    Args:
        source: 写入来源。

    Raises:
        ParamError: 取值不在 `TENANT_MEMBERSHIP_SOURCES` 内（10001）。
    """
    if source not in TENANT_MEMBERSHIP_SOURCES:
        allowed = " / ".join(TENANT_MEMBERSHIP_SOURCES)
        raise ParamError(f"未知的关系写入来源：{source!r}（允许 {allowed}）")
