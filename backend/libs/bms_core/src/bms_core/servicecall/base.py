"""服务间通信能力域：同步调用契约（服务间只经公开契约调用 + 显式超时 / 重试 / 熔断 / 限流）。

- `ServiceCallPolicy`：调用韧性策略（超时 / 最大重试 / 重试状态码 / 指数退避 / 熔断开关 / 限流规则）。
- `ServiceRequest`：服务间调用请求（目标服务 + 方法 + 公开契约路径 + 查询 / 头 / 体 + 策略）。
- `ServiceResponse`：调用响应（状态码 / 头 / 字节体 + `payload()` 解析）。
- `BaseServiceClient`：能力域中间层契约（`key = plugin_key = "service_client"`）——异步 `call`。
- `validate_service_request`：公开契约边界校验——目标服务须在服务目录登记启用、路径须属内部公开面
  （`/api/v1`）且策略合法，否则抛 `ParamError`（10001，不发起调用）。
- `build_service_url`：按基址模板（默认 Compose DNS `http://{service}:8000`）拼装目标地址。
- `service_dependency`：熔断 / 降级依赖标识（`service:<服务标识>`）。
- `get_service_client`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：基座只承载**调用封装与韧性判定**、不接管业务降级路径；失败时经 `BaseFallbackPolicy` 给出动作、
随 `ServiceUnavailableError`（10007）的 `data` 回传，调用方按动作处理。服务间调用**不经网关**（东西向直连）。
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import urlencode

from fastapi import Request

from bms_core.api.base import API_PREFIX
from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.ratelimit.base import RateLimitRule, build_rate_limit_key
from bms_core.services.service_contract import service_enabled

__all__ = [
    "DEFAULT_BASE_URL_TEMPLATE",
    "DEFAULT_CALL_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_BACKOFF",
    "DEFAULT_RETRY_STATUSES",
    "SERVICE_CALL_DEPENDENCY_PREFIX",
    "SERVICE_CLIENT_OPTION_BASE_URL",
    "BaseServiceClient",
    "ServiceCallPolicy",
    "ServiceRequest",
    "ServiceResponse",
    "build_service_url",
    "get_service_client",
    "resolve_rate_limit_key",
    "service_dependency",
    "validate_service_request",
]

DEFAULT_CALL_TIMEOUT = 5.0
"""默认调用超时（秒）；服务间调用宜快速失败，短于外部出站默认超时。"""

DEFAULT_MAX_RETRIES = 2
"""默认最大重试次数（不含首次；共 3 次尝试）。"""

DEFAULT_RETRY_BACKOFF = 0.1
"""默认重试退避基数（秒，指数退避：`base * 2 ** 尝试序号`；0 表示不等待）。"""

DEFAULT_RETRY_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)
"""默认可重试的响应状态码（下游瞬时故障）。"""

DEFAULT_BASE_URL_TEMPLATE = "http://{service}:8000"
"""默认基址模板（Compose DNS 服务名 + 每服务端口；迁 K8s 平移为 Service 名）。"""

SERVICE_CLIENT_OPTION_BASE_URL = "base_url_template"
"""基址模板配置键（`[service_client].options.base_url_template`）。"""

SERVICE_CLIENT_OPTION_ATTACH_TOKEN = "attach_service_token"
"""出站附加服务 JWT 开关配置键（`[service_client].options.attach_service_token`；默认 False）。"""

SERVICE_CALL_DEPENDENCY_PREFIX = "service:"
"""熔断 / 降级依赖标识前缀（`service:<服务标识>`，供 `BaseCircuitBreaker` / `BaseFallbackPolicy`）。"""


def service_dependency(service: str) -> str:
    """熔断 / 降级依赖标识（`service:<服务标识>`）。

    Args:
        service: 目标服务标识。

    Returns:
        str: 依赖标识。
    """
    return f"{SERVICE_CALL_DEPENDENCY_PREFIX}{service}"


@dataclass(frozen=True)
class ServiceCallPolicy(BaseObject):
    """调用韧性策略：超时 / 重试 / 熔断 / 限流（逐调用覆盖，缺省取本类默认值）。"""

    timeout: float = DEFAULT_CALL_TIMEOUT
    """显式超时（秒）。"""

    max_retries: int = DEFAULT_MAX_RETRIES
    """最大重试次数（不含首次；0 表示不重试）。"""

    retry_statuses: tuple[int, ...] = DEFAULT_RETRY_STATUSES
    """命中即重试的响应状态码（重试耗尽仍命中则按服务不可用处理）。"""

    retry_backoff: float = DEFAULT_RETRY_BACKOFF
    """重试退避基数（秒，指数退避；0 表示不等待）。"""

    circuit_breaker: bool = True
    """是否启用熔断（复用 `BaseCircuitBreaker`，依赖名 `service:<key>`）。"""

    rate_limit: RateLimitRule | None = None
    """调用侧限流规则（None 表示不限流；超限抛 `RateLimitError` 10005）。"""

    rate_limit_key: str | None = None
    """限流 key（None 时按维度 `service` + 目标服务生成）。"""

    scopes: tuple[str, ...] = ()
    """出站服务 JWT 所需 scope（开启 `attach_service_token` 时作为签发 scope 来源）。"""


@dataclass(frozen=True)
class ServiceRequest(BaseObject):
    """服务间同步调用请求。"""

    service: str
    """目标服务标识（须在服务目录登记启用）。"""

    method: str
    """HTTP 方法（GET / POST / ...）。"""

    path: str
    """目标路径（须以内部公开面 `/api/v1` 开头）。"""

    query: Mapping[str, str] | None = None
    """查询参数（可选）。"""

    headers: Mapping[str, str] | None = None
    """请求头（可选；出站一律剥离入站 `Authorization`，服务 JWT 由客户端按开关签发附上）。"""

    json_body: dict[str, object] | None = None
    """JSON 请求体（可选；与 `content` 二选一）。"""

    content: bytes | None = None
    """原始请求体（可选；与 `json_body` 二选一）。"""

    tenant: str | None = None
    """调用方租户编码（可选；开启 `attach_service_token` 时随服务 JWT 的 `tenant` claim 传递，
    供目标服务经边缘信任回写租户头、解析租户库）。"""

    policy: ServiceCallPolicy = field(default_factory=ServiceCallPolicy)
    """调用韧性策略。"""


@dataclass(frozen=True)
class ServiceResponse(BaseObject):
    """服务间同步调用响应（非 2xx 原样返回，由调用方判定）。"""

    status_code: int
    """HTTP 状态码。"""

    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    """响应头。"""

    content: bytes = b""
    """响应体字节。"""

    def payload(self) -> object | None:
        """解析响应体为 JSON（空体 / 非 JSON 返回 None）。

        Returns:
            object | None: 解析结果；不可解析返回 None。
        """
        if not self.content:
            return None
        try:
            return json.loads(self.content)
        except json.JSONDecodeError, UnicodeDecodeError:
            return None


def validate_service_request(request: ServiceRequest) -> None:
    """校验调用请求落在公开契约面且策略合法（越界即拒，不发起调用）。

    Args:
        request: 调用请求。

    Raises:
        ParamError: 目标服务未登记启用、路径非 `/api/v1` 公开面、方法为空或策略非法（10001）。
    """
    if not request.service or not service_enabled(request.service):
        raise ParamError(f"服务间调用目标未登记或未启用：{request.service!r}")
    if request.path != API_PREFIX and not request.path.startswith(f"{API_PREFIX}/"):
        raise ParamError(f"服务间调用只经公开契约路径（{API_PREFIX}）：{request.path!r}")
    if not request.method:
        raise ParamError("服务间调用缺少 HTTP 方法")
    if request.policy.timeout <= 0:
        raise ParamError(f"服务间调用超时须为正数：{request.policy.timeout!r}")
    if request.policy.max_retries < 0:
        raise ParamError(f"服务间调用最大重试次数不得为负：{request.policy.max_retries!r}")


def build_service_url(request: ServiceRequest, base_url_template: str = DEFAULT_BASE_URL_TEMPLATE) -> str:
    """按基址模板拼装目标地址（含查询串）。

    Args:
        request: 调用请求。
        base_url_template: 基址模板（占位 `{service}`）。

    Returns:
        str: 目标地址（`{基址}{path}`，附查询串）。
    """
    base = base_url_template.format(service=request.service).rstrip("/")
    url = f"{base}{request.path}"
    if request.query:
        url = f"{url}?{urlencode(request.query)}"
    return url


class BaseServiceClient(BasePluggable, ABC):
    """服务间同步调用契约：统一 `call`（韧性由实现内部处理）。"""

    key: str = "service_client"
    plugin_key: str = "service_client"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """发起服务间同步调用。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 调用响应（非 2xx 原样返回）。

        Raises:
            ParamError: 目标服务 / 路径 / 策略非法（10001）。
            RateLimitError: 调用侧限流超限（10005）。
            ServiceUnavailableError: 下游不可达 / 超时 / 重试耗尽 / 熔断断开（10007）。
        """


def get_service_client(request: Request) -> BaseServiceClient:
    """取应用级服务间调用客户端（依赖注入提供者）。

    Args:
        request: 应用请求（取装配 settings）。

    Returns:
        BaseServiceClient: 应用装配的服务间调用实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseServiceClient",
        resolve_plugin(
            "service_client",
            settings.service_client.provider,
            expected_version=BaseServiceClient.contract_version,
        ),
    )


def _default_rate_limit_key(request: ServiceRequest) -> str:
    """调用侧限流 key（未显式给出时按维度 `service` + 目标服务生成）。

    Args:
        request: 调用请求。

    Returns:
        str: 限流 key。
    """
    return build_rate_limit_key(dimension="service", target=request.service)


def resolve_rate_limit_key(request: ServiceRequest) -> str:
    """解析调用侧限流 key（显式优先，缺省按目标服务）。

    Args:
        request: 调用请求。

    Returns:
        str: 限流 key。
    """
    return request.policy.rate_limit_key or _default_rate_limit_key(request)
