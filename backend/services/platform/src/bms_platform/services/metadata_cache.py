"""元数据缓存版本助手（菜单表单与权限元数据共用，平台侧横切）。

菜单 / 表单 / 按钮 / 字段 / 权限码是**同一份**权限快照的解析输入（菜单 → 表单 → 权限码），
任一变更都必须让菜单树缓存与权限快照同时失效——只递增菜单版本会让已缓存的权限码集滞后一个 TTL。
本模块把「双版本递增 + 进程内元数据索引失效」收敛为一处，供两个业务域的服务共用。

本模块不含表结构与业务规则，故不归属任何业务域（`shared_paths`）。
"""

from bms_core.cache.base import CacheRegion
from bms_core.db.tenant import current_tenant_id_str
from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.menu import menu_tree_key, menu_version_key
from bms_core.permission.cache import current_permission_cache_store
from bms_core.permission.version import permission_version_key

__all__ = ["bump_metadata_version", "metadata_version"]


async def metadata_version(cache: CacheRegion) -> int:
    """当前元数据版本号（缓存计数器；未初始化按 0）。

    Args:
        cache: 缓存 Region。

    Returns:
        int: 元数据版本号。
    """
    raw = await cache.aget(menu_version_key())
    return raw if isinstance(raw, int) else 0


async def bump_metadata_version(cache: CacheRegion) -> None:
    """递增元数据版本并清空进程内元数据索引（菜单版本 + 权限版本同源失效）。

    语言与租户取请求上下文（与缓存键构造同源）。

    Args:
        cache: 缓存 Region。
    """
    locale = current_dict_locale.get() or DEFAULT_LOCALE
    tenant_id = current_tenant_id_str()
    old_version = await metadata_version(cache)
    await cache.aincrease(menu_version_key())
    await cache.adelete(menu_tree_key(tenant_id, locale, old_version))
    await cache.aincrease(permission_version_key(tenant_id))
    current_permission_cache_store().invalidate_metadata()
