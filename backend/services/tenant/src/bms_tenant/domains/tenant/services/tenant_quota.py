"""租户配额服务（读写 / 校验 / 占用 / 释放；任务 `04_01`）。

- 平台超管配置限额；用量由调用方经内部契约实时增量（用户数 / 存储字节）。
- 无配额行 = 不限制；超限统一 `82005`（`data` 带维度 / 限额 / 已用量）。
"""

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError, TenantQuotaExceededError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.tenant.tenant_quota import (
    QUOTA_KEY_OPEN_CALLS,
    QUOTA_KEY_STORAGE_BYTES,
    QUOTA_KEY_USER_COUNT,
    QUOTA_KEYS,
)
from bms_tenant.domains.tenant.repositories.tenant_quota import TenantQuotaRepository
from bms_tenant.domains.tenant.schemas.tenant_admin import QuotaResult, TenantQuotaItem, TenantQuotaUpdateItem

__all__ = ["TenantQuotaService", "quota_defaults"]


def quota_defaults(settings: Settings) -> ConcurrentStableDict[str, int]:
    """取配额默认值（`[tenant_quota]`）。

    Args:
        settings: 应用配置。

    Returns:
        ConcurrentStableDict[str, int]: 维度 → 默认限额。
    """
    section = settings.tenant_quota
    return ConcurrentStableDict(
        {
            QUOTA_KEY_USER_COUNT: section.default_user_count,
            QUOTA_KEY_STORAGE_BYTES: section.default_storage_bytes,
            QUOTA_KEY_OPEN_CALLS: section.default_open_calls,
        }
    )


class TenantQuotaService(BaseFrameworkObject):
    """租户配额服务（会话绑定；事务边界由调用方负责）。"""

    def __init__(self, session: DbSession, settings: Settings) -> None:
        """初始化。

        Args:
            session: 平台库会话。
            settings: 应用配置（默认值来源）。
        """
        self._repo = TenantQuotaRepository(session)
        self._settings = settings

    async def list_items(self, tenant_id: int) -> ConcurrentStableList[TenantQuotaItem]:
        """取租户配额与用量（按维度排序）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableList[TenantQuotaItem]: 配额项。
        """
        return ConcurrentStableList(
            TenantQuotaItem(quota_key=row.quota_key, limit_value=int(row.limit_value), used_value=int(row.used_value))
            for row in await self._repo.list_by_tenant(tenant_id)
        )

    async def update_limits(
        self, tenant_id: int, items: ConcurrentStableList[TenantQuotaUpdateItem]
    ) -> ConcurrentStableList[TenantQuotaItem]:
        """配置配额限额（不存在则新建；未列出的维度保持原值）。

        Args:
            tenant_id: 租户主键。
            items: 配额项清单。

        Returns:
            ConcurrentStableList[TenantQuotaItem]: 更新后的配额与用量。

        Raises:
            ParamError: 维度非法（10001）。
        """
        for item in items:
            if item.quota_key not in QUOTA_KEYS:
                raise ParamError(f"未知配额维度：{item.quota_key}")
            row = await self._repo.get(tenant_id, item.quota_key)
            if row is None:
                await self._repo.ensure_default(
                    tenant_id=tenant_id, quota_key=item.quota_key, limit_value=item.limit_value
                )
            else:
                await self._repo.update_limit(row, item.limit_value)
        return await self.list_items(tenant_id)

    async def seed_defaults(self, tenant_id: int) -> None:
        """按配置播种默认配额（幂等；已存在不改限额）。

        Args:
            tenant_id: 租户主键。
        """
        for quota_key, limit_value in quota_defaults(self._settings).items():
            await self._repo.ensure_default(tenant_id=tenant_id, quota_key=quota_key, limit_value=limit_value)

    async def check(self, tenant_id: int, quota_key: str, amount: int) -> QuotaResult:
        """校验配额是否足够（不写）。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。
            amount: 预占数量。

        Returns:
            QuotaResult: 校验结果（无配额行视为放行）。

        Raises:
            TenantQuotaExceededError: 超限（82005 / 409）。
        """
        row = await self._repo.get(tenant_id, quota_key)
        if row is None:
            return QuotaResult(allowed=True, used_value=0, limit_value=None)
        if int(row.used_value) + amount > int(row.limit_value):
            raise TenantQuotaExceededError(
                f"租户配额超限：{quota_key}",
                data={"quota_key": quota_key, "limit": int(row.limit_value), "used": int(row.used_value)},
            )
        return QuotaResult(allowed=True, used_value=int(row.used_value), limit_value=int(row.limit_value))

    async def consume(self, tenant_id: int, quota_key: str, amount: int) -> QuotaResult:
        """原子占用配额。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。
            amount: 占用数量。

        Returns:
            QuotaResult: 占用结果（无配额行视为放行、不计数）。

        Raises:
            TenantQuotaExceededError: 超限（82005 / 409）。
        """
        row = await self._repo.get(tenant_id, quota_key)
        if row is None:
            return QuotaResult(allowed=True, used_value=0, limit_value=None)
        if not await self._repo.consume(tenant_id=tenant_id, quota_key=quota_key, amount=amount):
            current = await self._repo.get(tenant_id, quota_key)
            limit_value = int(current.limit_value) if current is not None else int(row.limit_value)
            used_value = int(current.used_value) if current is not None else int(row.used_value)
            raise TenantQuotaExceededError(
                f"租户配额超限：{quota_key}",
                data={"quota_key": quota_key, "limit": limit_value, "used": used_value},
            )
        updated = await self._repo.get(tenant_id, quota_key)
        return QuotaResult(
            allowed=True,
            used_value=int(updated.used_value) if updated is not None else 0,
            limit_value=int(updated.limit_value) if updated is not None else None,
        )

    async def release(self, tenant_id: int, quota_key: str, amount: int) -> QuotaResult:
        """释放配额用量（下限 0）。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。
            amount: 释放数量。

        Returns:
            QuotaResult: 释放结果（无配额行视为放行、不计数）。
        """
        row = await self._repo.get(tenant_id, quota_key)
        if row is None:
            return QuotaResult(allowed=True, used_value=0, limit_value=None)
        used_value = await self._repo.release(tenant_id=tenant_id, quota_key=quota_key, amount=amount)
        return QuotaResult(allowed=True, used_value=used_value, limit_value=int(row.limit_value))
