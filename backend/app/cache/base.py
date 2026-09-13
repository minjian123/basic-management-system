"""缓存能力域：Region 分域基座契约（真实实现 → 阶段六 通用能力回补）。"""

from abc import ABC, abstractmethod

from app.core.base import BaseObject

CACHE_KEY_PREFIX = "bms"
GLOBAL_TENANT = "global"


def build_cache_key(*, tenant: str | None, domain: str, business_key: str) -> str:
    """构建缓存 key（规范 `bms:{租户|global}:{域}:{业务键}`）。

    Args:
        tenant: 租户标识；None 表示全局（`global`）。
        domain: 业务域简称。
        business_key: 业务键。

    Returns:
        str: 缓存 key。
    """
    return f"{CACHE_KEY_PREFIX}:{tenant or GLOBAL_TENANT}:{domain}:{business_key}"


class CacheRegion(BaseObject, ABC):
    """缓存 Region 分域基座契约：key 规范、TTL、全局版本号惰性比对。

    - 全 key 带 TTL；三防（穿透 / 击穿 / 雪崩）在基座统一。
    - 真实读写接 dogpile.cache Region（回补通用能力阶段）。
    """

    default_ttl: int = 300

    @property
    @abstractmethod
    def domain(self) -> str:
        """业务域简称（用于 key 分域）。"""

    @abstractmethod
    def get(self, key: str) -> object | None:
        """读缓存；不存在返回 None。"""

    @abstractmethod
    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（`ttl` 为空用 `default_ttl`）。"""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删缓存；不存在返回 False。"""

    @abstractmethod
    def get_global_version(self) -> int:
        """取全局版本号（跨实例一致性判定）。"""

    def build_key(self, business_key: str, *, tenant: str | None = None) -> str:
        """按域与租户拼缓存 key。

        Args:
            business_key: 业务键。
            tenant: 租户标识；None 为全局。

        Returns:
            str: 缓存 key。
        """
        return build_cache_key(tenant=tenant, domain=self.domain, business_key=business_key)

    def is_stale(self, key: str, version: int) -> bool:
        """版本陈旧判定（派生）：与当前全局版本号不一致即陈旧。

        Args:
            key: 缓存 key（预留：分层失效回补后使用）。
            version: 记录时捕获的版本号。

        Returns:
            bool: 陈旧为 True。
        """
        return version != self.get_global_version()
