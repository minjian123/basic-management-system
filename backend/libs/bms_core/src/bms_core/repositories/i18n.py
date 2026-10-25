"""多语言附表通用读写助手（域无关工具）。

平台各业务域的“主表 + `*_i18n` 附表”结构一致：附表以 `<主表>_id` 关联、`locale` 区分语言、
`name` 存文案、软删除保证 `(主表 ID, locale, deleted_at)` 唯一。本模块只提供这三条通用操作，
**不含任何业务语义**——业务域仓储自行组合：

- `load_i18n`：按主表 ID 集合与语言装载文案（读路径）；
- `load_i18n_all`：按主表 ID 集合装载全部语言（维护视图：编辑需见全部语言与停用语言存量值）；
- `replace_i18n`：整体替换某主表行的多语言文案（软删除旧行再插新行，规避唯一冲突）。

为什么在基座：菜单表单与权限元数据（图标名称）两个业务域都用同一套读写口径，留在任一域都会
造成跨域 import；本模块不含表归属，仅按传入模型操作。
"""

from typing import Any, cast

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.session import DbSession

__all__ = ["load_i18n", "load_i18n_all", "replace_i18n"]


async def load_i18n(
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


async def load_i18n_all(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_ids: ConcurrentStableList[int],
) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
    """按主表 ID 集合装载**全部语言**的多语言文案（维护视图用）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名（如 `menu_id`）。
        owner_ids: 主表 ID 集合。

    Returns:
        ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 主表 ID → （locale → 文案）。
    """
    if not owner_ids:
        return ConcurrentStableDict()
    key_attr = getattr(model, key_column)
    statement = select(key_attr, model.locale, model.name).where(
        key_attr.in_(list(owner_ids)),
        model.deleted_at.is_(None),
    )
    rows = (await session.execute(statement)).all()
    result: ConcurrentStableDict[int, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for row in rows:
        owner_id = int(cast("int", row[0]))
        bucket = result.get(owner_id)
        if bucket is None:
            bucket = ConcurrentStableDict[str, str]()
            result.set(owner_id, bucket)
        bucket.set(str(cast("str", row[1])), str(cast("str", row[2])))
    return result


async def replace_i18n(
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
