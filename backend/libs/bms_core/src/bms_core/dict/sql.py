"""字典真实取数与翻译（`app/dict/`）：SQLite 实测、四库兼容编写。

- `SqlDictSource`：`by_type`（版本比对三态 / 关键字 / 级联父值 / 按值子集 / 探针截断 / locale 回退）与
  `batch`（多类型合并、逐类型探针）；缓存两层（Redis 共享层 + 进程内 L1）经 `DictCacheRegion`。
- `SqlDictTranslator`：与取数共用同一份缓存；子集命中直出、缺失一次 `IN` 回填（防 N+1）；未命中不占位。
- 租户：实现侧从上下文解析（`current_tenant`，缺省 demo）并经 `EngineRegistry` 取租户库引擎；调用方不传租户。
- locale：`by_type` 从 `current_dict_locale` 上下文解析（路由层按 `Accept-Language` 设置）；批量 / 翻译显式入参。
- 降级：缓存异常由 Region 内部兜底（按未命中）；DB 异常抛字典错误码 `40101`；类型不存在 `40102`；语言不支持 `40103`。
"""

import asyncio
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import cast
from uuid import uuid4

from sqlalchemy import ColumnElement, and_, func, or_, select

from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import BizError
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_context
from bms_core.dict.base import (
    DICT_PROBE_LIMIT,
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictCacheRegion,
    DictItem,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
)
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.models import SysDictItem, SysDictItemI18n, SysDictType
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES

__all__ = ["SqlDictSource", "SqlDictTranslator", "current_dict_locale"]

_LOGGER = get_logger("bms")

current_dict_locale: ContextVar[str] = ContextVar("current_dict_locale", default=DEFAULT_LOCALE)
"""当前请求语言（路由层按 `Accept-Language` 解析后设置；缺省 `zh-CN`）。"""

LOCK_TTL_SECONDS = 5
"""类型取数互斥锁有效期（秒）。"""

LOCK_WAIT_SECONDS = 0.05
"""未获锁短暂等待（秒）后重读缓存，仍无则回源（防击穿）。"""


