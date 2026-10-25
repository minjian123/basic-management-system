"""平台服务 repositories 层：菜单与权限元数据仓储（业务码 / 动作码 / 权限码 + 菜单 / 表单 / 按钮 / 字段 + 多语言附表）。

- 主表仓储继承 `BaseDbRepository`（软删除过滤与统一 CRUD 由基类提供）；
- 多语言附表经模块级辅助函数读写（软删除旧行再插新行，规避 `(主表 ID, locale, deleted_at)` 唯一冲突）；
- 树与表单元数据一次装载（元数据量级小），聚合与过滤归服务层。
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.platform.menu_form import (
    SysButton,
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuForm,
    SysMenuI18n,
)
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.repositories.i18n import load_i18n, load_i18n_all
from bms_core.repositories.i18n import replace_i18n as replace_i18n_rows


class MenuRepository(BaseDbRepository[SysMenu]):
    """菜单仓储（`sys_menu`）：树装载与路径唯一探测。"""

    model = SysMenu

    async def list_all(self) -> ConcurrentStableList[SysMenu]:
        """列示全部菜单（同级排序升序、主键兜底）。

        Returns:
            ConcurrentStableList[SysMenu]: 菜单列表（插入序）。
        """
        statement = self._select().order_by(self._column("sort"), self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_path(self, path: str) -> SysMenu | None:
        """按路由路径探测菜单（软删除过滤）。

        Args:
            path: 前端路由路径。

        Returns:
            SysMenu | None: 既有菜单；无则 None。
        """
        statement = self._select().where(self._column("path") == path).limit(1)
        return (await self._session.execute(statement)).scalars().first()

    async def list_i18n(self, menu_ids: ConcurrentStableList[int], locale: str) -> ConcurrentStableDict[int, str]:
        """装载菜单多语言文案。

        Args:
            menu_ids: 菜单 ID 集合。
            locale: 语言标识。

        Returns:
            ConcurrentStableDict[int, str]: 菜单 ID → 文案。
        """
        return await load_i18n(self._session, SysMenuI18n, "menu_id", menu_ids, locale)

    async def list_i18n_all(
        self, menu_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """装载菜单**全部语言**文案（维护视图出参：多语言文案字段需按语言清单回显）。

        Args:
            menu_ids: 菜单 ID 集合。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 菜单 ID → （locale → 文案）。
        """
        return await load_i18n_all(self._session, SysMenuI18n, "menu_id", menu_ids)

    async def replace_i18n(self, menu_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换菜单多语言文案。

        Args:
            menu_id: 菜单 ID。
            names: 语言标识 → 文案。
        """
        await replace_i18n_rows(self._session, SysMenuI18n, "menu_id", menu_id, names)


