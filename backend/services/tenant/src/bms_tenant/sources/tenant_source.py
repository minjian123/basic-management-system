"""本地租户源：租户与配置服务直读自身平台服务库 `sys_tenant`（06_03 由共享基座库迁入实现）。

- 数据所有权：本服务是 `sys_tenant` 的**唯一写方**；其他服务经租户注册只读契约取数（`RemoteTenantSource`）。
- 缓存：域 `tenant`（平台数据），载荷带全局版本戳 `bms:global:tenant:version`；写路径 `bump_version()`
  使各消费方惰性重载（与字典版本键同模式）。
- 口径：`CacheRegion` 契约无原子自增，`bump_version` 以「读当前版本 + 1 后写回」实现（写方唯一、
  写路径串行；Redis 原生 INCR 待缓存基座扩展，见实施记录偏差）。
"""

from collections.abc import Mapping
from typing import cast

from sqlalchemy import select

from bms_core.cache.base import CacheRegion
from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import TenantNotFoundError, TenantSuspendedError
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.db.tenant import TenantContext
from bms_core.db.tenant_registry import (
    ACTIVE_STATUS,
    TENANT_VERSION_KEY,
    TenantSnapshot,
    snapshot_cache_key,
    to_tenant_context,
)
from bms_core.db.tenant_source import register_tenant_lookup
from bms_tenant.models.tenant import SysTenant

__all__ = ["LOCAL_TENANT_SOURCE", "LocalTenantSource", "register_local_tenant_source"]

LOCAL_TENANT_SOURCE = "local"
"""本地租户源实现名。"""


class LocalTenantSource(BaseObject):
    """本地租户源：查本服务平台库 + 缓存 + 版本键（实现 `TenantLookup` 契约）。"""

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
            registry: 引擎注册表（经平台服务库取数）。
            cache: 缓存 Region（None 表示不缓存、每次直查）。
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
            code: 租户编码。
            domain: 子域名。
        """
        if code:
            self._cache_delete(snapshot_cache_key("code", code))
        if domain:
            self._cache_delete(snapshot_cache_key("domain", domain))

    def bump_version(self) -> None:
        """递增全局版本键（写路径变更后调用；各消费方惰性重载）。"""
        cache = self.cache
        if cache is None:
            return
        cache.set(TENANT_VERSION_KEY, cache.get_global_version() + 1)

    async def _resolve(self, kind: str, value: str) -> TenantContext:
        """取数编排：缓存（版本比对）→ 库查询 → 回填 → 状态判定。

        Args:
            kind: `code` / `domain`。
            value: 查询值。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 租户不存在。
            TenantSuspendedError: 租户已停用（含引擎强制回收）。
        """
        key = snapshot_cache_key(kind, value)
        snapshot = self._cache_get(key)
        if snapshot is None:
            snapshot = await self._load(kind, value)
            if snapshot is None:
                raise TenantNotFoundError(f"未知租户：{value}")
            self._cache_set(key, snapshot)
        if snapshot.status != ACTIVE_STATUS:
            await self._registry.release(f"tenant_{snapshot.code}")
            raise TenantSuspendedError(f"租户已停用：{snapshot.code}")
        return to_tenant_context(snapshot)

    async def _load(self, kind: str, value: str) -> TenantSnapshot | None:
        """平台服务库查询（软删除过滤；未命中返回 None）。

        经统一会话入口取平台库会话：异步方言走异步会话，达梦等同步方言走同步门面。
        """
        column = SysTenant.code if kind == "code" else SysTenant.domain
        statement = select(SysTenant).where(column == value, SysTenant.deleted_at.is_(None)).limit(1)
        async with session_scope(self._registry, db_key=PLATFORM_DB_KEY, factory=self._session_factory) as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return None if row is None else _snapshot(row)

    def _cache_get(self, key: str) -> TenantSnapshot | None:
        """读缓存（版本不符视为未命中）。

        Args:
            key: 缓存 key。

        Returns:
            TenantSnapshot | None: 快照；未命中 / 陈旧返回 None。
        """
        cache = self.cache
        if cache is None:
            return None
        raw = cache.get(key)
        if not isinstance(raw, Mapping):
            return None
        payload = cast("Mapping[str, object]", raw)
        version = payload.get("version")
        if not isinstance(version, int) or cache.is_stale(TENANT_VERSION_KEY, version):
            return None
        try:
            return TenantSnapshot.from_payload(payload)
        except KeyError:
            return None

    def _cache_set(self, key: str, snapshot: TenantSnapshot) -> None:
        """写缓存（附当前全局版本戳）。

        Args:
            key: 缓存 key。
            snapshot: 注册快照。
        """
        cache = self.cache
        if cache is None:
            return
        cache.set(key, snapshot.to_payload(version=cache.get_global_version()), self._cache_ttl)

    def _cache_delete(self, key: str) -> None:
        """删缓存（幂等）。

        Args:
            key: 缓存 key。
        """
        cache = self.cache
        if cache is not None:
            cache.delete(key)


def register_local_tenant_source() -> None:
    """向共享基座登记 `local` 实现（本服务模块导入时调用，幂等）。"""

    def _factory(
        *,
        settings: Settings,
        registry: EngineRegistry,
        cache: CacheRegion | None,
        session_factory: SessionFactory | None,
    ) -> LocalTenantSource:
        """构造本地租户源。"""
        return LocalTenantSource(
            registry,
            cache=cache,
            session_factory=session_factory,
            cache_ttl=settings.tenant.resolve_cache_ttl,
        )

    register_tenant_lookup(LOCAL_TENANT_SOURCE, _factory)


def _snapshot(row: SysTenant) -> TenantSnapshot:
    """注册记录 → 快照（时间转 ISO 串，跨缓存实现序列化安全）。"""
    return TenantSnapshot(
        code=row.code,
        name=row.name,
        domain=row.domain,
        status=row.status,
        expire_at=row.expire_at.isoformat() if row.expire_at else None,
        tenant_id=int(row.id),
    )

