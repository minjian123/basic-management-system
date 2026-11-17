"""布局与字段属性仓储：`sys_form_layout` / `sys_form_field_attr`。

- 两级读取：按表单取全部层级行（三级解析在服务层做），按表单 + 层级取单行；
- 写入为**整份覆盖式**（布局保存 / 属性保存）：同 `(form_code, scope, role_id)` 存在则改、否则建；
- 唯一性由应用层判重（`(form_code, scope, role_id, deleted_at)` 复合唯一在 `deleted_at IS NULL` 时
  不生效——NULL 互不相等，三库同语义），故取行时必须显式过滤软删。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete as sa_delete

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.form_design import (
    SysFieldExt,
    SysFormFieldAttr,
    SysFormLayout,
)
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["FieldAttrRepository", "FieldExtRepository", "FormLayoutRepository"]


class FormLayoutRepository(BaseDbRepository[SysFormLayout]):
    """表单布局仓储（`sys_form_layout`）。"""

    model = SysFormLayout

    async def list_by_form(self, form_code: str) -> ConcurrentStableList[SysFormLayout]:
        """取该表单的全部层级布局（未删行，插入序）。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            ConcurrentStableList[SysFormLayout]: 布局行（可能为空）。
        """
        statement = (
            self._select()
            .where(self._column("form_code") == form_code)
            .order_by(self._column("scope").asc(), self._column("role_id").asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableList(rows)

    async def get_by_level(self, form_code: str, scope: str, role_id: int) -> SysFormLayout | None:
        """取指定层级布局（未删行）。

        Args:
            form_code: 表单标识。
            scope: 层级。
            role_id: 角色 ID（非角色层级传 0）。

        Returns:
            SysFormLayout | None: 布局行；不存在返回 None。
        """
        statement = self._select().where(
            self._column("form_code") == form_code,
            self._column("scope") == scope,
            self._column("role_id") == role_id,
        )
        return (await self._session.execute(statement)).scalars().first()

    async def upsert(
        self,
        *,
        form_code: str,
        scope: str,
        role_id: int,
        layout_config: str,
        now: datetime,
        actor: int | None,
    ) -> SysFormLayout:
        """整份覆盖式写入某层级布局（存在则改、不存在则建）。

        Args:
            form_code: 表单标识。
            scope: 层级。
            role_id: 角色 ID。
            layout_config: 布局配置 JSON 文本。
            now: 当前时刻（UTC naive）。
            actor: 操作人（可空）。

        Returns:
            SysFormLayout: 写入后的行。
        """
        existing = await self.get_by_level(form_code, scope, role_id)
        if existing is None:
            return await self.create(
                form_code=form_code,
                scope=scope,
                role_id=role_id,
                layout_config=layout_config,
                status="enabled",
            )
        updated = await self.update(existing.id, layout_config=layout_config, status="enabled")
        if updated is None:  # pragma: no cover - 取到即存在，更新必成功
            return existing
        return updated

    async def purge_by_level(self, form_code: str, scope: str, role_id: int) -> bool:
        """物理删除某层级布局（恢复默认：删该层回退下一级）。

        Args:
            form_code: 表单标识。
            scope: 层级。
            role_id: 角色 ID。

        Returns:
            bool: 删到为 True。
        """
        conditions = (
            SysFormLayout.form_code == form_code,
            SysFormLayout.scope == scope,
            SysFormLayout.role_id == role_id,
        )
        rows = (await self._session.execute(self._select().where(*conditions))).scalars().all()
        if len(rows) == 0:
            return False
        await self._session.execute(sa_delete(SysFormLayout).where(*conditions))
        return True


class FieldAttrRepository(BaseDbRepository[SysFormFieldAttr]):
    """字段属性仓储（`sys_form_field_attr`）。"""

    model = SysFormFieldAttr

    async def list_by_form(self, form_code: str) -> ConcurrentStableList[SysFormFieldAttr]:
        """取该表单的全部层级属性（未删行）。

        Args:
            form_code: 表单标识。

        Returns:
            ConcurrentStableList[SysFormFieldAttr]: 属性行（可能为空）。
        """
        statement = (
            self._select()
            .where(self._column("form_code") == form_code)
            .order_by(self._column("scope").asc(), self._column("role_id").asc(), self._column("field_key").asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableList(rows)

    async def replace_level(
        self,
        *,
        form_code: str,
        scope: str,
        role_id: int,
        items: ConcurrentStableList[tuple[str, str]],
    ) -> ConcurrentStableList[SysFormFieldAttr]:
        """整份覆盖某层级属性（先删该层全部行，再按 `items` 建）。

        Args:
            form_code: 表单标识。
            scope: 层级。
            role_id: 角色 ID。
            items: 待写入项（`(field_key, attrs_json)` 插入序）。

        Returns:
            ConcurrentStableList[SysFormFieldAttr]: 写入后的行（插入序）。
        """
        purge = sa_delete(SysFormFieldAttr).where(
            SysFormFieldAttr.form_code == form_code,
            SysFormFieldAttr.scope == scope,
            SysFormFieldAttr.role_id == role_id,
        )
        await self._session.execute(purge)
        created: ConcurrentStableList[SysFormFieldAttr] = ConcurrentStableList()
        for field_key, attrs in items:
            created.add(
                await self.create(
                    form_code=form_code,
                    scope=scope,
                    role_id=role_id,
                    field_key=field_key,
                    attrs=attrs,
                )
            )
        return created

    async def purge_level(self, form_code: str, scope: str, role_id: int) -> bool:
        """物理删除某层级属性（恢复默认）。

        Args:
            form_code: 表单标识。
            scope: 层级。
            role_id: 角色 ID。

        Returns:
            bool: 删到为 True。
        """
        conditions = (
            SysFormFieldAttr.form_code == form_code,
            SysFormFieldAttr.scope == scope,
            SysFormFieldAttr.role_id == role_id,
        )
        rows = (await self._session.execute(self._select().where(*conditions))).scalars().all()
        if len(rows) == 0:
            return False
        await self._session.execute(sa_delete(SysFormFieldAttr).where(*conditions))
        return True


class FieldExtRepository(BaseDbRepository[SysFieldExt]):
    """租户自建字段仓储（`sys_field_ext`）。"""

    model = SysFieldExt

    async def list_by_form(self, form_code: str) -> ConcurrentStableList[SysFieldExt]:
        """取该表单的自建字段（未删行，按 `sort` 升序 + `field_key` 升序）。

        Args:
            form_code: 表单标识。

        Returns:
            ConcurrentStableList[SysFieldExt]: 自建字段行。
        """
        statement = (
            self._select()
            .where(self._column("form_code") == form_code)
            .order_by(self._column("sort").asc(), self._column("field_key").asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableList(rows)

    async def get_by_key(self, form_code: str, field_key: str) -> SysFieldExt | None:
        """按字段键取自建字段（未删行；含停用行，供重建复用判定）。

        Args:
            form_code: 表单标识。
            field_key: 字段键。

        Returns:
            SysFieldExt | None: 自建字段行；不存在返回 None。
        """
        statement = self._select().where(
            self._column("form_code") == form_code,
            self._column("field_key") == field_key,
        )
        return (await self._session.execute(statement)).scalars().first()

    async def list_active(self, form_code: str) -> ConcurrentStableList[SysFieldExt]:
        """取该表单已生效的自建字段（`status=enabled` ∧ `ddl_status=active`）。

        Args:
            form_code: 表单标识。

        Returns:
            ConcurrentStableList[SysFieldExt]: 生效自建字段（`sort` 升序）。
        """
        statement = (
            self._select()
            .where(
                self._column("form_code") == form_code,
                self._column("status") == "enabled",
                self._column("ddl_status") == "active",
            )
            .order_by(self._column("sort").asc(), self._column("field_key").asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableList(rows)
