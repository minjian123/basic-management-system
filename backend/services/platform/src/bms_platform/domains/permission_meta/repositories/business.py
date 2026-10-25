"""权限元数据仓储：业务码 / 动作码 / 权限码（`sys_business(+_i18n)` / `sys_action(+_i18n)` / `sys_permission`）。

- 归属业务域 `permission_meta`；三个仓储共享「多语言附表整表替换」口径（助手在基座
  `bms_core/repositories/i18n.py`）；
- 主表仓储继承 `BaseDbRepository`（软删除过滤与统一 CRUD 由基类提供）；
- 查询与业务规则归 `services/permission_meta.py`，本层只管数据访问。
"""

from typing import cast

import sqlalchemy as sa
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.platform.permission_meta import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysPermission,
)
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.repositories.i18n import load_i18n, load_i18n_all
from bms_core.repositories.i18n import replace_i18n as replace_i18n_rows


class BusinessRepository(BaseDbRepository[SysBusiness]):
    """业务权限码仓储（`sys_business`）。"""

    model = SysBusiness

    async def list_all(self) -> ConcurrentStableList[SysBusiness]:
        """列示全部业务码（主键升序）。

        Returns:
            ConcurrentStableList[SysBusiness]: 业务码列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_i18n(self, business_ids: ConcurrentStableList[int], locale: str) -> ConcurrentStableDict[int, str]:
        """装载业务码多语言文案。

        Args:
            business_ids: 业务码 ID 集合。
            locale: 语言标识。

        Returns:
            ConcurrentStableDict[int, str]: 业务码 ID → 文案。
        """
        return await load_i18n(self._session, SysBusinessI18n, "business_id", business_ids, locale)

    async def list_i18n_all(
        self, business_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """装载业务码**全部语言**文案（维护视图出参：语言清单驱动界面，出参须完整）。

        Args:
            business_ids: 业务码 ID 集合。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 业务码 ID → （locale → 文案）。
        """
        return await load_i18n_all(self._session, SysBusinessI18n, "business_id", business_ids)

    async def get_by_code(self, code: str) -> SysBusiness | None:
        """按业务码取活动行。

        Args:
            code: 业务码。

        Returns:
            SysBusiness | None: 命中行；不存在返回 None。
        """
        statement = self._select().where(self._column("code") == code)
        return (await self._session.execute(statement)).scalars().first()

    async def get_deleted_by_code(self, code: str) -> SysBusiness | None:
        """按业务码取**软删除行**（重建同码时恢复用）。

        Args:
            code: 业务码。

        Returns:
            SysBusiness | None: 软删除行；不存在返回 None。
        """
        statement = select(SysBusiness).where(SysBusiness.code == code, SysBusiness.deleted_at.is_not(None))
        return (await self._session.execute(statement)).scalars().first()

    async def replace_i18n(self, business_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换业务码多语言文案。

        Args:
            business_id: 业务码 ID。
            names: 语言标识 → 文案。
        """
        await replace_i18n_rows(self._session, SysBusinessI18n, "business_id", business_id, names)


class ActionRepository(BaseDbRepository[SysAction]):
    """动作码字典仓储（`sys_action`）：全局动词，按主键列示与多语言装载。"""

    model = SysAction

    async def list_all(self) -> ConcurrentStableList[SysAction]:
        """列示全部动作码（全局字典；主键升序）。

        Returns:
            ConcurrentStableList[SysAction]: 动作码列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_i18n(self, action_ids: ConcurrentStableList[int], locale: str) -> ConcurrentStableDict[int, str]:
        """装载动作码多语言文案。

        Args:
            action_ids: 动作码 ID 集合。
            locale: 语言标识。

        Returns:
            ConcurrentStableDict[int, str]: 动作码 ID → 文案。
        """
        return await load_i18n(self._session, SysActionI18n, "action_id", action_ids, locale)

    async def list_i18n_all(
        self, action_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """装载动作码**全部语言**文案（维护视图出参）。

        Args:
            action_ids: 动作码 ID 集合。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 动作码 ID → （locale → 文案）。
        """
        return await load_i18n_all(self._session, SysActionI18n, "action_id", action_ids)

    async def get_by_code(self, code: str) -> SysAction | None:
        """按动作码取活动行。

        Args:
            code: 动作码。

        Returns:
            SysAction | None: 命中行；不存在返回 None。
        """
        statement = self._select().where(self._column("code") == code)
        return (await self._session.execute(statement)).scalars().first()

    async def get_deleted_by_code(self, code: str) -> SysAction | None:
        """按动作码取**软删除行**（重建同码时恢复用）。

        Args:
            code: 动作码。

        Returns:
            SysAction | None: 软删除行；不存在返回 None。
        """
        statement = select(SysAction).where(SysAction.code == code, SysAction.deleted_at.is_not(None))
        return (await self._session.execute(statement)).scalars().first()

    async def replace_i18n(self, action_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换动作码多语言文案。

        Args:
            action_id: 动作码 ID。
            names: 语言标识 → 文案。
        """
        await replace_i18n_rows(self._session, SysActionI18n, "action_id", action_id, names)


