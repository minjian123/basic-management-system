"""作业库键清单：本服务平台链 + 租户链（带 TTL 缓存）。

- 平台服务与产品服务同构：都扫「自身平台库 + 自身租户库」；
- 租户链由租户注册库（`platform_tenant`）的 `db_basis` 派生，新开通租户最迟一个 TTL 后纳入；
- 跨服务作业不互相扫描：worker 只处理本服务库里的作业。
"""

from __future__ import annotations

import time

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.tenant.registry import tenant_refs

__all__ = ["JobDbKeys"]


class JobDbKeys(BaseFrameworkObject):
    """作业库键提供者（平台链 + 租户链，TTL 缓存）。"""

    def __init__(
        self,
        *,
        factory: EngineFactory,
        service_key: str,
        ttl_seconds: float,
        include_platform_chain: bool = True,
    ) -> None:
        """初始化。

        Args:
            factory: 引擎工厂（解析租户注册库连接串）。
            service_key: 本服务标识（租户库名基按服务派生）。
            ttl_seconds: 缓存有效期（秒）。
            include_platform_chain: 是否包含服务平台链。
        """
        self._factory = factory
        self._service_key = service_key
        self._ttl = ttl_seconds
        self._include_platform_chain = include_platform_chain
        self._cached: ConcurrentStableList[str] = ConcurrentStableList()
        self._expires_at = 0.0

    async def __call__(self) -> ConcurrentStableList[str]:
        """取库键清单（命中缓存直接返回）。

        Returns:
            ConcurrentStableList[str]: 库键清单（平台链在前，租户链随后）。
        """
        monotonic = time.monotonic()
        if self._cached and monotonic < self._expires_at:
            return self._cached
        keys: ConcurrentStableList[str] = ConcurrentStableList()
        if self._include_platform_chain:
            keys.add(build_platform_db_key(self._service_key))
        registry_url = self._factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
        refs = await tenant_refs(registry_url)
        for ref in refs:
            keys.add(build_tenant_db_key(ref.db_basis, service=self._service_key))
        self._cached = keys
        self._expires_at = monotonic + self._ttl
        return keys
