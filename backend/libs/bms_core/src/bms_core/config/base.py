"""系统参数能力域：按 key 取数契约与缓存域（`sys_config` 读取基座）。

- 常量：缓存域 `CONFIG_CACHE_DOMAIN`（config）。
- `BaseConfigSource`（`key = plugin_key = "config_source"`）：异步 `get_many(keys)` 批量取参数值；
  只返回**存在的键**（缺失 / 源不可达降级由调用方回落代码默认表）。
- `ConfigCacheRegion`（`key = plugin_key = "config_cache_region"`）：缓存域扩展子类——固定 `domain="config"`，
  提供 `config_key` / `version_key` / `is_version_current` 与按 key 的异步读写 / 版本接口；
  真实实现（内存 / Redis）见 `config/cache.py`。
- 提供者 `get_config_source` / `get_config_cache_region`（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：**租户隔离由实现侧拼缓存 key / 选库**（方法不显式传租户，从请求上下文取），调用方不可绕过；
`get_many` 只承担「取存在的键值」，缺省回落由消费方的代码默认表承担（如验证码场景策略）。
管理面（CRUD / 页面 / 审计 / 平台默认下发流程）归阶段八「系统参数」模块，本基座只承载读取链路。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import cast

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "CONFIG_CACHE_DOMAIN",
    "BaseConfigSource",
    "ConfigCacheRegion",
    "get_config_cache_region",
    "get_config_source",
]

CONFIG_CACHE_DOMAIN = "config"
"""缓存域简称（`ConfigCacheRegion.domain`；key `bms:{tenant}:config:{config_key}`）。"""


class BaseConfigSource(BasePluggable, ABC):
    """系统参数取数契约：按 key 批量取参数值。"""

    key: str = "config_source"
    plugin_key: str = "config_source"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def get_many(self, keys: Sequence[str]) -> Mapping[str, str]:
        """批量取参数值（按 key）。

        只返回**存在的键**；缺失键不出现（调用方回落默认）。源不可达时返回空映射（降级，不抛错）。

        Args:
            keys: 参数键序列（实现侧去重）。

        Returns:
            Mapping[str, str]: 命中键 → 值；无命中返回空映射。
        """

    async def get(self, key: str, default: str = "") -> str:
        """取单参数值（默认实现委托 `get_many`；缺失回落 `default`）。

        Args:
            key: 参数键。
            default: 缺失时的默认值。

        Returns:
            str: 参数值或默认值。
        """
        values = await self.get_many((key,))
        return values.get(key, default)


class ConfigCacheRegion(CacheRegion, ABC):
    """系统参数缓存域扩展子类：固定 `domain="config"` 并补充按 key 的缓存与版本接口。"""

    key: str = "config_cache_region"
    plugin_key: str = "config_cache_region"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    def domain(self) -> str:
        """业务域简称（固定 `config`）。

        Returns:
            str: 缓存域简称。
        """
        return CONFIG_CACHE_DOMAIN

    def config_key(self, tenant: str | None, config_key: str) -> str:
        """拼参数缓存 key（`bms:{tenant}:config:{config_key}`）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。

        Returns:
            str: 缓存 key。
        """
        return self.build_key(config_key, tenant=tenant)

    def version_key(self, tenant: str | None) -> str:
        """拼参数版本键（`bms:{tenant}:config:version`）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            str: 版本键。
        """
        return self.build_key("version", tenant=tenant)

    def is_version_current(self, version: int, *, tenant: str | None) -> bool:
        """版本一致性判定（派生）。

        Args:
            version: 记录时捕获的版本号。
            tenant: 租户标识；None 为全局。

        Returns:
            bool: 一致为 True。
        """
        return not self.is_stale(self.version_key(tenant), version)

    async def aget_value(self, tenant: str | None, config_key: str) -> str | None:
        """读参数缓存（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。

        Returns:
            str | None: 命中值；未命中返回 None。
        """
        cached = self.get(self.config_key(tenant, config_key))
        return cached if isinstance(cached, str) else None

    async def aset_value(self, tenant: str | None, config_key: str, value: str, ttl: int | None = None) -> None:
        """写参数缓存（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。
            value: 参数值。
            ttl: 有效期（秒）。
        """
        self.set(self.config_key(tenant, config_key), value, ttl)

    async def adrop_value(self, tenant: str | None, config_key: str) -> None:
        """删参数缓存（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。
        """
        self.delete(self.config_key(tenant, config_key))

    async def aversion(self, tenant: str | None) -> int:
        """读参数版本号（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 当前版本号。
        """
        return self.get_global_version()

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增参数版本号（异步；缺省回退为当前版本 + 1）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 递增后的版本号。
        """
        return self.get_global_version() + 1


def get_config_source(request: Request) -> BaseConfigSource:
    """取应用级系统参数取数契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseConfigSource: 应用装配的参数取数实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseConfigSource",
        resolve_plugin(
            "config_source",
            settings.config_source.provider,
            expected_version=BaseConfigSource.contract_version,
        ),
    )


def get_config_cache_region(request: Request) -> ConfigCacheRegion:
    """取应用级系统参数缓存域（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        ConfigCacheRegion: 应用装配的参数缓存域实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "ConfigCacheRegion",
        resolve_plugin(
            "config_cache_region",
            settings.config_cache_region.provider,
            expected_version=ConfigCacheRegion.contract_version,
        ),
    )