class FormRepository(BaseDbRepository[SysForm]):
    """表单仓储（`sys_form`）：业务 1:1 挂接探测（菜单入口经 `sys_menu_form`）。"""

    model = SysForm

    async def list_all(self) -> ConcurrentStableList[SysForm]:
        """列示全部表单（主键升序）。

        Returns:
            ConcurrentStableList[SysForm]: 表单列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_business(self, business_id: int) -> SysForm | None:
        """按业务码探测表单（1:1）。

        Args:
            business_id: 业务码 ID。

        Returns:
            SysForm | None: 既有表单；无则 None。
        """
        statement = self._select().where(self._column("business_id") == business_id).limit(1)
        return (await self._session.execute(statement)).scalars().first()


class MenuFormRepository(BaseDbRepository[SysMenuForm]):
    """菜单 ↔ 表单关联仓储（`sys_menu_form`）：多对多装载、探测与批量软删。"""

    model = SysMenuForm

    async def list_all(self) -> ConcurrentStableList[SysMenuForm]:
        """列示全部关联（主键升序）。

        Returns:
            ConcurrentStableList[SysMenuForm]: 关联行列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_by_menu(self, menu_id: int) -> ConcurrentStableList[SysMenuForm]:
        """按菜单列示关联（主键升序）。

        Args:
            menu_id: 菜单 ID。

        Returns:
            ConcurrentStableList[SysMenuForm]: 关联行列表（插入序）。
        """
        statement = self._select().where(self._column("menu_id") == menu_id).order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_form_ids_by_menu(self, menu_id: int) -> ConcurrentStableList[int]:
        """按菜单取关联的表单主键清单（主键升序）。

        Args:
            menu_id: 菜单 ID。

        Returns:
            ConcurrentStableList[int]: 表单主键清单。
        """
        statement = (
            select(self._column("form_id"))
            .where(*self._scope_where(), self._column("menu_id") == menu_id)
            .order_by(self._column("id"))
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_by_form(self, form_id: int) -> ConcurrentStableList[SysMenuForm]:
        """按表单列示关联（主键升序）。

        Args:
            form_id: 表单 ID。

        Returns:
            ConcurrentStableList[SysMenuForm]: 关联行列表（插入序）。
        """
        statement = self._select().where(self._column("form_id") == form_id).order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_menu_form(self, menu_id: int, form_id: int) -> SysMenuForm | None:
        """按「菜单 + 表单」探测生效关联。

        Args:
            menu_id: 菜单 ID。
            form_id: 表单 ID。

        Returns:
            SysMenuForm | None: 既有生效关联；无则 None。
        """
        statement = (
            self._select().where(self._column("menu_id") == menu_id, self._column("form_id") == form_id).limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def delete_by_form(self, form_id: int, *, now: datetime | None = None) -> None:
        """批量软删表单的全部关联（表单删除时解除挂接）。

        Args:
            form_id: 表单 ID。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or datetime.now(UTC).replace(tzinfo=None)
        statement = (
            sa.update(self.model)
            .where(self._column("form_id") == form_id, self._column("deleted_at").is_(None))
            .values(deleted_at=current, updated_at=current)
        )
        await self._session.execute(statement)

    async def delete_by_menu(self, menu_id: int, *, now: datetime | None = None) -> None:
        """批量软删菜单的全部关联（菜单删除时解除挂接）。

        Args:
            menu_id: 菜单 ID。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or datetime.now(UTC).replace(tzinfo=None)
        statement = (
            sa.update(self.model)
            .where(self._column("menu_id") == menu_id, self._column("deleted_at").is_(None))
            .values(deleted_at=current, updated_at=current)
        )
        await self._session.execute(statement)


class ButtonRepository(BaseDbRepository[SysButton]):
    """按钮仓储（`sys_button`）：按表单列示与唯一探测。"""

    model = SysButton

    async def list_by_form(self, form_id: int) -> ConcurrentStableList[SysButton]:
        """按表单列示按钮（排序升序、主键兜底）。

        Args:
            form_id: 表单 ID。

        Returns:
            ConcurrentStableList[SysButton]: 按钮列表（插入序）。
        """
        statement = (
            self._select().where(self._column("form_id") == form_id).order_by(self._column("sort"), self._column("id"))
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_all(self) -> ConcurrentStableList[SysButton]:
        """列示全部按钮（主键升序）。

        Returns:
            ConcurrentStableList[SysButton]: 按钮列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_by_permission(self, permission_id: int) -> ConcurrentStableList[SysButton]:
        """按权限码列示挂接的按钮（删除 / 停用权限码时的引用探测）。

        Args:
            permission_id: 权限码 ID。

        Returns:
            ConcurrentStableList[SysButton]: 按钮列表（插入序）。
        """
        statement = self._select().where(self._column("permission_id") == permission_id)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_form_permission(self, form_id: int, permission_id: int) -> SysButton | None:
        """按「表单 + 权限码」探测既有按钮（1:1）。

        Args:
            form_id: 表单 ID。
            permission_id: 权限码 ID。

        Returns:
            SysButton | None: 既有按钮；无则 None。
        """
        statement = (
            self._select()
            .where(self._column("form_id") == form_id, self._column("permission_id") == permission_id)
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()


class FieldRepository(BaseDbRepository[SysField]):
    """字段仓储（`sys_field`）：按表单列示与键唯一探测。"""

    model = SysField

    async def list_by_form(self, form_id: int) -> ConcurrentStableList[SysField]:
        """按表单列示字段（排序升序、主键兜底）。

        Args:
            form_id: 表单 ID。

        Returns:
            ConcurrentStableList[SysField]: 字段列表（插入序）。
        """
        statement = (
            self._select().where(self._column("form_id") == form_id).order_by(self._column("sort"), self._column("id"))
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_all(self) -> ConcurrentStableList[SysField]:
        """列示全部字段（主键升序）。

        Returns:
            ConcurrentStableList[SysField]: 字段列表（插入序）。
        """
        statement = self._select().order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_by_form_key(self, form_id: int, field_key: str) -> SysField | None:
        """按「表单 + 字段键」探测既有字段。

        Args:
            form_id: 表单 ID。
            field_key: 字段键。

        Returns:
            SysField | None: 既有字段；无则 None。
        """
        statement = (
            self._select().where(self._column("form_id") == form_id, self._column("field_key") == field_key).limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def list_i18n(self, field_ids: ConcurrentStableList[int], locale: str) -> ConcurrentStableDict[int, str]:
        """装载字段多语言文案。

        Args:
            field_ids: 字段 ID 集合。
            locale: 语言标识。

        Returns:
            ConcurrentStableDict[int, str]: 字段 ID → 文案。
        """
        return await load_i18n(self._session, SysFieldI18n, "field_id", field_ids, locale)

    async def list_i18n_all(
        self, field_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """装载字段**全部语言**文案（维护视图出参）。

        Args:
            field_ids: 字段 ID 集合。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 字段 ID → （locale → 文案）。
        """
        return await load_i18n_all(self._session, SysFieldI18n, "field_id", field_ids)

    async def replace_i18n(self, field_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换字段多语言文案。

        Args:
            field_id: 字段 ID。
            names: 语言标识 → 文案。
        """
        await replace_i18n_rows(self._session, SysFieldI18n, "field_id", field_id, names)
