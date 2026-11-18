"""工作台卡片仓储：卡片注册表 + 卡片名多语言附表（`sys_dashboard_card` / `_i18n`）。

多语言读写统一走 `bms_core/repositories/i18n.py` 的统一助手（《数据规范》§5：三级回退、
主表默认文案列为派生快照、同生命周期连带软删），**不在本域自建一套多语言读写**。
"""

from __future__ import annotations

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
)
from bms_core.models.platform.dashboard import SysDashboardCard, SysDashboardCardI18n
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.repositories.i18n import load_i18n_texts, replace_i18n_texts, soft_delete_i18n

__all__ = ["DashboardCardI18nRepository", "DashboardCardRepository"]


class DashboardCardRepository(BaseDbRepository[SysDashboardCard]):
    """卡片注册表仓储（软删除由基座 `_select()` 统一过滤）。"""

    model = SysDashboardCard

    async def list_cards(
        self, *, card_type: str | None = None, enabled_only: bool = False
    ) -> ConcurrentStableList[SysDashboardCard]:
        """取卡片（按 `sort` 升序、同序按 `code` 升序）。

        Args:
            card_type: 卡片类型筛选（None 不筛选）。
            enabled_only: 仅取启用卡片。

        Returns:
            ConcurrentStableList[SysDashboardCard]: 卡片清单（插入序即排布序）。
        """
        statement = self._select()
        if card_type is not None:
            statement = statement.where(SysDashboardCard.card_type == card_type)
        if enabled_only:
            statement = statement.where(SysDashboardCard.status == "enabled")
        statement = statement.order_by(SysDashboardCard.sort, SysDashboardCard.code)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_code(self, code: str) -> SysDashboardCard | None:
        """按卡片标识取活行（含已停用；不存在返回 None）。

        Args:
            code: 卡片标识。

        Returns:
            SysDashboardCard | None: 卡片行。
        """
        statement = self._select().where(SysDashboardCard.code == code)
        return (await self._session.execute(statement)).scalars().first()


class DashboardCardI18nRepository(BaseDbRepository[SysDashboardCardI18n]):
    """卡片名多语言附表仓储（薄壳：真实读写委托基座助手）。"""

    model = SysDashboardCardI18n

    async def load_names(
        self, card_ids: ConcurrentStableList[int], *, locales: ConcurrentStableList[str]
    ) -> ConcurrentStableDict[int, str]:
        """按语言优先级批量装载卡片名（三级回退由助手实现）。

        Args:
            card_ids: 卡片主键清单。
            locales: 语言优先级序（从高到低）。

        Returns:
            ConcurrentStableDict[int, str]: 卡片主键 → 优先级最高的非空文案。
        """
        buckets = await load_i18n_texts(self._session, SysDashboardCardI18n, "card_id", card_ids, locales=locales)
        names: ConcurrentStableDict[int, str] = ConcurrentStableDict()
        for card_id, columns in buckets.items():
            text = columns.get("name")
            if text is not None:  # pragma: no branch - i18n 助手只回非空文本（缺列不出现在结果里）
                names.set(card_id, text)
        return names

    async def load_all_names(
        self, card_ids: ConcurrentStableList[int], *, locales: ConcurrentStableList[str]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """按卡片批量装载全部语言的文案（管理面回显用）。

        Args:
            card_ids: 卡片主键清单。
            locales: 语言清单（缺省语言在前）。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 卡片主键 → （语言 → 文案）。
        """
        if not card_ids:
            return ConcurrentStableDict()
        statement = (
            self._select()
            .where(SysDashboardCardI18n.card_id.in_(list(card_ids)))
            .order_by(SysDashboardCardI18n.card_id, SysDashboardCardI18n.locale)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        result: ConcurrentStableDict[int, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for row in rows:
            bucket: ConcurrentStableDict[str, str] | None = result.get(int(row.card_id))
            if bucket is None:
                bucket = ConcurrentStableDict()
                result.set(int(row.card_id), bucket)
            bucket.set(row.locale, row.name)
        return result

    async def replace_names(self, card_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整份覆盖某卡片的多语言名（主表默认列由调用方派生写入）。

        Args:
            card_id: 卡片主键。
            names: 语言 → 文案。
        """
        texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for locale, name in names.items():
            column_map: ConcurrentStableDict[str, str] = ConcurrentStableDict()
            column_map.set("name", name)
            texts.set(locale, column_map)
        await replace_i18n_texts(self._session, SysDashboardCardI18n, "card_id", card_id, texts)

    async def soft_delete_names(self, card_id: int) -> None:
        """软删除某卡片的全部多语言文案（卡片删除时连带清理）。

        Args:
            card_id: 卡片主键。
        """
        await soft_delete_i18n(self._session, SysDashboardCardI18n, "card_id", card_id)
