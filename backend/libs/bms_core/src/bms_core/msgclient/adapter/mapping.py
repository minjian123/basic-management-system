"""`ServiceRequest` ↔ RPC 帧的字段翻译，与帧错误 → bms 异常的逐码分派（07B `06_01` 步 2）。

**只翻译、不判定**：可重试性与错误类别由 04-4 的 `classify()` 在服务端判定、经帧头原样带到客户端
（`RpcCallError` 的 `category` / `retryable` / `layer`）。本模块**不维护第二张码表**——那会让
「客户端说可重试、服务端说不可重试」变成常驻 bug。

**方法名归一化只有一处**：`/api/v1/foo/bar` → `foo.bar`（msg 04-5 §2.3 同一口径）。放进调用点
就会在「加一层子路径」时漂移。
"""

from __future__ import annotations

import json

from bms_core.api.base import API_PREFIX
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import BizError, ParamError, RateLimitError, ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.serialization import normalize_collections
from bms_core.msgclient.constants import RPC_RATE_LIMITED_CODE
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.rpc import RpcCallError
from bms_core.servicecall.base import ServiceRequest

__all__ = [
    "OUTCOME_UNKNOWN",
    "QUERY_HEADER_PREFIX",
    "method_of",
    "query_headers",
    "request_payload",
    "to_bms_error",
]

QUERY_HEADER_PREFIX = "query."
"""查询串透传前缀（帧头键 `query.<name>`；首期只承诺透传，不承诺等价 HTTP query 语义）。"""

OUTCOME_UNKNOWN = "unknown"
"""结果未知标记（`data.outcome`；与 04-2 的 `Outcome.UNKNOWN` 同值）。"""

_LOGGER = get_logger("bms_core.msgclient.adapter")


def method_of(path: str) -> str:
    """把公开契约路径归一为 RPC 方法名（`/api/v1/foo/bar` → `foo.bar`）。

    Args:
        path: 目标路径（调用前已由 `validate_service_request` 校验落在 `API_PREFIX` 下）。

    Returns:
        str: RPC 方法名。

    Raises:
        ParamError: 路径恰为 `API_PREFIX`（没有可归一的末段，无法成为方法名）。
    """
    if path == API_PREFIX:
        raise ParamError(f"服务间调用路径无法归一为 RPC 方法名：{path!r}")
    prefix = f"{API_PREFIX}/"
    tail = path[len(prefix) :] if path.startswith(prefix) else path
    tail = tail.strip("/")
    if not tail:
        raise ParamError(f"服务间调用路径无法归一为 RPC 方法名：{path!r}")
    return tail.replace("/", ".")


def query_headers(query: ConcurrentStableFrozenDict[str, str] | None) -> ConcurrentStableDict[str, str]:
    """查询串逐项转帧头（`query.<name>`）。

    RPC 帧没有查询串概念，但把 query 丢掉会让现有 GET 调用在切换后静默变形；塞进 payload 又会
    改变载荷契约。折中是**显式前缀透传**：服务端能从帧头原样读到，语义解释留给消费方。

    Args:
        query: 查询参数（可为空）。

    Returns:
        ConcurrentStableDict[str, str]: 帧头片段（无查询时为空表）。
    """
    headers: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if not query:
        return headers
    for name, value in query.items():
        headers.set(f"{QUERY_HEADER_PREFIX}{name}", value)
    return headers


def request_payload(request: ServiceRequest) -> bytes:
    """把 `ServiceRequest` 的请求体转成 RPC 载荷字节。

    `json_body` 与 `content` **二选一**：同时给按 `ParamError` 拒（不猜优先级——猜错的后果是
    服务端收到一份「看起来对但字段缺一半」的报文）。

    Args:
        request: 调用请求。

    Returns:
        bytes: 载荷（无请求体为空字节）。

    Raises:
        ParamError: `json_body` 与 `content` 同时给（10001）。
    """
    if request.json_body is not None and request.content is not None:
        raise ParamError("服务间调用请求体二选一（json_body / content）")
    if request.json_body is not None:
        # 请求体常为集合体系对象（`ConcurrentStableDict` 等），标准 `json.dumps` 不认
        # → 出站前归一为内建容器（与 `servicecall.http` 同口径）；键排序保证同输入同字节。
        normalized = normalize_collections(request.json_body)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return request.content or b""


def to_bms_error(error: RpcCallError) -> BizError:
    """把帧错误分派为 bms 异常（按 `category` 选类，码值只进 `data`）。

    分派顺序即语义优先级：参数错误（改参可解）→ 业务拒绝（上抛不重试）→ 限流（唯一按码单列的
    瞬时码）→ 结果未知（超时）→ 服务端 bug（上抛并告警）→ 兜底不可用。

    Args:
        error: 协议层调用错误（`category` / `code` / `attempts` / `backoff_ms` 已由 04-4 回填）。

    Returns:
        BizError: 待抛出的 bms 异常实例（由调用方 `raise`，保留原始栈）。
    """
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "code": error.code,
            "category": str(error.category),
            "layer": error.layer,
            "attempts": error.attempts,
        }
    )
    if error.backoff_ms:
        data.set("backoff_ms", list(error.backoff_ms))
    if error.category is ErrorCategory.PARAM_ERROR:
        return ParamError(error.message or "RPC 调用参数错误", data=data)
    if error.category is ErrorCategory.BUSINESS_REJECT:
        code = error.code or int(ErrorCode.SERVICE_UNAVAILABLE)
        return BizError(code, error.message or "RPC 调用被业务拒绝", data=data)
    if error.category is ErrorCategory.TRANSIENT and error.code == int(RPC_RATE_LIMITED_CODE):
        if error.retry_after_ms is not None:
            data.set("retry_after_ms", error.retry_after_ms)
        return RateLimitError(error.message or "RPC 调用被限流", data=data)
    if error.category is ErrorCategory.UNKNOWN:
        data.set("outcome", OUTCOME_UNKNOWN)
        return ServiceUnavailableError(error.message or "RPC 调用结果未知（超时）", data=data)
    if error.category is ErrorCategory.SERVER_BUG:
        # 服务端 bug 要能被告警抓到：调用方拿到的仍是「下游不可用」，排障面靠这条日志。
        _LOGGER.warning("msg_rpc_server_bug", code=error.code, message=error.message, layer=error.layer)
    return ServiceUnavailableError(error.message or "RPC 服务不可用", data=data)
