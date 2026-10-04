"""菜单能力域常量与缓存键构造（域 `menu`）。

缓存键形态（对齐《概要设计 · 菜单管理》「关键时序与协作」节）：

- 菜单树 / 表单元数据：`bms:{租户|global}:menu:{locale}:{version}`（未过滤的元数据，按语言维度）；
- 元数据版本号：`bms:global:menu:version`（全局计数器，写操作递增）。
"""

from bms_core.cache.base import build_cache_key

MENU_CACHE_DOMAIN = "menu"
"""菜单能力域缓存域名（键第二段）。"""

MENU_TREE_CACHE_TTL_KEY = "menu.tree_cache_ttl"
"""菜单树缓存 TTL 参数键（`sys_config` 参数；缺省见 `DEFAULT_MENU_TREE_CACHE_TTL`）。"""

DEFAULT_MENU_TREE_CACHE_TTL = 300
"""菜单树缓存 TTL 缺省值（秒；含随机偏移）。"""

MENU_STATUSES = ("enabled", "disabled")
"""菜单 / 表单 / 按钮 / 字段 / 业务码 / 动作码状态取值。"""

BUTTON_TYPES = ("toolbar", "interface")
"""按钮形态取值：`toolbar`（工具栏）/ `interface`（表单界面内）。"""


def menu_version_key() -> str:
    """元数据版本号键（全局）。

    Returns:
        str: `bms:global:menu:version`。
    """
    return build_cache_key(tenant=None, domain=MENU_CACHE_DOMAIN, business_key="version")


def menu_tree_key(tenant: str | None, locale: str, version: int) -> str:
    """菜单树 / 表单元数据缓存键（按租户与语言维度）。

    Args:
        tenant: 租户标识；None 表示全局。
        locale: 语言标识（如 `zh-CN`）。
        version: 元数据版本号（变更即 +1，旧版本键自然过期）。

    Returns:
        str: `bms:{租户|global}:menu:{locale}:{version}`。
    """
    return build_cache_key(tenant=tenant, domain=MENU_CACHE_DOMAIN, business_key=f"{locale}:{version}")
