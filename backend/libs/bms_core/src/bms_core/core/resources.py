"""core 层异步资源统一登记与回收：应用生命周期统一释放。"""

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject


class ResourceManager(BaseFrameworkObject):
    """异步资源登记表：登记后由应用生命周期逆序统一释放。"""

    def __init__(self) -> None:
        """初始化空登记表。"""
        self._resources: ConcurrentStableList[BaseAsyncResource] = ConcurrentStableList()

    def register(self, resource: BaseAsyncResource) -> None:
        """登记异步资源。

        Args:
            resource: 实现 `aclose` 的异步资源。
        """
        self._resources.add(resource)

    async def aclose(self) -> None:
        """逆序释放全部资源（幂等）。"""
        while self._resources:
            resource = self._resources[-1]
            self._resources.remove(resource)
            await resource.aclose()
