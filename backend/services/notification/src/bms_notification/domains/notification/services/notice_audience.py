"""公告应读人数读取：复用平台用户只读出口（`platform.user.query`）。

- 只读、不缓存：应读人数要求实时反映启用 / 停用；
- 平台入口按「能力分配 + 平台内部服务白名单」判定，通知服务经 `require_capability_or_service`
  白名单放行（不要求在服务票据里声明 `user` 域）；
- 不可达 / 非 2xx / 响应非法一律 `70206`，不返回猜测值。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import NoticeAudienceUnavailableError, ServiceUnavailableError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = ["USER_QUERY_PATH", "NoticeAudienceReader"]

PLATFORM_SERVICE_KEY = "platform"
"""平台服务标识（用户只读出口的提供方）。"""

USER_QUERY_PATH = "/api/v1/platform/internal/users/query"
"""平台用户只读查询端点。"""


class NoticeAudienceReader(BaseFrameworkObject):
    """应读人数读取（平台启用用户数）。"""

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def count_enabled(self) -> int:
        """读取当前租户启用用户数。

        Returns:
            int: 启用用户总数。

        Raises:
            NoticeAudienceUnavailableError: 下游不可达 / 非 2xx / 响应非法（`70206` / 503）。
        """
        request = ServiceRequest(
            service=PLATFORM_SERVICE_KEY,
            method="POST",
            path=USER_QUERY_PATH,
            tenant_id=get_current_tenant_id(),
            json_body=ConcurrentStableFrozenDict({"status": "enabled", "page": 1, "size": 1}),
        )
        try:
            response = await self._client.call(request)
        except ServiceUnavailableError as exc:
            raise NoticeAudienceUnavailableError("应读人数读取失败：用户服务不可用") from exc
        if not 200 <= response.status_code < 300:
            raise NoticeAudienceUnavailableError(f"应读人数读取失败：HTTP {response.status_code}")
        payload = response.payload()
        if not isinstance(payload, dict):
            raise NoticeAudienceUnavailableError("应读人数读取失败：响应不是 JSON 对象")
        envelope = cast("dict[str, object]", payload)
        if int(str(envelope.get("code", -1))) != 0:
            raise NoticeAudienceUnavailableError(f"应读人数读取失败：{envelope.get('message') or envelope.get('code')}")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise NoticeAudienceUnavailableError("应读人数读取失败：响应缺少 data 对象")
        total = cast("dict[str, object]", data).get("total")
        if not isinstance(total, int) or total < 0:
            raise NoticeAudienceUnavailableError("应读人数读取失败：total 非法")
        return total
