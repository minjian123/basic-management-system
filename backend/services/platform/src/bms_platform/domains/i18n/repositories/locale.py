"""语言清单仓储（`sys_i18n_locale`）：分页 / 按键取 / 默认语言 / 乐观锁更新。

- 唯一性由**应用层判重**（`get_by_code`，大小写不敏感）保证：`(code, deleted_at)` 复合唯一在
  `deleted_at IS NULL` 时不生效（NULL 互不相等，三库同语义）。
- **默认语言唯一性**：切默认时先 `clear_default(exclude_id)` 再置本条，二者同一事务。
- 回收站视图（`include_deleted=True`）绕过软删过滤；普通查询只看未删行。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, func, or_, select, update

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.i18n import SysI18nLocale, SysI18nMessage
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["LocaleRepository"]


class LocaleRepository(BaseDbRepository[SysI18nLocale]):
    """语言清单仓储（`sys_i18n_locale`）。"""

    model = SysI18nLocale
    sortable_fields = ConcurrentStableSet({"id", "code", "sort", "status", "updated_at"})

    async def page_filtered(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[ConcurrentStableList[SysI18nLocale], int]:
        """按关键字 / 状态分页查询（可按回收站视图含已删行）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 关键字（语言标识 / 名称模糊匹配）。
            status: 状态精确匹配。
            include_deleted: 是否包含已软删行（回收站视图）。

        Returns:
            tuple[ConcurrentStableList[SysI18nLocale], int]: （当页记录, 总数）。
        """
        statement = self._select(include_soft_delete=not include_deleted)
        if keyword:
            pattern = f"%{keyword}%"
            statement = statement.where(or_(self._column("code").like(pattern), self._column("name").like(pattern)))
        if status:
            statement = statement.where(self._column("status") == status)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("sort").asc(), self._column("code").asc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def get_by_code(self, code: str) -> SysI18nLocale | None:
        """按语言标识取未删除行（判重与详情用；大小写不敏感）。

        Args:
            code: 语言标识。

        Returns:
            SysI18nLocale | None: 语言行；不存在 / 已删返回 None。
        """
        statement = self._select().where(func.lower(self._column("code")) == code.strip().lower())
        return (await self._session.execute(statement)).scalars().first()

    async def count_enabled(self) -> int:
        """统计启用语言数量（至少保留一种启用的判据）。

        Returns:
            int: 启用语言行数。
        """
        statement = select(func.count()).select_from(
            self._select().where(self._column("status") == "enabled").subquery()
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def has_messages(self, code: str) -> bool:
        """判定某语言是否仍存在语言包行（删除保护）。

        Args:
            code: 语言标识（调用方已归一）。

        Returns:
            bool: 存在语言包行 True。
        """
        statement = (
            select(func.count())
            .select_from(SysI18nMessage)
            .where(
                func.lower(SysI18nMessage.locale) == code.strip().lower(),
                SysI18nMessage.deleted_at.is_(None),
            )
        )
        return int((await self._session.execute(statement)).scalar_one()) > 0

    async def update_checked(self, item_id: int, *, expected_version: int, now: datetime, **values: object) -> bool:
        """带乐观锁的字段更新（`version` 不匹配即拒绝）。

        Args:
            item_id: 语言主键。
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
            update(SysI18nLocale)
            .where(
                SysI18nLocale.id == item_id,
                SysI18nLocale.version == expected_version,
                SysI18nLocale.deleted_at.is_(None),
            )
            .values(**payload)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return result.rowcount == 1

    async def clear_default(self, *, exclude_id: int | None, now: datetime) -> None:
        """清除其它行的默认语言标记（切默认时与置位同一事务）。

        Args:
            exclude_id: 保持不受影响的主键（None 表示清全部）。
            now: 当前时刻（UTC naive）。
        """
        statement = update(SysI18nLocale).where(SysI18nLocale.is_default.is_(True))
        if exclude_id is not None:
            statement = statement.where(SysI18nLocale.id != exclude_id)
        await self._session.execute(statement.values(is_default=False, updated_at=now))