class SqlDictSource(BaseDictSource):
    """真实字典取数（插件名 `sql`）：租户库查询 + 两层缓存。"""

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        cache: DictCacheRegion | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表（按租户库键取引擎）。
            cache: 字典缓存域（缺省进程内实现；装配侧注入配置选定的实现）。
        """
        self._engines = engines
        self._cache = cache or MemoryDictCacheRegion()

    @property
    def cache(self) -> DictCacheRegion:
        """字典缓存域（供测试与登记核对）。

        Returns:
            DictCacheRegion: 缓存域实例。
        """
        return self._cache

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按类型取字典（版本比对 / 关键字 / 级联 / 按值子集 / 条数上限）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果（版本一致时 `items=None`）。

        Raises:
            BizError: 40102 类型不存在 / 40103 语言不支持 / 40101 数据源不可用。
        """
        locale = _current_locale()
        tenant = current_tenant_context().tenant_code
        version = await self._cache.aversion(tenant)
        if query.version is not None and query.version == version:
            return DictTypeResult(version=version, items=None)
        filtered = _is_filtered(query)
        cacheable_read = not filtered and query.limit is None
        if cacheable_read:
            snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, query.dict_type), version)
            if snapshot is not None:
                return snapshot
        token = uuid4().hex
        locked = await self._cache.alock(tenant, locale, query.dict_type, token, LOCK_TTL_SECONDS)
        if not locked:
            await asyncio.sleep(LOCK_WAIT_SECONDS)
            if cacheable_read:
                snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, query.dict_type), version)
                if snapshot is not None:
                    return snapshot
        try:
            items, total, has_more = await self._load_type_page(query, locale)
        finally:
            if locked:
                await self._cache.arelease_lock(tenant, locale, query.dict_type, token)
        result = DictTypeResult(version=version, items=tuple(items), has_more=has_more, total=total)
        cacheable_write = not filtered and (query.limit is None or not has_more)
        if cacheable_write:
            await self._cache.aset_type(tenant, locale, query.dict_type, _snapshot_payload(result))
        return result

    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        """批量合并取字典（一次请求多类型，表单页多字段合并）。

        Args:
            query: 批量取数参数对象。

        Returns:
            DictBatchResult: 批量结果（版本一致的类型 `items=None`）。

        Raises:
            BizError: 40103 语言不支持 / 40101 数据源不可用。
        """
        locale = query.locale or DEFAULT_LOCALE
        _ensure_supported_locale(locale)
        types = list(dict.fromkeys(query.types))
        tenant = current_tenant_context().tenant_code
        version = await self._cache.aversion(tenant)
        results: dict[str, DictTypeResult | None] = {}
        pending: list[str] = []
        for name in types:
            if query.version is not None and query.version == version:
                results[name] = None
                continue
            snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, name), version)
            if snapshot is not None:
                results[name] = snapshot
            else:
                pending.append(name)
        if pending:
            pages = await self._load_batch_pages(pending, locale)
            for name in pending:
                items, total = pages.get(name, ([], 0))
                has_more = len(items) > DICT_PROBE_LIMIT
                trimmed = items[:DICT_PROBE_LIMIT]
                result = DictTypeResult(version=version, items=tuple(trimmed), has_more=has_more, total=total)
                results[name] = result
                await self._cache.aset_type(tenant, locale, name, _snapshot_payload(result))
        return DictBatchResult(version=version, items=results)

    async def _load_type_page(
        self,
        query: DictQuery,
        locale: str,
    ) -> tuple[list[DictItem], int, bool]:
        """查租户库单类型页（类型存在性校验 + 探针截断）。

        Args:
            query: 单类型取数参数。
            locale: 语言。

        Returns:
            tuple[list[DictItem], int, bool]: 条目 / 总数 / 是否截断。

        Raises:
            BizError: 40102 类型不存在 / 40101 数据源不可用。
        """
        try:
            async with self._session() as session:
                type_row = await _load_type(session, query.dict_type)
                if type_row is None:
                    raise BizError(ErrorCode.DICT_TYPE_NOT_FOUND, f"字典类型不存在：{query.dict_type}", http_status=404)
                return await _query_page(session, type_row.id, locale, query)
        except BizError:
            raise
        except Exception as exc:
            _LOGGER.warning("字典取数失败", scope="by_type", dict_type=query.dict_type, error=repr(exc))
            raise BizError(ErrorCode.DICT_SOURCE_UNAVAILABLE, "字典数据源不可用", http_status=503) from exc

    async def _load_batch_pages(
        self,
        types: Sequence[str],
        locale: str,
    ) -> dict[str, tuple[list[DictItem], int]]:
        """批量查租户库（一次查询按类型分组）。

        Args:
            types: 字典类型码序列。
            locale: 语言。

        Returns:
            dict[str, tuple[list[DictItem], int]]: 类型 → (条目, 总数)。

        Raises:
            BizError: 40101 数据源不可用。
        """
        try:
            async with self._session() as session:
                return await _query_batch(session, types, locale)
        except BizError:
            raise
        except Exception as exc:
            raise BizError(ErrorCode.DICT_SOURCE_UNAVAILABLE, "字典数据源不可用", http_status=503) from exc

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话（异步会话，或同步方言下的同步门面）。
        """
        async with session_scope(self._engines) as session:
            yield session


class SqlDictTranslator(BaseDictTranslator):
    """真实字典翻译（插件名 `sql`）：与取数共用同一份缓存，缺失一次 `IN` 回填。"""

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        cache: DictCacheRegion | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
            cache: 字典缓存域（与取数共用同一实例；缺省进程内实现）。
        """
        self._engines = engines
        self._cache = cache or MemoryDictCacheRegion()

    async def translate(self, query: DictTranslateQuery) -> Mapping[str, str]:
        """按 value 批量翻译为 label（当前 locale；未命中不占位）。

        Args:
            query: 翻译参数对象。

        Returns:
            Mapping[str, str]: value → label（仅命中项）。

        Raises:
            BizError: 40103 语言不支持 / 40101 数据源不可用。
        """
        locale = query.locale or DEFAULT_LOCALE
        _ensure_supported_locale(locale)
        values = list(dict.fromkeys(query.values))
        if not values:
            return {}
        tenant = current_tenant_context().tenant_code
        cached = await self._cache.avalue_subset(tenant, locale, query.dict_type, values)
        missing = [value for value in values if value not in cached]
        if missing:
            loaded = await self._load_labels(query.dict_type, locale, missing)
            if loaded:
                await self._cache.aset_value_subset(tenant, locale, query.dict_type, loaded)
            cached = {**cached, **loaded}
        return {value: cached[value] for value in values if value in cached}

    async def _load_labels(self, dict_type: str, locale: str, values: Sequence[str]) -> dict[str, str]:
        """查租户库缺失 value 的 label（一次 `IN`）。

        Args:
            dict_type: 字典类型码。
            locale: 语言。
            values: 缺失 value 序列。

        Returns:
            dict[str, str]: value → label。

        Raises:
            BizError: 40101 数据源不可用。
        """
        try:
            async with self._session() as session:
                type_row = await _load_type(session, dict_type)
                if type_row is None:
                    return {}
                return await _query_labels(session, type_row.id, locale, values)
        except BizError:
            raise
        except Exception as exc:
            raise BizError(ErrorCode.DICT_SOURCE_UNAVAILABLE, "字典数据源不可用", http_status=503) from exc

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话（异步会话，或同步方言下的同步门面）。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _load_type(session: DbSession, dict_type: str) -> SysDictType | None:
    """按类型码取启用类型。

    Args:
        session: 租户库会话。
        dict_type: 字典类型码。

    Returns:
        SysDictType | None: 类型行；不存在 / 停用 / 已删返回 None。
    """
    stmt = select(SysDictType).where(
        SysDictType.type == dict_type,
        SysDictType.status == "enabled",
        SysDictType.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _query_page(
    session: DbSession,
    type_id: int,
    locale: str,
    query: DictQuery,
) -> tuple[list[DictItem], int, bool]:
    """单类型条目页查询（`COUNT` + 页查询 + 探针截断）。

    Args:
        session: 租户库会话。
        type_id: 类型 ID。
        locale: 语言。
        query: 单类型取数参数。

    Returns:
        tuple[list[DictItem], int, bool]: 条目 / 总数 / 是否截断。
    """
    conditions = _item_conditions(type_id, query)
    total = int((await session.execute(select(func.count()).select_from(SysDictItem).where(*conditions))).scalar_one())
    stmt = (
        select(SysDictItem, SysDictItemI18n.label)
        .outerjoin(
            SysDictItemI18n,
            and_(SysDictItemI18n.dict_item_id == SysDictItem.id, SysDictItemI18n.locale == locale),
        )
        .where(*conditions)
        .order_by(SysDictItem.sort, SysDictItem.id)
    )
    limit = query.limit
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    has_more = False
    if limit is not None and limit > 0 and len(rows) > limit:
        has_more = True
        rows = rows[:limit]
    items = [_to_item(item, i18n_label) for item, i18n_label in rows]
    return items, total, has_more


async def _query_batch(
    session: DbSession,
    types: Sequence[str],
    locale: str,
) -> dict[str, tuple[list[DictItem], int]]:
    """多类型条目查询（一次类型查询 + 一次条目查询，按类型分组）。

    Args:
        session: 租户库会话。
        types: 字典类型码序列。
        locale: 语言。

    Returns:
        dict[str, tuple[list[DictItem], int]]: 类型 → (条目, 总数)。
    """
    stmt_types = select(SysDictType).where(
        SysDictType.type.in_(tuple(types)),
        SysDictType.status == "enabled",
        SysDictType.deleted_at.is_(None),
    )
    type_rows = list((await session.execute(stmt_types)).scalars().all())
    if not type_rows:
        return {}
    id_to_type = {row.id: row.type for row in type_rows}
    type_ids = tuple(id_to_type.keys())
    conditions: list[ColumnElement[bool]] = [
        SysDictItem.type_id.in_(type_ids),
        SysDictItem.status == "enabled",
        SysDictItem.deleted_at.is_(None),
    ]
    stmt = (
        select(SysDictItem, SysDictItemI18n.label)
        .outerjoin(
            SysDictItemI18n,
            and_(SysDictItemI18n.dict_item_id == SysDictItem.id, SysDictItemI18n.locale == locale),
        )
        .where(*conditions)
        .order_by(SysDictItem.type_id, SysDictItem.sort, SysDictItem.id)
    )
    rows = (await session.execute(stmt)).all()
    pages: dict[str, tuple[list[DictItem], int]] = {name: ([], 0) for name in types}
    for item, i18n_label in rows:
        name = id_to_type.get(item.type_id)
        if name is None:
            continue
        items, total = pages[name]
        items.append(_to_item(item, i18n_label))
        pages[name] = (items, total + 1)
    return pages


async def _query_labels(
    session: DbSession,
    type_id: int,
    locale: str,
    values: Sequence[str],
) -> dict[str, str]:
    """按 value 子集查 label（一次 `IN`，防 N+1）。

    Args:
        session: 租户库会话。
        type_id: 类型 ID。
        locale: 语言。
        values: value 序列。

    Returns:
        dict[str, str]: value → label（仅命中项）。
    """
    stmt = (
        select(SysDictItem.value, SysDictItem.label, SysDictItemI18n.label)
        .outerjoin(
            SysDictItemI18n,
            and_(SysDictItemI18n.dict_item_id == SysDictItem.id, SysDictItemI18n.locale == locale),
        )
        .where(
            SysDictItem.type_id == type_id,
            SysDictItem.value.in_(tuple(values)),
            SysDictItem.status == "enabled",
            SysDictItem.deleted_at.is_(None),
        )
    )
    rows = (await session.execute(stmt)).all()
    result: dict[str, str] = {}
    for value, label, i18n_label in rows:
        result[str(value)] = str(i18n_label or label)
    return result


def _item_conditions(type_id: int, query: DictQuery) -> list[ColumnElement[bool]]:
    """构造条目过滤条件（状态 / 删除 / 关键字 / 按值子集 / 级联父值）。

    Args:
        type_id: 类型 ID。
        query: 单类型取数参数。

    Returns:
        list[ColumnElement[bool]]: SQLAlchemy 条件列表。
    """
    conditions: list[ColumnElement[bool]] = [
        SysDictItem.type_id == type_id,
        SysDictItem.status == "enabled",
        SysDictItem.deleted_at.is_(None),
    ]
    keyword = (query.keyword or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        conditions.append(
            or_(
                SysDictItem.label.like(pattern),
                SysDictItem.value.like(pattern),
                SysDictItem.code.like(pattern),
            )
        )
    if query.values:
        conditions.append(SysDictItem.value.in_(tuple(query.values)))
    if query.parent_id is not None:
        if query.parent_id == "":
            conditions.append(SysDictItem.parent_id.is_(None))
        else:
            conditions.append(SysDictItem.parent_id == query.parent_id)
    return conditions


def _to_item(item: SysDictItem, i18n_label: str | None) -> DictItem:
    """ORM 条目 → 结果契约（label 按 locale 命中优先）。

    Args:
        item: ORM 条目。
        i18n_label: i18n 附表 label（可空）。

    Returns:
        DictItem: 结果条目。
    """
    return DictItem(
        value=item.value,
        label=str(i18n_label or item.label),
        code=item.code,
        parent_id=item.parent_id,
        sort=item.sort,
        status=item.status,
        color=item.color,
    )


def _current_locale() -> str:
    """取当前语言并校验支持清单。

    Returns:
        str: 语言。

    Raises:
        BizError: 40103 语言不支持。
    """
    locale = current_dict_locale.get() or DEFAULT_LOCALE
    _ensure_supported_locale(locale)
    return locale


def _ensure_supported_locale(locale: str) -> None:
    """校验语言在支持清单内。

    Args:
        locale: 语言。

    Raises:
        BizError: 40103 语言不支持。
    """
    if locale not in SUPPORTED_LOCALES:
        raise BizError(ErrorCode.DICT_LOCALE_UNSUPPORTED, f"不支持的语言：{locale}", http_status=400)


def _is_filtered(query: DictQuery) -> bool:
    """是否带过滤条件（带过滤不写整类型缓存）。

    Args:
        query: 单类型取数参数。

    Returns:
        bool: 带过滤为 True。
    """
    return bool((query.keyword or "").strip()) or bool(query.values) or query.parent_id is not None


def _snapshot_payload(result: DictTypeResult) -> dict[str, object]:
    """结果 → 缓存载荷（JSON 友好）。

    Args:
        result: 取数结果。

    Returns:
        dict[str, object]: 缓存载荷。
    """
    items = result.items or ()
    return {
        "version": result.version,
        "items": [
            {
                "value": item.value,
                "label": item.label,
                "code": item.code,
                "parent_id": item.parent_id,
                "sort": item.sort,
                "status": item.status,
                "color": item.color,
            }
            for item in items
        ],
        "has_more": result.has_more,
        "total": result.total,
    }


def _cache_snapshot(cached: object, version: int) -> DictTypeResult | None:
    """缓存载荷 → 结果（版本一致才命中）。

    Args:
        cached: 缓存载荷。
        version: 当前全局版本号。

    Returns:
        DictTypeResult | None: 命中结果；不一致 / 非法载荷返回 None。
    """
    if not isinstance(cached, Mapping):
        return None
    payload = cast("Mapping[str, object]", cached)
    if payload.get("version") != version:
        return None
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return None
    items: list[DictItem] = []
    for raw in cast("list[object]", raw_items):
        if not isinstance(raw, Mapping):
            return None
        row = cast("Mapping[str, object]", raw)
        parent_id = row.get("parent_id")
        color = row.get("color")
        items.append(
            DictItem(
                value=_as_str(row.get("value")),
                label=_as_str(row.get("label")),
                code=_as_str(row.get("code")),
                parent_id=None if parent_id is None else _as_str(parent_id),
                sort=_as_int(row.get("sort")),
                status=_as_str(row.get("status"), "enabled"),
                color=None if color is None else _as_str(color),
            )
        )
    return DictTypeResult(
        version=version,
        items=tuple(items),
        has_more=payload.get("has_more") is True,
        total=_as_int(payload.get("total"), len(items)),
    )


def _as_str(value: object, default: str = "") -> str:
    """把缓存载荷值转字符串（非字符串回落默认）。

    Args:
        value: 原始值。
        default: 默认值。

    Returns:
        str: 字符串值。
    """
    return value if isinstance(value, str) else default


def _as_int(value: object, default: int = 0) -> int:
    """把缓存载荷值转整数（非整数回落默认）。

    Args:
        value: 原始值。
        default: 默认值。

    Returns:
        int: 整数值。
    """
    return value if isinstance(value, int) else default
