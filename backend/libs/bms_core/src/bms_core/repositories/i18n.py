"""多语言附表通用读写助手（域无关工具）。

平台各业务域的“主表 + `*_i18n` 附表”结构一致：附表以 `<主表>_id` 关联、`locale` 区分语言、
文案列存文本、软删除保证 `(主表 ID, locale, deleted_at)` 唯一。本模块只提供通用操作，
**不含任何业务语义**——业务域仓储自行组合：

- `load_i18n`：按主表 ID 集合与**语言优先级序**装载文案（读路径，两级回退）；
- `load_i18n_texts`：同上但支持**多文案列**（如邮件模板 `subject` + `content`），每列独立回退；
- `load_i18n_all` / `load_i18n_all_texts`：装载全部语言（维护视图：编辑需见全部语言与停用语言存量值）；
- `replace_i18n` / `replace_i18n_texts`：整体替换某主表行的多语言文案（软删除旧行再插新行，规避唯一冲突）；
- `soft_delete_i18n`：主表删除时连带软删除其附表行（同生命周期，不留孤儿）。

**回退口径**（《数据库设计 · 数据规范》§5）：附表缺某 locale 行（或「去空白后为空」）时，读取侧按
调用方给定的 `locales` 顺序回退——调用方传 `[请求语言, 系统默认语言]` 即为两级回退；两级皆缺时
本模块不返回该键，由调用方回退主表默认文案列（派生快照）。`locale` 比较一律**大小写不敏感**。

为什么在基座：菜单表单、权限元数据、字典数据源等多个业务域都用同一套读写口径，留在任一域都会
造成跨域 import；本模块不含表归属，仅按传入模型操作。
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.session import DbSession

__all__ = [
    "DEFAULT_TEXT_COLUMN",
    "I18nTextMap",
    "load_i18n",
    "load_i18n_all",
    "load_i18n_all_texts",
    "load_i18n_texts",
    "replace_i18n",
    "replace_i18n_texts",
    "soft_delete_i18n",
]

DEFAULT_TEXT_COLUMN = "name"
"""缺省文案列（多数附表的名称列；多列场景显式传 `text_columns`）。"""

I18nTextMap = ConcurrentStableDict[str, str]
"""单行文案映射：文案列 → 文本。"""


def _normalized_locales(locales: Sequence[str]) -> ConcurrentStableList[str]:
    """归一语言优先级序（去空白、去重、小写），保持首现顺序。

    Args:
        locales: 语言标识序列（按回退优先级从高到低）。

    Returns:
        ConcurrentStableList[str]: 小写归一的语言序列。
    """
    result: ConcurrentStableList[str] = ConcurrentStableList()
    seen: set[str] = set()
    for locale in locales:
        key = (locale or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _is_blank(value: object) -> bool:
    """判定文案是否为空（None / 纯空白视为缺失）。

    Args:
        value: 原始列值。

    Returns:
        bool: 缺失为 True。
    """
    if value is None:
        return True
    return not str(value).strip()


async def load_i18n_texts(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_ids: ConcurrentStableList[int],
    *,
    locales: Sequence[str],
    text_columns: Sequence[str] = (DEFAULT_TEXT_COLUMN,),
) -> ConcurrentStableDict[int, I18nTextMap]:
    """按主表 ID 集合与语言优先级装载**多列**文案（每列独立回退）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名（如 `menu_id`）。
        owner_ids: 主表 ID 集合。
        locales: 语言优先级序（从高到低；通常为 `[请求语言, 系统默认语言]`）。
        text_columns: 文案列名序列（如 `("name",)` / `("subject", "content")`）。

    Returns:
        ConcurrentStableDict[int, I18nTextMap]: 主表 ID → （文案列 → 该列优先级最高的非空文本）。
            两级语言均无文案的行不返回，由调用方回退主表默认文案列。
    """
    ordered = _normalized_locales(locales)
    if not owner_ids or not ordered:
        return ConcurrentStableDict()
    priority = {locale: index for index, locale in enumerate(ordered)}
    key_attr = getattr(model, key_column)
    text_attrs = [getattr(model, column) for column in text_columns]
    statement = select(key_attr, model.locale, *text_attrs).where(
        key_attr.in_(list(owner_ids)),
        func.lower(model.locale).in_(list(ordered)),
        model.deleted_at.is_(None),
    )
    rows = (await session.execute(statement)).all()

    best: dict[tuple[int, str], int] = {}
    collected: dict[tuple[int, str], str] = {}
    for row in rows:
        owner_id = int(cast("int", row[0]))
        rank = priority[str(cast("str", row[1])).strip().lower()]
        for index, column in enumerate(text_columns):
            value = row[index + 2]
            if _is_blank(value):
                continue
            slot = (owner_id, column)
            current = best.get(slot)
            if current is not None and current <= rank:
                continue
            best[slot] = rank
            collected[slot] = str(cast("str", value))

    result: ConcurrentStableDict[int, I18nTextMap] = ConcurrentStableDict()
    for (owner_id, column), text in collected.items():
        bucket = result.get(owner_id)
        if bucket is None:
            bucket = ConcurrentStableDict[str, str]()
            result.set(owner_id, bucket)
        bucket.set(column, text)
    return result


async def load_i18n(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_ids: ConcurrentStableList[int],
    *,
    locales: Sequence[str],
    text_column: str = DEFAULT_TEXT_COLUMN,
) -> ConcurrentStableDict[int, str]:
    """按主表 ID 集合与语言优先级装载**单列**文案（两级回退）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名（如 `menu_id`）。
        owner_ids: 主表 ID 集合。
        locales: 语言优先级序（从高到低）。
        text_column: 文案列名（缺省 `name`）。

    Returns:
        ConcurrentStableDict[int, str]: 主表 ID → 该列优先级最高的非空文本。
    """
    texts = await load_i18n_texts(
        session,
        model,
        key_column,
        owner_ids,
        locales=locales,
        text_columns=(text_column,),
    )
    projected: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    for owner_id, bucket in texts.items():
        projected.set(owner_id, bucket[text_column])
    return projected


async def load_i18n_all_texts(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_ids: ConcurrentStableList[int],
    *,
    text_columns: Sequence[str] = (DEFAULT_TEXT_COLUMN,),
) -> ConcurrentStableDict[int, ConcurrentStableDict[str, I18nTextMap]]:
    """按主表 ID 集合装载**全部语言的多列**文案（维护视图用）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名。
        owner_ids: 主表 ID 集合。
        text_columns: 文案列名序列。

    Returns:
        ConcurrentStableDict[int, ConcurrentStableDict[str, I18nTextMap]]:
            主表 ID → （语言标识 → （文案列 → 文本））。
    """
    if not owner_ids:
        return ConcurrentStableDict()
    key_attr = getattr(model, key_column)
    text_attrs = [getattr(model, column) for column in text_columns]
    statement = select(key_attr, model.locale, *text_attrs).where(
        key_attr.in_(list(owner_ids)),
        model.deleted_at.is_(None),
    )
    rows = (await session.execute(statement)).all()
    collected: dict[tuple[int, str, str], str] = {}
    for row in rows:
        owner_id = int(cast("int", row[0]))
        locale = str(cast("str", row[1]))
        for index, column in enumerate(text_columns):
            value = row[index + 2]
            if _is_blank(value):
                continue
            collected[(owner_id, locale, column)] = str(cast("str", value))

    result: ConcurrentStableDict[int, ConcurrentStableDict[str, I18nTextMap]] = ConcurrentStableDict()
    for (owner_id, locale, column), text in collected.items():
        by_locale = result.get(owner_id)
        if by_locale is None:
            by_locale = ConcurrentStableDict[str, I18nTextMap]()
            result.set(owner_id, by_locale)
        bucket = by_locale.get(locale)
        if bucket is None:
            bucket = ConcurrentStableDict[str, str]()
            by_locale.set(locale, bucket)
        bucket.set(column, text)
    return result


async def load_i18n_all(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_ids: ConcurrentStableList[int],
    *,
    text_column: str = DEFAULT_TEXT_COLUMN,
) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
    """按主表 ID 集合装载**全部语言的单列**文案（维护视图用）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名。
        owner_ids: 主表 ID 集合。
        text_column: 文案列名（缺省 `name`）。

    Returns:
        ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 主表 ID → （语言 → 文案）。
    """
    texts = await load_i18n_all_texts(
        session,
        model,
        key_column,
        owner_ids,
        text_columns=(text_column,),
    )
    projected: ConcurrentStableDict[int, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for owner_id, by_locale in texts.items():
        bucket: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for locale, values in by_locale.items():
            bucket.set(locale, values[text_column])
        projected.set(owner_id, bucket)
    return projected


async def replace_i18n_texts(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_id: int,
    texts: Mapping[str, Mapping[str, str]],
    *,
    text_columns: Sequence[str] = (DEFAULT_TEXT_COLUMN,),
) -> None:
    """整体替换某主表行的多语言多列文案（软删除旧行后按语言插新行）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名。
        owner_id: 主表 ID。
        texts: 语言标识 → （文案列 → 文本）；某语言下各列去空白后全为空则跳过该语言。
        text_columns: 文案列名序列（列必须存在于模型）。
    """
    await soft_delete_i18n(session, model, key_column, owner_id)
    for locale, values in texts.items():
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict({key_column: owner_id, "locale": locale})
        for column in text_columns:
            text = (values.get(column) or "").strip()
            if text:
                payload.set(column, text)
        if len(payload) <= 2:
            continue
        session.add(model(**payload))
    await session.flush()


async def replace_i18n(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_id: int,
    names: Mapping[str, str],
    *,
    text_column: str = DEFAULT_TEXT_COLUMN,
) -> None:
    """整体替换某主表行的**单列**多语言文案（软删除旧行后插新行）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名。
        owner_id: 主表 ID。
        names: 语言标识 → 文案。
        text_column: 文案列名（缺省 `name`）。
    """
    texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for locale, name in names.items():
        texts.set(locale, ConcurrentStableDict({text_column: name}))
    await replace_i18n_texts(
        session,
        model,
        key_column,
        owner_id,
        texts,
        text_columns=(text_column,),
    )


async def soft_delete_i18n(
    session: DbSession,
    model: Any,
    key_column: str,
    owner_id: int,
) -> None:
    """软删除某主表行的全部附表行（主表删除时连带清理，同生命周期）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key_column: 主表 ID 列名。
        owner_id: 主表 ID。
    """
    key_attr = getattr(model, key_column)
    statement = select(model).where(key_attr == owner_id, model.deleted_at.is_(None))
    rows = (await session.execute(statement)).scalars().all()
    for row in rows:
        row.soft_delete()
    await session.flush()
