"""字典写路径服务：类型 / 条目 / 属性 CRUD + 写库后失效（删缓存 + `INCR` 版本）。

- 顺序：**先写库（提交）后删缓存 + 版本递增**（与《概要设计 · 字典管理》写路径一致）。
- 唯一性：类型 `type` 与条目 `(type_id, code)` 未删除行唯一（服务层校验 + DB 复合唯一兜底）；
  软删除后重建同 type / code 放行（复合唯一含 `deleted_at`）。
- 并发：乐观锁冲突转 `ConcurrentConflictError`（409 语义）；类型 / 条目不存在抛 `NotFoundError`。
- 权限码（`dict:manage`）由上层声明；本服务只做数据与缓存失效。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ConcurrentConflictError, ConflictError, NotFoundError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_context
from bms_core.dict.base import DictCacheRegion
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.models import SysDictAttr, SysDictItem, SysDictType
from bms_core.i18n.base import SUPPORTED_LOCALES
from bms_core.schemas.base import BaseSchema

__all__ = [
    "DictAttrPayload",
    "DictItemPayload",
    "DictService",
    "DictTypePayload",
]


class DictTypePayload(BaseSchema):
    """字典类型写入载荷。"""

    type: str = Field(description="类型编码（唯一）")
    name: str = Field(description="类型名称（默认语言）")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态（enabled/disabled）")


class DictItemPayload(BaseSchema):
    """字典条目写入载荷。"""

    code: str = Field(description="条目编码（类型内唯一）")
    label: str = Field(description="条目标签（默认语言）")
    value: str = Field(description="条目值")
    parent_id: str | None = Field(default=None, description="级联父值")
    attr_json: dict[str, object] | None = Field(default=None, description="扩展属性值（普通链路不返回）")
    color: str | None = Field(default=None, description="语义色")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态（enabled/disabled）")


class DictAttrPayload(BaseSchema):
    """字典扩展属性写入载荷。"""

    attr_key: str = Field(description="属性键")
    name: str = Field(description="属性名（默认语言）")
    data_type: str = Field(description="数据类型（text/number/date/enum/bool）")
    operators: tuple[str, ...] | None = Field(default=None, description="可用操作符集合")
    widget: str | None = Field(default=None, description="值控件")
    options: tuple[dict[str, object], ...] | None = Field(default=None, description="enum 选项集")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态（enabled/disabled）")
    scope: str = Field(default="platform", description="属性来源（platform/tenant）")


class DictService(BaseObject):
    """字典写路径服务（CRUD + 失效）。"""

    def __init__(self, *, engines: EngineRegistry, cache: DictCacheRegion | None = None) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
            cache: 字典缓存域（失效用；缺省进程内实现）。
        """
        self._engines = engines
        self._cache = cache or MemoryDictCacheRegion()

    async def create_type(self, payload: DictTypePayload) -> SysDictType:
        """新增字典类型。

        Args:
            payload: 类型载荷。

        Returns:
            SysDictType: 落库后的类型行。

        Raises:
            ConflictError: 类型编码已存在。
        """
        async with self._session() as session:
            existing = await _find_type_by_code(session, payload.type)
            if existing is not None:
                raise ConflictError(f"字典类型已存在：{payload.type}")
            row = SysDictType(
                type=payload.type,
                name=payload.name,
                sort=payload.sort,
                status=payload.status,
            )
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
        await self.invalidate(payload.type)
        return row

    async def update_type(self, type_id: int, payload: DictTypePayload) -> SysDictType:
        """修改字典类型。

        Args:
            type_id: 类型 ID。
            payload: 类型载荷。

        Returns:
            SysDictType: 落库后的类型行。

        Raises:
            NotFoundError: 类型不存在。
            ConflictError: 类型编码与其他类型重复。
        """
        async with self._session() as session:
            row = await _get_type(session, type_id)
            if row is None:
                raise NotFoundError(f"字典类型不存在：{type_id}")
            if payload.type != row.type:
                duplicated = await _find_type_by_code(session, payload.type)
                if duplicated is not None and duplicated.id != type_id:
                    raise ConflictError(f"字典类型已存在：{payload.type}")
            row.type = payload.type
            row.name = payload.name
            row.sort = payload.sort
            row.status = payload.status
            await self._commit(session)
            await session.refresh(row)
        await self.invalidate(row.type)
        return row

    async def delete_type(self, type_id: int) -> None:
        """软删除字典类型。

        Args:
            type_id: 类型 ID。

        Raises:
            NotFoundError: 类型不存在。
        """
        async with self._session() as session:
            row = await _get_type(session, type_id)
            if row is None:
                raise NotFoundError(f"字典类型不存在：{type_id}")
            row.soft_delete()
            await self._commit(session)
            dict_type = row.type
        await self.invalidate(dict_type)

    async def create_item(self, dict_type: str, payload: DictItemPayload) -> SysDictItem:
        """新增字典条目。

        Args:
            dict_type: 字典类型码。
            payload: 条目载荷。

        Returns:
            SysDictItem: 落库后的条目行。

        Raises:
            NotFoundError: 类型不存在。
            ConflictError: 条目编码已存在。
        """
        async with self._session() as session:
            type_row = await _find_type_by_code(session, dict_type)
            if type_row is None:
                raise NotFoundError(f"字典类型不存在：{dict_type}")
            existing = await _find_item_by_code(session, type_row.id, payload.code)
            if existing is not None:
                raise ConflictError(f"字典条目编码已存在：{payload.code}")
            row = SysDictItem(
                type_id=type_row.id,
                code=payload.code,
                label=payload.label,
                value=payload.value,
                parent_id=payload.parent_id,
                attr_json=payload.attr_json,
                color=payload.color,
                sort=payload.sort,
                status=payload.status,
            )
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
        await self.invalidate(dict_type)
        return row

    async def update_item(self, item_id: int, payload: DictItemPayload) -> SysDictItem:
        """修改字典条目。

        Args:
            item_id: 条目 ID。
            payload: 条目载荷。

        Returns:
            SysDictItem: 落库后的条目行。

        Raises:
            NotFoundError: 条目不存在。
            ConflictError: 条目编码与同类型其他条目重复。
        """
        async with self._session() as session:
            row = await session.get(SysDictItem, item_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(f"字典条目不存在：{item_id}")
            if payload.code != row.code:
                duplicated = await _find_item_by_code(session, row.type_id, payload.code)
                if duplicated is not None and duplicated.id != item_id:
                    raise ConflictError(f"字典条目编码已存在：{payload.code}")
            row.code = payload.code
            row.label = payload.label
            row.value = payload.value
            row.parent_id = payload.parent_id
            row.attr_json = payload.attr_json
            row.color = payload.color
            row.sort = payload.sort
            row.status = payload.status
            await self._commit(session)
            await session.refresh(row)
            type_row = await _get_type(session, row.type_id)
            dict_type = type_row.type if type_row is not None else ""
        if dict_type:
            await self.invalidate(dict_type)
        return row

    async def delete_item(self, item_id: int) -> None:
        """软删除字典条目。

        Args:
            item_id: 条目 ID。

        Raises:
            NotFoundError: 条目不存在。
        """
        async with self._session() as session:
            row = await session.get(SysDictItem, item_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(f"字典条目不存在：{item_id}")
            row.soft_delete()
            await self._commit(session)
            type_row = await _get_type(session, row.type_id)
            dict_type = type_row.type if type_row is not None else ""
        if dict_type:
            await self.invalidate(dict_type)

    async def upsert_attr(self, dict_type: str, payload: DictAttrPayload) -> SysDictAttr:
        """新增 / 更新字典扩展属性（按 `(type_id, attr_key)` 判存）。

        Args:
            dict_type: 字典类型码。
            payload: 属性载荷。

        Returns:
            SysDictAttr: 落库后的属性行。

        Raises:
            NotFoundError: 类型不存在。
        """
        async with self._session() as session:
            type_row = await _find_type_by_code(session, dict_type)
            if type_row is None:
                raise NotFoundError(f"字典类型不存在：{dict_type}")
            stmt = select(SysDictAttr).where(
                SysDictAttr.type_id == type_row.id,
                SysDictAttr.attr_key == payload.attr_key,
                SysDictAttr.deleted_at.is_(None),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = SysDictAttr(type_id=type_row.id, attr_key=payload.attr_key)
                session.add(row)
            row.name = payload.name
            row.data_type = payload.data_type
            row.operators = list(payload.operators) if payload.operators is not None else None
            row.widget = payload.widget
            row.options = [dict(item) for item in payload.options] if payload.options is not None else None
            row.sort = payload.sort
            row.status = payload.status
            row.scope = payload.scope
            await self._commit(session)
            await session.refresh(row)
        return row

    async def delete_attr(self, attr_id: int) -> None:
        """软删除字典扩展属性。

        Args:
            attr_id: 属性 ID。

        Raises:
            NotFoundError: 属性不存在。
        """
        async with self._session() as session:
            row = await session.get(SysDictAttr, attr_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError(f"字典属性不存在：{attr_id}")
            row.soft_delete()
            await self._commit(session)

    async def invalidate(self, dict_type: str) -> None:
        """失效字典缓存：删各 locale 类型 key 与子集 key，并递增全局版本（跨实例失效）。

        Args:
            dict_type: 字典类型码。
        """
        tenant = current_tenant_context().tenant_code
        for locale in SUPPORTED_LOCALES:
            await self._cache.adrop_type(tenant, locale, dict_type)
            self._cache.delete(self._cache.value_key(tenant, locale, dict_type))
        await self._cache.aincrease_version(tenant)

    async def _commit(self, session: DbSession) -> None:
        """提交（乐观锁冲突转 409 语义）。

        Args:
            session: 租户库会话。

        Raises:
            ConcurrentConflictError: 乐观锁冲突。
        """
        try:
            await session.commit()
        except StaleDataError as exc:
            raise ConcurrentConflictError("字典数据已被修改，请刷新后重试") from exc

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话（异步会话，或同步方言下的同步门面）。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _get_type(session: DbSession, type_id: int) -> SysDictType | None:
    """按 ID 取未删除类型。

    Args:
        session: 租户库会话。
        type_id: 类型 ID。

    Returns:
        SysDictType | None: 类型行；不存在 / 已删返回 None。
    """
    row = await session.get(SysDictType, type_id)
    if row is None or row.deleted_at is not None:
        return None
    return row


async def _find_type_by_code(session: DbSession, dict_type: str) -> SysDictType | None:
    """按类型码取未删除类型。

    Args:
        session: 租户库会话。
        dict_type: 类型编码。

    Returns:
        SysDictType | None: 类型行；不存在 / 已删返回 None。
    """
    stmt = select(SysDictType).where(SysDictType.type == dict_type, SysDictType.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def _find_item_by_code(session: DbSession, type_id: int, code: str) -> SysDictItem | None:
    """按类型 + 编码取未删除条目。

    Args:
        session: 租户库会话。
        type_id: 类型 ID。
        code: 条目编码。

    Returns:
        SysDictItem | None: 条目行；不存在 / 已删返回 None。
    """
    stmt = select(SysDictItem).where(
        SysDictItem.type_id == type_id,
        SysDictItem.code == code,
        SysDictItem.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()
