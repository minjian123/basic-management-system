"""查询方案真实存储（`sys_query_scheme` 落库）：三级作用域 CRUD 与默认解析。

- 契约面见 `app/listing/base.py`（`BaseQuerySchemeStore` / `QueryScheme`，02-4-20 交付）。
- 作用域口径：个人方案（`scope=user`）按当前用户过滤（`current_user_id` 上下文）；租户 / 平台方案全可见；
  默认解析优先级 个人 > 租户 > 平台（同作用域取 `is_default` 首个）。
- 并发：`BaseModel` 乐观锁（`version_id_col`）冲突转 `ConcurrentConflictError`（409 语义）。
- 路由 `/api/v1/query-schemes`（既有占位路由接本实现）；权限码 `dict:query-scheme` / `query:scheme` 随 RBAC 阶段。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import or_, select
from sqlalchemy.orm.exc import StaleDataError

from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ConcurrentConflictError, NotFoundError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.listing.base import BaseQuerySchemeStore, QueryScheme, QuerySchemeScope, QuerySchemeTarget
from bms_core.listing.models import SysQueryScheme

__all__ = ["SqlQuerySchemeStore"]

_SCOPE_PRIORITY: tuple[str, ...] = ("user", "tenant", "platform")
"""默认方案解析优先级。"""


class SqlQuerySchemeStore(BaseQuerySchemeStore):
    """查询方案真实存储（插件名 `sql`；租户库落库）。"""

    def __init__(self, *, engines: EngineRegistry) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
        """
        self._engines = engines

    async def list(
        self,
        target: QuerySchemeTarget,
        *,
        field_key: str | None = None,
    ) -> tuple[QueryScheme, ...]:
        """列查询方案（个人方案按当前用户过滤）。

        Args:
            target: 方案目标。
            field_key: 表单标识（列表筛选维度；可选）。

        Returns:
            tuple[QueryScheme, ...]: 方案元组（默认方案优先、更新时间倒序）。
        """
        stmt = select(SysQueryScheme).where(
            SysQueryScheme.target == target.value,
            SysQueryScheme.status == "enabled",
            SysQueryScheme.deleted_at.is_(None),
        )
        if field_key is not None:
            stmt = stmt.where(SysQueryScheme.field_key == field_key)
        user_id = current_user_id.get()
        stmt = stmt.where(or_(SysQueryScheme.scope != "user", SysQueryScheme.owner_id == user_id))
        stmt = stmt.order_by(SysQueryScheme.is_default.desc(), SysQueryScheme.updated_at.desc())
        async with self._session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        return tuple(_to_scheme(row) for row in rows)

    async def get(self, scheme_id: int) -> QueryScheme | None:
        """取单个方案（未命中返回 None）。

        Args:
            scheme_id: 方案 ID。

        Returns:
            QueryScheme | None: 方案；未命中为 None。
        """
        async with self._session() as session:
            row = await session.get(SysQueryScheme, scheme_id)
            if row is None or row.deleted_at is not None:
                return None
            return _to_scheme(row)

    async def save(self, scheme: QueryScheme) -> QueryScheme:
        """保存 / 更新方案（`id` 为空表示新建；乐观锁冲突转 409 语义）。

        Args:
            scheme: 方案数据。

        Returns:
            QueryScheme: 落库后的方案。

        Raises:
            NotFoundError: 更新目标不存在。
            ConcurrentConflictError: 乐观锁冲突。
        """
        async with self._session() as session:
            try:
                if scheme.id is None:
                    row = SysQueryScheme(
                        name=scheme.name,
                        scope=scheme.scope.value,
                        owner_id=scheme.owner_id if scheme.owner_id is not None else current_user_id.get(),
                        target=scheme.target.value,
                        dict_type=scheme.dict_type,
                        field_key=scheme.field_key,
                        provider_key=scheme.provider_key,
                        conditions=scheme.conditions,
                        params=scheme.params,
                        layout=scheme.layout,
                        is_default=scheme.is_default,
                        shared=scheme.shared,
                        status=scheme.status,
                    )
                    session.add(row)
                    await session.commit()
                    await session.refresh(row)
                    return _to_scheme(row)
                row = await session.get(SysQueryScheme, scheme.id)
                if row is None or row.deleted_at is not None:
                    raise NotFoundError(f"查询方案不存在：{scheme.id}")
                row.name = scheme.name
                row.scope = scheme.scope.value
                row.owner_id = scheme.owner_id
                row.target = scheme.target.value
                row.dict_type = scheme.dict_type
                row.field_key = scheme.field_key
                row.provider_key = scheme.provider_key
                row.conditions = scheme.conditions
                row.params = scheme.params
                row.layout = scheme.layout
                row.is_default = scheme.is_default
                row.shared = scheme.shared
                row.status = scheme.status
                await session.commit()
                await session.refresh(row)
                return _to_scheme(row)
            except StaleDataError as exc:
                raise ConcurrentConflictError("查询方案已被修改，请刷新后重试") from exc

    async def delete(self, scheme_id: int) -> bool:
        """软删除方案。

        Args:
            scheme_id: 方案 ID。

        Returns:
            bool: 删到为 True。
        """
        async with self._session() as session:
            row = await session.get(SysQueryScheme, scheme_id)
            if row is None or row.deleted_at is not None:
                return False
            row.soft_delete()
            await session.commit()
            return True

    async def resolve_default(
        self,
        target: QuerySchemeTarget,
        *,
        field_key: str | None = None,
    ) -> QueryScheme | None:
        """按三级优先级（个人 > 租户 > 平台）解析默认方案。

        Args:
            target: 方案目标。
            field_key: 表单标识（列表筛选维度；可选）。

        Returns:
            QueryScheme | None: 命中最高优先级的默认方案；无则 None。
        """
        user_id = current_user_id.get()
        async with self._session() as session:
            for scope in _SCOPE_PRIORITY:
                stmt = select(SysQueryScheme).where(
                    SysQueryScheme.target == target.value,
                    SysQueryScheme.scope == scope,
                    SysQueryScheme.is_default.is_(True),
                    SysQueryScheme.status == "enabled",
                    SysQueryScheme.deleted_at.is_(None),
                )
                if field_key is not None:
                    stmt = stmt.where(SysQueryScheme.field_key == field_key)
                if scope == "user":
                    stmt = stmt.where(SysQueryScheme.owner_id == user_id)
                stmt = stmt.order_by(SysQueryScheme.updated_at.desc()).limit(1)
                row = (await session.execute(stmt)).scalars().first()
                if row is not None:
                    return _to_scheme(row)
        return None

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话（异步会话，或同步方言下的同步门面）。
        """
        async with session_scope(self._engines) as session:
            yield session


def _to_scheme(row: SysQueryScheme) -> QueryScheme:
    """ORM 行 → 查询方案契约。

    Args:
        row: ORM 行。

    Returns:
        QueryScheme: 方案数据契约。
    """
    try:
        scope = QuerySchemeScope(row.scope)
    except ValueError:
        scope = QuerySchemeScope.USER
    return QueryScheme(
        id=row.id,
        name=row.name,
        scope=scope,
        owner_id=row.owner_id,
        target=QuerySchemeTarget(row.target),
        dict_type=row.dict_type,
        field_key=row.field_key,
        provider_key=row.provider_key,
        conditions=dict(row.conditions) if row.conditions is not None else None,
        params=dict(row.params) if row.params is not None else None,
        layout=dict(row.layout) if row.layout is not None else None,
        is_default=row.is_default,
        shared=row.shared,
        status=row.status,
    )
