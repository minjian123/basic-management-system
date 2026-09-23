"""edge 能力域网关标记头实现：按网关专属标记头判定可信来源（过渡实现）。

- `MarkerEdgeTrust`：请求头 `X-Gateway-Identity` 命中期望值即判定为「来自可信边缘」，
  按身份头解析 `EdgeIdentity`；不命中即不信任。
- 构造需显式参数（不经继承自动登记），由 `MarkerEdgeTrustFactory(settings)` 显式登记。
- 占位口径：期望值为非密钥常量（Git 内可见），仅结构占位 + 可测；真实防旁路（服务 JWT / mTLS）
  随 07_03 / K8s 阶段回补，届时以真实实现替换 `[edge].provider`。
"""

from collections.abc import Mapping

from bms_core.edge.base import BaseEdgeTrust, EdgeIdentity, EdgeTrustDecision
from bms_core.edge.headers import GATEWAY_IDENTITY_HEADER

__all__ = ["MarkerEdgeTrust"]


class MarkerEdgeTrust(BaseEdgeTrust):
    """网关专属标记头信任实现（标记命中即信任，按身份头解析身份）。"""

    plugin_name: str = "marker"

    def __init__(self, *, expected: str) -> None:
        """初始化。

        Args:
            expected: 网关专属标记头期望值（`X-Gateway-Identity`）。
        """
        self._expected = expected

    def evaluate(self, headers: Mapping[str, str]) -> EdgeTrustDecision:
        """按标记头判定信任并解析身份。

        Args:
            headers: 请求头映射（`str -> str`；键大小写不敏感）。

        Returns:
            EdgeTrustDecision: 标记命中 → 信任 + 身份；未命中 → 不信任。
        """
        normalized = {key.lower(): value for key, value in headers.items()}
        marker = normalized.get(GATEWAY_IDENTITY_HEADER.lower())
        if marker != self._expected:
            return EdgeTrustDecision(trusted=False, reason="missing gateway identity marker")
        return EdgeTrustDecision(trusted=True, identity=EdgeIdentity.from_headers(headers))
