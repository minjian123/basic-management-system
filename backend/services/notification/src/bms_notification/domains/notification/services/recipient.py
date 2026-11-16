"""收件人解析：显式地址优先，缺省经平台用户只读出口取邮箱 / 手机号 / locale。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.objects import BaseValueObject
from bms_core.core.roots import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = ["PLATFORM_USER_QUERY_PATH", "RecipientInfo", "RecipientResolver"]

PLATFORM_USER_QUERY_PATH = "/api/v1/platform/internal/users/query"
"""平台用户只读出口路径。"""


@dataclass(frozen=True)
class RecipientInfo(BaseValueObject):
    """收件人信息（用户维度）。"""

    email: str | None = None
    """邮箱。"""

    phone: str | None = None
    """手机号。"""

    locale: str | None = None
    """语言偏好。"""


class RecipientResolver(BaseFrameworkObject):
    """按用户主键解析地址与语言（平台用户只读出口）。"""

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端。
        """
        self._client = client

    async def resolve(self, user_id: int) -> RecipientInfo:
        """读取用户地址与语言。

        Args:
            user_id: 用户主键。

        Returns:
            RecipientInfo: 收件人信息；用户不存在返回全空。

        Raises:
            ServiceUnavailableError: 平台用户查询不可达 / 响应非法（10007）。
        """
        request = ServiceRequest(
            service="platform",
            method="POST",
            path=PLATFORM_USER_QUERY_PATH,
            tenant_id=get_current_tenant_id(),
            json_body=ConcurrentStableFrozenDict(
                {
                    "ids": [str(user_id)],
                    "status": "enabled",
                    "page": 1,
                    "size": 1,
                }
            ),
        )
        response = await self._client.call(request)
        if not 200 <= response.status_code < 300:
            raise ServiceUnavailableError(f"平台用户查询返回 {response.status_code}")
        return _parse_payload(response.payload())


def _parse_payload(payload: object) -> RecipientInfo:
    """解析平台用户查询响应。

    Args:
        payload: 响应体。

    Returns:
        RecipientInfo: 收件人信息。

    Raises:
        ServiceUnavailableError: 响应结构非法。
    """
    if not isinstance(payload, Mapping):
        raise ServiceUnavailableError("平台用户查询响应非法")
    data = cast("Mapping[str, object]", payload).get("data")
    if not isinstance(data, Mapping):
        raise ServiceUnavailableError("平台用户查询响应非法")
    rows = cast("Mapping[str, object]", data).get("list")
    if not isinstance(rows, list) or not rows:
        return RecipientInfo()
    first = cast("list[object]", rows)[0]
    if not isinstance(first, Mapping):
        raise ServiceUnavailableError("平台用户查询响应非法")
    row = cast("Mapping[str, object]", first)
    email = row.get("email")
    phone = row.get("phone")
    locale = row.get("locale")
    return RecipientInfo(
        email=email if isinstance(email, str) and email else None,
        phone=phone if isinstance(phone, str) and phone else None,
        locale=locale if isinstance(locale, str) and locale else None,
    )
