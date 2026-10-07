"""权限版本与权限缓存键构造（域 `permission`）。

缓存键形态（对齐《概要设计 · 角色管理》与《架构设计 · 权限计算引擎》）：

- 权限版本号：`bms:{租户}:permission:version`（**按租户**计数器，授权变更后一次递增）；
- 用户权限缓存：`bms:{租户}:perm:{用户 ID}:{版本}`（权限计算引擎按版本判定失效）。

与菜单版本（全局 `bms:global:menu:version`）区分：授权属**租户内**数据，某租户的授权变更不应影响其它租户。
"""

from bms_core.cache.base import build_cache_key

PERMISSION_CACHE_DOMAIN = "permission"
"""权限版本缓存域名（键第二段）。"""

PERMISSION_CACHE_BUSINESS_DOMAIN = "perm"
"""用户权限缓存域名（权限计算引擎缓存键第二段）。"""

PERMISSION_VERSION_BUSINESS_KEY = "version"
"""权限版本业务键（键第三段）。"""


def permission_version_key(tenant_id: str | None) -> str:
    """权限版本号键（按租户）。

    Args:
        tenant_id: 租户标识；None 表示全局（兜底）。

    Returns:
        str: `bms:{租户|global}:permission:version`。
    """
    return build_cache_key(
        tenant=tenant_id, domain=PERMISSION_CACHE_DOMAIN, business_key=PERMISSION_VERSION_BUSINESS_KEY
    )


def permission_user_cache_key(tenant_id: str | None, user_id: int | str, version: int) -> str:
    """用户权限缓存键（按租户 + 用户 + 版本）。

    Args:
        tenant_id: 租户标识；None 表示全局。
        user_id: 用户主键。
        version: 权限版本号（变更即 +1，旧版本键自然失效）。

    Returns:
        str: `bms:{租户|global}:perm:{用户 ID}:{版本}`。
    """
    return build_cache_key(
        tenant=tenant_id, domain=PERMISSION_CACHE_BUSINESS_DOMAIN, business_key=f"{user_id}:{version}"
    )
