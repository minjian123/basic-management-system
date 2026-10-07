"""平台服务 repositories 层：菜单与权限元数据仓储（六实体 + 多语言附表）。

- 主表仓储继承 `BaseDbRepository`（软删除过滤与统一 CRUD 由基类提供）；
- 多语言附表经模块级辅助函数读写（软删除旧行再插新行，规避 `(主表 ID, locale, deleted_at)` 唯一冲突）；
- 树与表单元数据一次装载（元数据量级小），聚合与过滤归服务层。
"""

from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_platform.models.menu import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysButton,
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuForm,
    SysMenuI18n,
)


async def _load_i18n(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_ids: ConcurrentStableList[int],
    locale: str,
) -> ConcurrentStableDict[int, str]:
    """按主表 ID 集合与语言装载多语言文案。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名（如 `menu_id`）。
        owner_ids: 主表 ID 集合。
        locale: 语言标识。

    Returns:
        ConcurrentStableDict[int, str]: 主表 ID → 该语言文案。
    """
    if not owner_ids:
        return ConcurrentStableDict()
    key_attr = getattr(model, key_column)
    statement = select(key_attr, model.name).where(
        key_attr.in_(list(owner_ids)),
        model.locale == locale,
        model.deleted_at.is_(None),
    )
    rows = (await session.execute(statement)).all()
    return ConcurrentStableDict({int(cast("int", row[0])): str(cast("str", row[1])) for row in rows})


async def _replace_i18n(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_id: int,
    names: ConcurrentStableDict[str, str],
) -> None:
    """整体替换某主表行的多语言文案（软删除旧行后插新行）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名。
        owner_id: 主表 ID。
        names: 语言标识 → 文案。
    """
    key_attr = getattr(model, key_column)
    existing = (await session.execute(select(model).where(key_attr == owner_id, model.deleted_at.is_(None)))).scalars()
    for row in existing.all():
        row.soft_delete()
    for locale, name in names.items():
        session.add(model(**{key_column: owner_id, "locale": locale, "name": name}))
    await session.flush()


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
        return await _load_i18n(self._session, SysBusinessI18n, "business_id", business_ids, locale)


class ActionRepository(BaseDbRepository[SysAction]):
    """动作权限码仓储（`sys_action`）。"""

    model = SysAction

    async def list_by_business(self, business_id: int | None = None) -> ConcurrentStableList[SysAction]:
        """按业务码列示动作码（可空 = 全部；主键升序）。

        Args:
            business_id: 业务码 ID；None 表示全部。

        Returns:
            ConcurrentStableList[SysAction]: 动作码列表（插入序）。
        """
        statement = self._select()
        if business_id is not None:
            statement = statement.where(self._column("business_id") == business_id)
        statement = statement.order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_i18n(self, action_ids: ConcurrentStableList[int], locale: str) -> ConcurrentStableDict[int, str]:
        """装载动作码多语言文案。

        Args:
            action_ids: 动作码 ID 集合。
            locale: 语言标识。

        Returns:
            ConcurrentStableDict[int, str]: 动作码 ID → 文案。
        """
        return await _load_i18n(self._session, SysActionI18n, "action_id", action_ids, locale)


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
        return await _load_i18n(self._session, SysMenuI18n, "menu_id", menu_ids, locale)

    async def replace_i18n(self, menu_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换菜单多语言文案。

        Args:
            menu_id: 菜单 ID。
            names: 语言标识 → 文案。
        """
        await _replace_i18n(self._session, SysMenuI18n, "menu_id", menu_id, names)


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

    async def get_by_form_action(self, form_id: int, action_id: int) -> SysButton | None:
        """按「表单 + 动作」探测既有按钮（1:1）。

        Args:
            form_id: 表单 ID。
            action_id: 动作码 ID。

        Returns:
            SysButton | None: 既有按钮；无则 None。
        """
        statement = (
            self._select().where(self._column("form_id") == form_id, self._column("action_id") == action_id).limit(1)
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
        return await _load_i18n(self._session, SysFieldI18n, "field_id", field_ids, locale)

    async def replace_i18n(self, field_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整体替换字段多语言文案。

        Args:
            field_id: 字段 ID。
            names: 语言标识 → 文案。
        """
        await _replace_i18n(self._session, SysFieldI18n, "field_id", field_id, names)
