"""表单元数据读面实现（`FormMetadataPort`）：平台库只读（业务码 → 表单 → 字段 + 物理表名）。

**为什么在本域另建读面**（域边界）：菜单元数据归 `menu_form` 域，跨域只能经其公共出口或能力契约；
本实现**只读平台库三表**（`sys_business` / `sys_form` / `sys_field`），不写、不 JOIN 租户库，
且经装配面注入（域实现之间零 import）。

**物理表名来源**：`form_code`（业务码）→ 表单标识清单 `FORM_CATALOG` 的 `form_key → table`
（`bms_core/registry/forms.py`，构建期清单 + 产品注入）。解析不到即不可建列（`40401`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.registry.forms import FormRecord, FormRegistry
from bms_platform.domains.form_design.ports import FormFieldSnapshot

__all__ = [
    "BusinessFormSnapshot",
    "FieldSnapshot",
    "MetadataRepository",
    "PlatformModelCollection",
]


class PlatformModelCollection(Protocol):
    r"""平台库三表模型集合（装配面注入的 \`_PlatformMetadataModels\`）。

    域实现不 import 他域模型，模型类由装配面以本协议注入；ORM 模型类的列属性是运行期元数据，
    类型层面以 \`type[Any]\` 表达（SQLAlchemy 的列表达式无法在静态类型上逐列声明）。
    """

    @property
    def business(self) -> type[Any]:
        """业务码模型（`sys_business`）。"""
        ...

    @property
    def form(self) -> type[Any]:
        """表单模型（`sys_form`）。"""
        ...

    @property
    def field(self) -> type[Any]:
        """字段模型（`sys_field`）。"""
        ...


@dataclass(frozen=True)
class FieldSnapshot(BaseValueObject):
    """平台字段快照（`sys_field` 只读）。"""

    field_key: str
    """字段键。"""
    name: str
    """字段名（默认文案）。"""
    type: str
    """字段类型。"""
    sort: int
    """同表单内排序。"""
    status: str
    """状态（`enabled` / `disabled`）。"""


@dataclass(frozen=True)
class BusinessFormSnapshot(BaseValueObject):
    """业务码 + 表单快照（跨库逻辑引用：`sys_business.code` ↔ `sys_form.business_id`）。"""

    form_code: str
    """表单标识（业务码）。"""
    form_id: int
    """表单主键（`sys_form.id`）。"""
    status: str
    """表单状态。"""
    table_name: str | None = None
    """派生物理表名（表单标识清单解析；不可解析为 None）。"""
    fields: ConcurrentStableList[FormFieldSnapshot] = field(default_factory=lambda: ConcurrentStableList())
    """平台字段清单（`sort` 升序；契约按 `FormMetadataSnapshot` 声明，构造时填 `FieldSnapshot`）。"""


class MetadataRepository:
    r"""平台库表单元数据只读仓储（`FormMetadataPort` 的实现）。

    **模型引用经注入**：本仓储只做「按业务码 → 表单 → 字段」的读取编排，三张平台表的 ORM 模型由
    装配面以 \`models\` 注入（\`menu_form\` / \`permission_meta\` 域的表）——域实现不 import 他域模型，
    依赖方向恒为「装配 → 域」。
    """

    def __init__(
        self,
        session: DbSession,
        *,
        registry: FormRegistry | None = None,
        models: PlatformModelCollection,
    ) -> None:
        r"""初始化。

        Args:
            session: 平台库会话。
            registry: 表单标识清单（None 用构建期清单，产品注入项由装配面传入）。
            models: 平台表模型集合（\`business\` / \`form\` / \`field\` 三个模型类；装配面注入）。
        """
        self._session = session
        self._registry = registry if registry is not None else FormRegistry()
        self._models = models

    async def load(self, form_code: str) -> BusinessFormSnapshot | None:
        """按业务码装载表单元数据（表单不存在 / 业务码停用返回 None）。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            BusinessFormSnapshot | None: 快照；不可定制返回 None。
        """
        business_model = self._models.business
        business = (
            (
                await self._session.execute(
                    select(business_model).where(
                        business_model.code == form_code,
                        business_model.status == "enabled",
                        business_model.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if business is None:
            return None
        form_model = self._models.form
        form = (
            (
                await self._session.execute(
                    select(form_model).where(
                        form_model.business_id == business.id,
                        form_model.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if form is None:
            return None
        field_model = self._models.field
        rows = (
            (
                await self._session.execute(
                    select(field_model)
                    .where(field_model.form_id == form.id, field_model.deleted_at.is_(None))
                    .order_by(field_model.sort.asc(), field_model.field_key.asc())
                )
            )
            .scalars()
            .all()
        )
        fields: ConcurrentStableList[FormFieldSnapshot] = ConcurrentStableList(
            FieldSnapshot(
                field_key=row.field_key,
                name=row.name,
                type=row.type,
                sort=row.sort,
                status=row.status,
            )
            for row in rows
        )
        return BusinessFormSnapshot(
            form_code=form_code,
            form_id=form.id,
            status=form.status,
            table_name=self._table_of(form_code),
            fields=fields,
        )

    def _table_of(self, form_code: str) -> str | None:
        """按表单标识清单解析物理表名（`form_key → table`）。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            str | None: 物理表名；未登记返回 None。
        """
        records: ConcurrentStableDict[str, FormRecord] = ConcurrentStableDict()
        for record in self._registry.catalog_records():
            if record.form_key not in records:
                records.set(record.form_key, record)
        record = records.get(form_code)
        if record is None:
            return None
        return record.table
