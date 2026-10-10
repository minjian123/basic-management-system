"""字典种子：平台常用字典（类型 / 条目 / i18n / 属性）幂等写入。

- 幂等：按 `code` 与 `(dict_type_id, value)` 判存（存在跳过）；可重复执行（`ops/seed_dict.py` 与测试夹具共用）。
- 用途：开发 / 联调 / 测试（`user_status` / `user_gender` / `biz_type` / `region` 级联示例）；
  真实平台种子随字典模块阶段（阶段八）扩展。
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseI18nSeedContract, BaseValueObject
from bms_core.dict.models import SysDictAttr, SysDictItem, SysDictItemI18n, SysDictType, SysDictTypeI18n

__all__ = ["SEED_TYPES", "SeedAttr", "SeedItem", "SeedType", "seed_dicts"]


@dataclass(frozen=True)
class SeedItem(BaseI18nSeedContract):
    """种子条目。"""

    code: str
    value: str
    label: str
    color: str | None = None
    parent_value: str | None = None
    i18n: ConcurrentStableDict[str, str] = field(default_factory=ConcurrentStableDict[str, str])


@dataclass(frozen=True)
class SeedAttr(BaseValueObject):
    """种子扩展属性。"""

    attr_key: str
    name: str
    data_type: str
    operators: tuple[str, ...] | None = None
    widget: str | None = None


@dataclass(frozen=True)
class SeedType(BaseI18nSeedContract):
    """种子字典类型。"""

    type: str
    name: str
    items: tuple[SeedItem, ...]
    sort: int = 0
    i18n: ConcurrentStableDict[str, str] = field(default_factory=ConcurrentStableDict[str, str])
    attrs: tuple[SeedAttr, ...] = ()


SEED_TYPES: tuple[SeedType, ...] = (
    SeedType(
        type="user_status",
        name="用户状态",
        sort=1,
        i18n=ConcurrentStableDict({"en-US": "User status"}),
        items=(
            SeedItem(
                code="enabled",
                value="enabled",
                label="启用",
                color="success",
                i18n=ConcurrentStableDict({"en-US": "Enabled"}),
            ),
            SeedItem(
                code="disabled",
                value="disabled",
                label="停用",
                color="danger",
                i18n=ConcurrentStableDict({"en-US": "Disabled"}),
            ),
        ),
    ),
    SeedType(
        type="user_gender",
        name="性别",
        sort=2,
        i18n=ConcurrentStableDict({"en-US": "Gender"}),
        items=(
            SeedItem(code="male", value="male", label="男", i18n=ConcurrentStableDict({"en-US": "Male"})),
            SeedItem(code="female", value="female", label="女", i18n=ConcurrentStableDict({"en-US": "Female"})),
            SeedItem(code="unknown", value="unknown", label="未知"),
        ),
    ),
    SeedType(
        type="biz_type",
        name="业务类型",
        sort=3,
        i18n=ConcurrentStableDict({"en-US": "Business type"}),
        items=(
            SeedItem(code="purchase", value="purchase", label="采购", color="primary"),
            SeedItem(code="sales", value="sales", label="销售", color="success"),
            SeedItem(code="inventory", value="inventory", label="库存", color="info"),
        ),
        attrs=(SeedAttr(attr_key="budget", name="预算金额", data_type="number", widget="number"),),
    ),
    SeedType(
        type="region",
        name="行政区划",
        sort=4,
        i18n=ConcurrentStableDict({"en-US": "Region"}),
        items=(
            SeedItem(code="zj", value="zj", label="浙江省"),
            SeedItem(code="hz", value="hz", label="杭州市", parent_value="zj"),
            SeedItem(code="xh", value="xh", label="西湖区", parent_value="hz"),
        ),
        attrs=(SeedAttr(attr_key="level", name="层级", data_type="number", widget="number"),),
    ),
)


async def seed_dicts(session: AsyncSession) -> int:
    """幂等写入种子（返回新增行数；已存在项跳过）。

    Args:
        session: 租户库会话（调用方负责引擎与租户）。

    Returns:
        int: 新增行数（类型 + 条目 + i18n + 属性）。
    """
    created = 0
    for seed in SEED_TYPES:
        type_row = await _find_type(session, seed.type)
        if type_row is None:
            type_row = SysDictType(code=seed.type, name=seed.name, sort=seed.sort, status="enabled")
            session.add(type_row)
            await session.flush()
            created += 1
        created += await _seed_type_i18n(session, type_row, seed)
        created += await _seed_items(session, type_row, ConcurrentStableList(seed.items))
        created += await _seed_attrs(session, type_row, ConcurrentStableList(seed.attrs))
    await session.commit()
    return created


async def _find_type(session: AsyncSession, dict_type: str) -> SysDictType | None:
    """按类型码取未删除类型。

    Args:
        session: 租户库会话。
        dict_type: 类型编码。

    Returns:
        SysDictType | None: 类型行；不存在返回 None。
    """
    stmt = select(SysDictType).where(SysDictType.code == dict_type, SysDictType.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def _seed_type_i18n(session: AsyncSession, type_row: SysDictType, seed: SeedType) -> int:
    """写入类型 i18n（幂等）。

    Args:
        session: 租户库会话。
        type_row: 类型行。
        seed: 种子定义。

    Returns:
        int: 新增行数。
    """
    created = 0
    for locale, label in seed.i18n.items():
        stmt = select(SysDictTypeI18n).where(
            SysDictTypeI18n.dict_type_id == type_row.id,
            SysDictTypeI18n.locale == locale,
            SysDictTypeI18n.deleted_at.is_(None),
        )
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            continue
        session.add(SysDictTypeI18n(dict_type_id=type_row.id, locale=locale, label=label))
        created += 1
    return created


def _link_parents(rows_by_value: ConcurrentStableDict[str, SysDictItem], items: ConcurrentStableList[SeedItem]) -> None:
    """按父条目 `value` 回填上级条目 ID（第二遍；`parent_id` 自引用同表 `id`）。

    Args:
        rows_by_value: 条目 `value` → ORM 行（第一遍写入后）。
        items: 种子条目序列。
    """
    for item in items:
        if item.parent_value is None:
            continue
        row = rows_by_value.get(item.value)
        parent = rows_by_value.get(item.parent_value)
        if row is None or parent is None or row.parent_id == parent.id:
            continue
        row.parent_id = parent.id


async def _seed_items(session: AsyncSession, type_row: SysDictType, items: ConcurrentStableList[SeedItem]) -> int:
    """写入条目与条目 i18n（幂等），并回填上级条目 ID。

    Args:
        session: 租户库会话。
        type_row: 类型行。
        items: 种子条目序列。

    Returns:
        int: 新增行数。
    """
    created = 0
    rows_by_value: ConcurrentStableDict[str, SysDictItem] = ConcurrentStableDict()
    for item in items:
        stmt = select(SysDictItem).where(
            SysDictItem.dict_type_id == type_row.id,
            SysDictItem.value == item.value,
            SysDictItem.deleted_at.is_(None),
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = SysDictItem(
                dict_type_id=type_row.id,
                code=item.code,
                name=item.label,
                value=item.value,
                color=item.color,
                sort=0,
                status="enabled",
            )
            session.add(row)
            await session.flush()
            created += 1
        rows_by_value.set(item.value, row)
        for locale, label in item.i18n.items():
            i18n_stmt = select(SysDictItemI18n).where(
                SysDictItemI18n.dict_item_id == row.id,
                SysDictItemI18n.locale == locale,
                SysDictItemI18n.deleted_at.is_(None),
            )
            if (await session.execute(i18n_stmt)).scalar_one_or_none() is not None:
                continue
            session.add(SysDictItemI18n(dict_item_id=row.id, locale=locale, label=label))
            created += 1
    _link_parents(rows_by_value, items)
    await session.flush()
    return created


async def _seed_attrs(session: AsyncSession, type_row: SysDictType, attrs: ConcurrentStableList[SeedAttr]) -> int:
    """写入扩展属性（幂等）。

    Args:
        session: 租户库会话。
        type_row: 类型行。
        attrs: 种子属性序列。

    Returns:
        int: 新增行数。
    """
    created = 0
    for index, attr in enumerate(attrs):
        stmt = select(SysDictAttr).where(
            SysDictAttr.dict_type_id == type_row.id,
            SysDictAttr.attr_key == attr.attr_key,
            SysDictAttr.deleted_at.is_(None),
        )
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            continue
        session.add(
            SysDictAttr(
                dict_type_id=type_row.id,
                attr_key=attr.attr_key,
                name=attr.name,
                data_type=attr.data_type,
                operators=list(attr.operators) if attr.operators is not None else None,
                widget=attr.widget,
                sort=index,
                status="enabled",
                scope="platform",
            )
        )
        created += 1
    return created
