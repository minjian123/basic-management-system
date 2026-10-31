"""系统参数管理域仓储（`sys_config`）：分页筛选 / 按键取 / 乐观锁更新 / 软删与恢复。

- 唯一性由**应用层判重**（`get_by_key`）保证：`(code, deleted_at)` 复合唯一在 `deleted_at IS NULL`
  时因 NULL 互不相等而不生效（SQLite / MySQL / PG 同语义，实测 2026-10-31）。
- 回收站视图（`include_deleted=True`）绕过软删过滤；普通查询只看未删行。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, func, or_, select, update

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["ConfigRepository"]


class ConfigRepository(BaseDbRepository[SysConfig]):
    """系统参数仓储（`sys_config`）。"""

    model = SysConfig
    sortable_fields = ConcurrentStableSet({"id", "config_key", "status", "updated_at"})

    async def get_by_key(self, config_key: str) -> SysConfig | None:
        """按参数键取未删除行（唯一性判重与依赖校验用）。

        Args:
            config_key: 参数键。

        Returns:
            SysConfig | None: 参数行；不存在 / 已删返回 None。
        """
        statement = self._select().where(self._column("config_key") == config_key)
        return (await self._session.execute(statement)).scalars().first()

    async def get_including_deleted(self, item_id: int) -> SysConfig | None:
        """按主键取行（含已软删，恢复与审计用）。

        Args:
            item_id: 参数主键。

        Returns:
            SysConfig | None: 参数行；不存在返回 None。
        """
        statement = self._select(include_soft_delete=False).where(self._column("id") == item_id)
        return (await self._session.execute(statement)).scalars().first()

    async def page_filtered(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        group: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[ConcurrentStableList[SysConfig], int]:
        """按关键字 / 分组前缀 / 状态分页查询（可按回收站视图含已删行）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 关键字（参数键 / 名称 / 备注模糊匹配）。
            group: 分组前缀（参数键首段，如 `password`）。
            status: 状态精确匹配。
            include_deleted: 是否包含已软删行（回收站视图）。

        Returns:
            tuple[ConcurrentStableList[SysConfig], int]: （当页记录, 总数）。
        """
        statement = self._select(include_soft_delete=not include_deleted)
        if keyword:
            pattern = f"%{keyword}%"
            statement = statement.where(
                or_(
                    self._column("config_key").like(pattern),
                    self._column("name").like(pattern),
                    self._column("remark").like(pattern),
                )
            )
        if group:
            statement = statement.where(self._column("config_key").like(f"{group}.%"))
        if status:
            statement = statement.where(self._column("status") == status)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("config_key").asc()).offset((page - 1) * size).limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def update_checked(self, item_id: int, *, expected_version: int, now: datetime, **values: object) -> bool:
        """带乐观锁的字段更新（`version` 不匹配即拒绝）。

        Args:
            item_id: 参数主键。
            expected_version: 期望版本（取详情里的当前值）。
            now: 当前时刻（UTC naive）。
            **values: 待更新字段。

        Returns:
            bool: 更新成功 True；版本不匹配 / 记录不存在 False。
        """
        payload = dict(values)
        payload["updated_at"] = now
        payload["version"] = expected_version + 1
        statement = (
            update(SysConfig)
            .where(
                SysConfig.id == item_id,
                SysConfig.version == expected_version,
                SysConfig.deleted_at.is_(None),
            )
            .values(**payload)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return result.rowcount == 1

    async def restore(self, item_id: int) -> bool:
        """恢复软删除行（清 `deleted_at`，乐观锁版本由 ORM 自增）。

        Args:
            item_id: 参数主键。

        Returns:
            bool: 恢复成功 True；记录不存在 / 未删除 False。
        """
        row = await self.get_including_deleted(item_id)
        if row is None:
            return False
        row.restore()
        await self._session.flush()
        return True