class PermissionRepository(BaseDbRepository[SysPermission]):
    """权限码仓储（`sys_permission`）：业务码 × 动作码组合，受控可授项。"""

    model = SysPermission

    async def list_all(self) -> ConcurrentStableList[SysPermission]:
        """列示全部权限码（主键升序）。

        Returns:
            ConcurrentStableList[SysPermission]: 权限码列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_by_business(self, business_id: int | None = None) -> ConcurrentStableList[SysPermission]:
        """按业务码列示权限码（可空 = 全部；主键升序）。

        Args:
            business_id: 业务码 ID；None 表示全部。

        Returns:
            ConcurrentStableList[SysPermission]: 权限码列表（插入序）。
        """
        statement = self._select()
        if business_id is not None:
            statement = statement.where(self._column("business_id") == business_id)
        statement = statement.order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_pair(self, business_id: int, action_id: int) -> SysPermission | None:
        """按业务码 × 动作码取活动行。

        Args:
            business_id: 业务码 ID。
            action_id: 动作码 ID。

        Returns:
            SysPermission | None: 命中行；不存在返回 None。
        """
        statement = self._select().where(
            self._column("business_id") == business_id,
            self._column("action_id") == action_id,
        )
        return (await self._session.execute(statement)).scalars().first()

    async def get_deleted_by_pair(self, business_id: int, action_id: int) -> SysPermission | None:
        """按组合取**软删除行**（重建同组合时恢复用）。

        Args:
            business_id: 业务码 ID。
            action_id: 动作码 ID。

        Returns:
            SysPermission | None: 软删除行；不存在返回 None。
        """
        statement = select(SysPermission).where(
            SysPermission.business_id == business_id,
            SysPermission.action_id == action_id,
            SysPermission.deleted_at.is_not(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def count_by_business(self, business_id: int) -> int:
        """统计某业务码下的权限码数量（含停用）。

        Args:
            business_id: 业务码 ID。

        Returns:
            int: 权限码数量。
        """
        statement = (
            select(sa.func.count())
            .select_from(SysPermission)
            .where(
                SysPermission.business_id == business_id,
                SysPermission.deleted_at.is_(None),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def count_by_businesses(self) -> ConcurrentStableDict[int, int]:
        """按业务码批量统计权限码数量（列表页「权限码数」列用）。

        Returns:
            ConcurrentStableDict[int, int]: 业务码 ID → 权限码数量。
        """
        statement = (
            select(SysPermission.business_id, sa.func.count())
            .where(SysPermission.deleted_at.is_(None))
            .group_by(SysPermission.business_id)
        )
        rows = (await self._session.execute(statement)).all()
        return ConcurrentStableDict({int(cast("int", row[0])): int(cast("int", row[1])) for row in rows})

    async def count_by_action(self, action_id: int) -> int:
        """统计某动作码下的权限码数量（含停用）。

        Args:
            action_id: 动作码 ID。

        Returns:
            int: 权限码数量。
        """
        statement = (
            select(sa.func.count())
            .select_from(SysPermission)
            .where(
                SysPermission.action_id == action_id,
                SysPermission.deleted_at.is_(None),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def list_by_action(self, action_id: int) -> ConcurrentStableList[SysPermission]:
        """列示某动作码下的权限码（含停用；主键升序）。

        Args:
            action_id: 动作码 ID。

        Returns:
            ConcurrentStableList[SysPermission]: 权限码列表。
        """
        statement = self._select().where(self._column("action_id") == action_id).order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def restore(self, item_id: int) -> bool:
        """恢复软删除的权限码行。

        Args:
            item_id: 权限码主键。

        Returns:
            bool: 是否恢复成功（行不存在返回 False）。
        """
        statement = select(SysPermission).where(SysPermission.id == item_id, SysPermission.deleted_at.is_not(None))
        row = (await self._session.execute(statement)).scalars().first()
        if row is None:  # pragma: no cover - 调用方按已取到的软删行传入，行必存在
            return False
        row.restore()
        await self._session.flush()
        return True
