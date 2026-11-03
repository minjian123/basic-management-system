"""语言包仓储（`sys_i18n_message`）：分页筛选 / 按 key+locale 取 / 乐观锁更新 / 软删。

- 唯一性由**应用层判重**（`get_by_key_locale`）保证：`(code, locale, deleted_at)` 复合唯一在
  `deleted_at IS NULL` 时不生效（NULL 互不相等，三库同语义）。
- 「缺失」判定：`value` 去空白后为空（`func.trim(value) = ''`），与前端派生口径一致。
- 按语言全量加载（运行时下发）走 `list_by_locale`，命中 `idx_sys_i18n_message_locale`。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, func, select, update

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.i18n import SysI18nMessage
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["MessageRepository"]


class MessageRepository(BaseDbRepository[SysI18nMessage]):
    """语言包仓储（`sys_i18n_message`）。"""

    model = SysI18nMessage
    sortable_fields = ConcurrentStableSet({"id", "msg_key", "locale", "updated_at"})

    async def page_filtered(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        module: str | None = None,
        locale: str | None = None,
        missing_only: bool = False,
        include_deleted: bool = False,
    ) -> tuple[ConcurrentStableList[SysI18nMessage], int]:
        """按关键字 / 模块前缀 / 语言 / 缺失分页查询。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 关键字（文案 key 模糊匹配）。
            module: 模块前缀（key 首段，如 `common`）。
            locale: 语言精确匹配（大小写不敏感）。
            missing_only: 只看缺失（`value` 去空白为空）。
            include_deleted: 是否包含已软删行（回收站视图）。

        Returns:
            tuple[ConcurrentStableList[SysI18nMessage], int]: （当页记录, 总数）。
        """
        statement = self._select(include_soft_delete=not include_deleted)
        if keyword:
            statement = statement.where(self._column("msg_key").like(f"%{keyword}%"))
        if module:
            statement = statement.where(self._column("msg_key").like(f"{module}.%"))
        if locale:
            statement = statement.where(func.lower(self._column("locale")) == locale.strip().lower())
        if missing_only:
            statement = statement.where(func.trim(self._column("value")) == "")
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("msg_key").asc(), self._column("locale").asc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def get_by_key_locale(self, msg_key: str, locale: str) -> SysI18nMessage | None:
        """按 `(key, locale)` 取未删除行（判重与幂等 upsert 用）。

        Args:
            msg_key: 文案 key。
            locale: 语言标识（大小写不敏感）。

        Returns:
            SysI18nMessage | None: 文案行；不存在 / 已删返回 None。
        """
        statement = self._select().where(
            self._column("msg_key") == msg_key,
            func.lower(self._column("locale")) == locale.strip().lower(),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def get_including_deleted(self, item_id: int) -> SysI18nMessage | None:
        """按主键取行（含已软删，审计用）。

        Args:
            item_id: 文案主键。

        Returns:
            SysI18nMessage | None: 文案行；不存在返回 None。
        """
        statement = self._select(include_soft_delete=False).where(self._column("id") == item_id)
        return (await self._session.execute(statement)).scalars().first()

    async def update_checked(self, item_id: int, *, expected_version: int, now: datetime, **values: object) -> bool:
        """带乐观锁的字段更新（`version` 不匹配即拒绝）。

        Args:
            item_id: 文案主键。
            expected_version: 期望版本（取列表里的当前值）。
            now: 当前时刻（UTC naive）。
            **values: 待更新字段。

        Returns:
            bool: 更新成功 True；版本不匹配 / 记录不存在 False。
        """
        payload = dict(values)
        payload["updated_at"] = now
        payload["version"] = expected_version + 1
        statement = (
            update(SysI18nMessage)
            .where(
                SysI18nMessage.id == item_id,
                SysI18nMessage.version == expected_version,
                SysI18nMessage.deleted_at.is_(None),
            )
            .values(**payload)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return result.rowcount == 1
