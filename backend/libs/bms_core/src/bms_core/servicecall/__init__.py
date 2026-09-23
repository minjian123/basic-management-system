"""服务间通信能力域（servicecall）：同步调用契约与实现（服务间只经公开契约调用）。

- 契约与数据：`BaseServiceClient` / `ServiceRequest` / `ServiceResponse` / `ServiceCallPolicy`。
- 实现：`HttpServiceClient`（httpx）/ `NullServiceClient`（占位）。
- 提供者：`get_service_client`。
"""

from bms_core.servicecall.base import (
    DEFAULT_BASE_URL_TEMPLATE,
    DEFAULT_CALL_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_STATUSES,
    SERVICE_CALL_DEPENDENCY_PREFIX,
    SERVICE_CLIENT_OPTION_BASE_URL,
    BaseServiceClient,
    ServiceCallPolicy,
    ServiceRequest,
    ServiceResponse,
    build_service_url,
    get_service_client,
    resolve_rate_limit_key,
    service_dependency,
    validate_service_request,
)
from bms_core.servicecall.http import HttpServiceClient
from bms_core.servicecall.null import NullServiceClient

__all__ = [
    "DEFAULT_BASE_URL_TEMPLATE",
    "DEFAULT_CALL_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_BACKOFF",
    "DEFAULT_RETRY_STATUSES",
    "SERVICE_CALL_DEPENDENCY_PREFIX",
    "SERVICE_CLIENT_OPTION_BASE_URL",
    "BaseServiceClient",
    "HttpServiceClient",
    "NullServiceClient",
    "ServiceCallPolicy",
    "ServiceRequest",
    "ServiceResponse",
    "build_service_url",
    "get_service_client",
    "resolve_rate_limit_key",
    "service_dependency",
    "validate_service_request",
]
