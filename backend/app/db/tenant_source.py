"""租户源：平台库 `sys_tenant` 真实取数、缓存基座短 TTL 与停用强制回收。

- 取数经平台库引擎（`PLATFORM_DB_KEY`）+ 独立短会话；查询过滤软删除（NULL=未删）。
- 缓存经缓存能力域（`CacheRegion`；缺省 null 实现下 get 恒未命中、set 空操作，直查不阻断），
  缓存域 `tenant`、平台数据（key 的租户位取 `global`）；缓存值为普通字典（跨实现可序列化），
  命中的记录同样执行状态判定。
- 停用租户：`status != active` → **强制回收**该租户引擎（`EngineRegistry.release`）后拒绝
  （`TenantSuspendedError`，403 / 80002）；未知租户抛 `TenantNotFoundError`（404 / 80001）。
- `invalidate`：开通 / 停用 / 改名后失效缓存（租户管理阶段写路径接入）。
"""

from typing import Any, cast

from sqlalchemy import select

from app.cache.base import CacheRegion, build_cache_key
from app.core.base import BaseObject
from app.core.exceptions import TenantNotFoundError, TenantSuspendedError
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry
from app.db.session import SessionFactory
from app.db.tenant import TenantContext, build_tenant_db_key
from app.models.platform import SysTenant

__all__ = ["TENANT_CACHE_DOMAIN", "TenantSource"]

TENANT_CACHE_DOMAIN = "tenant"
"""租户注册表缓存域（平台库数据，缓存 key 的租户位取全局）。"""

_ACTIVE_STATUS = "active"
"""租户可用状态（其余状态一律按停用拒绝）。"""


class TenantSource(BaseObject):
    """租户源：按编码 / 子域名取租户上下文（查库 + 缓存 + 停用回收）。"""

    def __init__(
        self,
        registry: EngineRegistry,
        *,
        cache: CacheRegion | None = None,
        session_factory: SessionFactory | None = None,
        cache_ttl: int = 60,
    ) -> None:
        """初始化。

        Args:
            registry: 引擎注册表（经平台库引擎取数）。
            cache: 缓存 Region（缺省 None 表示不缓存、每次直查）。
            session_factory: 会话工厂（缺省 `SessionFactory()`）。
            cache_ttl: 缓存 TTL（秒）。
        """
        self._registry = registry
        self.cache = cache
        self._session_factory = session_factory or SessionFactory()
        self._cache_ttl = cache_ttl

    async def by_code(self, code: str) -> TenantContext:
        """按租户编码取上下文。

        Args:
            code: 租户编码（全小写）。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 租户不存在（404 / 80001）。
            TenantSuspendedError: 租户已停用（403 / 80002）。
        """
        return await self._resolve("code", code)

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取上下文。

        Args:
            domain: 子域名（如 `demo.bms.example.com`）。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 域名未注册租户（404 / 80001）。
            TenantSuspendedError: 租户已停用（403 / 80002）。
        """
        return await self._resolve("domain", domain)

    async def invalidate(self, code: str | None = None, *, domain: str | None = None) -> None:
        """失效缓存（开通 / 停用 / 改名后调用）。

        Args:
            code: 租户编码（失效按编码的缓存项）。
            domain: 子域名（失效按域名的缓存项）。
        """
        if code:
            await self._cache_delete(self._cache_key("code", code))
        if domain:
            await self._cache_delete(self._cache_key("domain", domain))

    async def _resolve(self, kind: str, value: str) -> TenantContext:
        """取数编排：缓存 → 平台库 → 回填 → 状态判定。

        Args:
            kind: `code` / `domain`。
            value: 查询值。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 租户不存在。
            TenantSuspendedError: 租户已停用（含引擎强制回收）。
        """
        key = self._cache_key(kind, value)
        record = await self._cache_get(key)
        if record is None:
            record = await self._load(kind, value)
            if record is None:
                raise TenantNotFoundError(f"未知租户：{value}")
            await self._cache_set(key, record)
        context = _to_context(record)
        if context.status != _ACTIVE_STATUS:
            await self._registry.release(context.db_key)
            raise TenantSuspendedError(f"租户已停用：{context.tenant_code}")
        return context

    async def _load(self, kind: str, value: str) -> dict[str, Any] | None:
        """平台库查询（软删除过滤；未命中返回 None）。"""
        engine = await self._registry.get(PLATFORM_DB_KEY)
        column = SysTenant.code if kind == "code" else SysTenant.domain
        statement = select(SysTenant).where(column == value, SysTenant.deleted_at.is_(None)).limit(1)
        async with self._session_factory.create(engine)() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return None if row is None else _snapshot(row)

    def _cache_key(self, kind: str, value: str) -> str:
        """租户缓存 key（平台数据：key 的租户位取全局）。"""
        return build_cache_key(tenant=None, domain=TENANT_CACHE_DOMAIN, business_key=f"{kind}:{value}")

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        """缓存读取（优先异步方法；无缓存实现返回 None）。"""
        cache = self.cache
        if cache is None:
            return None
        getter = getattr(cache, "aget", None)
        value = await getter(key) if getter is not None else cache.get(key)
        return cast("dict[str, Any] | None", value)

    async def _cache_set(self, key: str, value: dict[str, Any]) -> None:
        """缓存写入（优先异步方法；无缓存实现空操作）。"""
        cache = self.cache
        if cache is None:
            return
        setter = getattr(cache, "aset", None)
        if setter is not None:
            await setter(key, value, self._cache_ttl)
        else:
            cache.set(key, value, self._cache_ttl)

    async def _cache_delete(self, key: str) -> None:
        """缓存删除（优先异步方法；无缓存实现空操作）。"""
        cache = self.cache
        if cache is None:
            return
        deleter = getattr(cache, "adelete", None)
        if deleter is not None:
            await deleter(key)
        else:
            cache.delete(key)


def _snapshot(row: SysTenant) -> dict[str, Any]:
    """注册记录 → 可缓存字典（时间转 ISO 串，跨缓存实现序列化安全）。"""
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "domain": row.domain,
        "db_key": row.db_key or build_tenant_db_key(row.code),
        "status": row.status,
        "expire_at": row.expire_at.isoformat() if row.expire_at else None,
    }


def _to_context(record: dict[str, Any]) -> TenantContext:
    """缓存 / 查询字典 → 租户上下文。"""
    code = str(record["code"])
    tenant_id = record.get("id")
    return TenantContext(
        tenant_code=code,
        db_key=str(record.get("db_key") or build_tenant_db_key(code)),
        name=str(record.get("name") or code),
        tenant_id=int(tenant_id) if tenant_id is not None else None,
        status=str(record.get("status") or _ACTIVE_STATUS),
        domain=cast("str | None", record.get("domain")),
    )
