"""平台服务：图标注册表落库实现（`icon_registry` 插件，provider = `db`）。

注册表为应用级单例；实际落库按请求上下文（`current_icon_store`）委托平台 `IconStore`，
由 `api/icon.py` 的请求依赖设置与复位——保持「能力可替换」接缝，同时避免单例持有会话。
"""

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import PluginError
from bms_core.icon.base import (
    BaseIconRegistry,
    IconDraft,
    IconInfo,
    IconPatch,
    current_icon_store,
)

DB_ICON_PROVIDER = "db"
"""落库实现 provider 名（`[icon_registry].provider = "db"`）。"""


def _store():
    """取当前请求的图标落库实现。

    Returns:
        IconStore: 落库实现。

    Raises:
        PluginError: 请求上下文未设置（非 HTTP 调用路径）。
    """
    store = current_icon_store.get()
    if store is None:
        raise PluginError("图标落库实现未就绪（缺少请求上下文）")
    return store


class DbIconRegistry(BaseIconRegistry):
    """图标注册表：委托请求级落库实现（`sys_icon`）。"""

    plugin_name: str = DB_ICON_PROVIDER

    async def list(
        self, *, category: str | None = None, status: str | None = None, keyword: str | None = None
    ) -> ConcurrentStableList[IconInfo]:
        """列示图标（委托落库实现）。

        Args:
            category: 图标分组（None 表示全部）。
            status: 状态（None 表示全部）。
            keyword: 关键字（None 表示不过滤）。

        Returns:
            ConcurrentStableList[IconInfo]: 图标清单。
        """
        return await _store().list(category=category, status=status, keyword=keyword)

    async def get(self, code: str) -> IconInfo:
        """取图标详情（委托落库实现）。

        Args:
            code: 图标键。

        Returns:
            IconInfo: 图标定义。
        """
        return await _store().get(code)

    async def create(self, draft: IconDraft) -> IconInfo:
        """新增图标（委托落库实现）。

        Args:
            draft: 新增入参。

        Returns:
            IconInfo: 新增后的图标。
        """
        return await _store().create(draft)

    async def update(self, code: str, patch: IconPatch) -> IconInfo:
        """更新图标（委托落库实现）。

        Args:
            code: 图标键。
            patch: 更新入参。

        Returns:
            IconInfo: 更新后的图标。
        """
        return await _store().update(code, patch)

    async def delete(self, code: str) -> bool:
        """删除图标（委托落库实现）。

        Args:
            code: 图标键。

        Returns:
            bool: 是否删除了既有图标。
        """
        return await _store().delete(code)
