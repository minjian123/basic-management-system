"""出站集成能力域 · HTTP：统一外部调用契约（真实 httpx 封装随系统集成阶段回补）。

- `DEFAULT_TIMEOUT` / `DEFAULT_MAX_RETRIES`：默认超时（秒）与最大重试次数。
- `HttpResponse`：响应数据契约（frozen）。
- `BaseHttpClient`：能力域中间层契约（`key = "http_client"`）——异步 `request`（超时 / 重试 / 熔断由实现内部处理）。
- `get_http_client`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "BaseHttpClient",
    "HttpResponse",
    "get_http_client",
]

DEFAULT_TIMEOUT = 10
"""默认超时（秒）。"""

DEFAULT_MAX_RETRIES = 3
"""默认最大重试次数。"""


@dataclass(frozen=True)
class HttpResponse(BaseObject):
    """响应数据契约。"""

    status_code: int
    """HTTP 状态码。"""

    headers: Mapping[str, str]
    """响应头。"""

    content: bytes
    """响应体字节。"""


class BaseHttpClient(BasePluggable, ABC):
    """出站 HTTP 契约：统一请求（超时 / 重试 / 熔断由实现内部处理）。"""

    key: str = "http_client"
    plugin_key: str = "http_client"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        timeout: int | None = None,
    ) -> HttpResponse:
        """发起出站 HTTP 请求。

        Args:
            method: HTTP 方法（GET / POST / ...）。
            url: 目标地址。
            headers: 请求头（可选）。
            content: 请求体字节（可选）。
            timeout: 超时（秒，默认 `DEFAULT_TIMEOUT`）。

        Returns:
            HttpResponse: 响应（状态码 / 头 / 字节内容）。
        """


def get_http_client(request: Request) -> BaseHttpClient:
    """取应用级 HTTP 客户端（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseHttpClient: 应用装配的客户端实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseHttpClient",
        resolve_plugin(
            "http_client",
            settings.http_client.provider,
            expected_version=BaseHttpClient.contract_version,
        ),
    )
