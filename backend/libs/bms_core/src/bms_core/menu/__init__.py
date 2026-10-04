"""菜单能力域（`menu`）：权限元数据缓存键与常量。

- 缓存域 `MENU_CACHE_DOMAIN`（`menu`）：菜单树 / 表单元数据缓存键经基座
  `bms_core/cache/base.py::build_cache_key` 规范构造为 `bms:{租户|global}:menu:{业务键}`；
- 版本键 `menu:version`（全局）：元数据写操作递增，键带版本号实现即时失效。
"""

from bms_core.menu.base import (
    BUTTON_TYPES,
    DEFAULT_MENU_TREE_CACHE_TTL,
    MENU_CACHE_DOMAIN,
    MENU_STATUSES,
    MENU_TREE_CACHE_TTL_KEY,
    menu_tree_key,
    menu_version_key,
)

__all__ = [
    "BUTTON_TYPES",
    "DEFAULT_MENU_TREE_CACHE_TTL",
    "MENU_CACHE_DOMAIN",
    "MENU_STATUSES",
    "MENU_TREE_CACHE_TTL_KEY",
    "menu_tree_key",
    "menu_version_key",
]
