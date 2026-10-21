"""平台服务 repositories 层：自定义图标仓储（`sys_icon` / `sys_icon_i18n`）。

- 主表继承 `BaseDbRepository`（软删除过滤与统一 CRUD 由基类提供）；
- 多语言附表复用菜单域的同构辅助（软删除旧行再插新行）；
- 引用计数按菜单 `icon` 列（完整 icon key）统计，供删除前置检查。
"""

import sqlalchemy as sa
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_platform.models.menu import SysMenu
from bms_platform.models.system import SysIcon, SysIconI18n
from bms_platform.repositories.menu import _load_i18n_all, _replace_i18n  # pyright: ignore[reportPrivateUsage]


class IconRepository(BaseDbRepository[SysIcon]):
    """自定义图标仓储（租户库）：筛选清单、按图标键定位与多语言读写。"""

    model = SysIcon

    async def list_filtered(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> ConcurrentStableList[SysIcon]:
        """按分组 / 状态 / 关键字列示图标（主键升序）。

        Args:
            category: 图标分组（None 表示全部）。
            status: 状态（None 表示全部）。
            keyword: 关键字（匹配图标键 / 名称 / 标签；None 表示不过滤）。

        Returns:
            ConcurrentStableList[SysIcon]: 图标列表。
        """
        statement = self._select()
        if category:
            statement = statement.where(self._column("category") == category)
        if status:
            statement = statement.where(self._column("status") == status)
        if keyword:
            pattern = f"%{keyword}%"
            statement = statement.where(
                sa.or_(
                    self._column("code").like(pattern),
                    self._column("name").like(pattern),
                    self._column("tags").like(pattern),
                )
            )
        statement = statement.order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_code(self, code: str) -> SysIcon | None:
        """按图标键取活动行。

        Args:
            code: 图标键。

        Returns:
            SysIcon | None: 命中行；不存在返回 None。
        """
        statement = self._select().where(self._column("code") == code)
        return (await self._session.execute(statement)).scalars().first()

    async def get_deleted_by_code(self, code: str) -> SysIcon | None:
        """按图标键取软删除行（重建同键时恢复用）。

        Args:
            code: 图标键。

        Returns:
            SysIcon | None: 软删除行；不存在返回 None。
        """
        statement = select(SysIcon).where(SysIcon.code == code, SysIcon.deleted_at.is_not(None))
        return (await self._session.execute(statement)).scalars().first()

    async def list_i18n_all(
        self, icon_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """装载图标全部语言名称。

        Args:
            icon_ids: 图标 ID 集合。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 图标 ID → （locale → 文案）。
        """
        return await _load_i18n_all(self._session, SysIconI18n, "icon_id", icon_ids)

    async def replace_i18n(self, icon_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换图标多语言名称。

        Args:
            icon_id: 图标 ID。
            names: 语言标识 → 文案。
        """
        await _replace_i18n(self._session, SysIconI18n, "icon_id", icon_id, names)

    async def count_menu_refs(self, icon_key: str) -> int:
        """统计引用某完整 icon key 的菜单数（删除前置检查）。

        Args:
            icon_key: 完整 icon key（`custom:{图标键}`）。

        Returns:
            int: 引用菜单数。
        """
        statement = (
            select(sa.func.count())
            .select_from(SysMenu)
            .where(
                SysMenu.icon == icon_key,
                SysMenu.deleted_at.is_(None),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())
