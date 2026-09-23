"""edge 能力域缺省实现（Null Object）：恒定不信任、不引入假身份。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.edge.base import BaseEdgeTrust, EdgeTrustDecision

__all__ = ["NullEdgeTrust"]


class NullEdgeTrust(BaseEdgeTrust, BaseNullObject):
    """占位边缘信任：恒定不信任（未接入真实实现时使用；请求净化仍由边缘守卫执行）。"""

    def evaluate(self, headers: Mapping[str, str]) -> EdgeTrustDecision:
        """恒定不信任（不读头、不引入假身份）。

        Args:
            headers: 请求头映射（占位忽略）。

        Returns:
            EdgeTrustDecision: 恒定 `trusted=False`。
        """
        del headers
        return EdgeTrustDecision(trusted=False, reason="edge trust placeholder")
