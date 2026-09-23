"""api 层中间件：入站链路 id（`X-Trace-Id`）、边缘请求净化、租户解析与请求日志（访问 / 慢请求 / 探针排除）。

- `TraceIdMiddleware`：纯 ASGI 中间件——读入站 `X-Trace-Id`（缺失回退当前 request_id，再缺失生成 32 位 hex）、
  写入 `core/context.py` 的 `current_trace_id`（日志体系与审计统一取值），并回写响应头；请求结束复位。
- `EdgeGuardMiddleware`：纯 ASGI 中间件——边缘请求净化与信任边界：无条件剥除客户端伪造身份头；
  信任时按契约回写网关验证过的身份、置请求态 `edge_identity` 与 `current_user_id`；
  `[edge].require_gateway_identity` 开且非豁免路径缺失可信身份时就地拒绝（网关旁路，直接 401）；
  装配次序先于租户解析，使信任模式下租户身份只采信网关注入值。见 `bms_core/edge/`。
- `TenantMiddleware`：纯 ASGI 中间件——全局租户解析（子域名 → `X-Tenant-ID` → token 租户位），
  写请求态 `tenant` 与租户上下文变量；豁免路径放行；未知 / 停用租户就地转统一错误响应（不进入下游）。
- `RequestLoggingMiddleware`：纯 ASGI 中间件——每请求生成 `request_id`（uuid4 hex）并解析 `client_ip` 写入上下文；
  请求结束输出单行访问日志（普通 INFO `request`，超 `slow_request_ms` 整行 WARNING `slow_request`）；
  探针（`/healthz`、`/readyz`）与文档路径（`/docs`、`/redoc`、`/openapi.json`）排除，任何级别不记。

口径：
- **必须为纯 ASGI 中间件**（不经 `BaseHTTPMiddleware`）：后者把下游应用放在独立任务中执行，
  中间件内设置的上下文变量传不到接口内（与 02-3-5「同步生成器依赖经线程池执行导致上下文丢失」同类问题）。
- `client_ip` 取 `X-Forwarded-For` 首值（兼容 nginx 反代）、兜底连接地址；仅日志展示，不作安全判定。
- 未捕获异常由全局异常处理器记 ERROR（含堆栈），本中间件照常记录 `status=500` 访问行。
"""

import time
import uuid
from collections.abc import Mapping
from contextvars import Token
from typing import cast

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bms_core.api.errors import build_error_response
from bms_core.core.base import BaseObject
from bms_core.core.context import (
    get_current_request_id,
    reset_current_client_ip,
    reset_current_request_id,
    reset_current_tenant,
    reset_current_trace_id,
    reset_current_user_id,
    reset_read_only,
    reset_tenant_context,
    set_current_client_ip,
    set_current_request_id,
    set_current_tenant,
    set_current_trace_id,
    set_current_user_id,
    set_read_only,
    set_tenant_context,
)
from bms_core.core.exceptions import AuthError, BizError
from bms_core.core.logging import get_logger
from bms_core.db.routing import is_read_method
from bms_core.db.tenant import DEFAULT_EXEMPT_PATHS, is_exempt_path, resolve_request_tenant
from bms_core.edge.base import BaseEdgeTrust, EdgeIdentity
from bms_core.edge.headers import (
    DEFAULT_EDGE_EXEMPT_PATHS,
    GATEWAY_IDENTITY_HEADER,
    SERVICE_IDENTITY_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    USER_SCOPES_HEADER,
)
from bms_core.edge.null import NullEdgeTrust
from bms_core.tracing.base import TRACE_ID_HEADER, new_trace_id

__all__ = [
    "EdgeGuardMiddleware",
    "ReadOnlyMiddleware",
    "RequestLoggingMiddleware",
    "TenantMiddleware",
    "TraceIdMiddleware",
]

_EXCLUDED_PATHS = frozenset({"/healthz", "/readyz", "/docs", "/redoc", "/openapi.json"})


class TraceIdMiddleware(BaseObject):
    """入站链路 id 中间件（纯 ASGI）：读请求头 → 缺省生成 → 上下文 → 回写响应头。"""

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = Headers(scope=scope).get(TRACE_ID_HEADER) or get_current_request_id() or new_trace_id()
        scope.setdefault("state", {})["trace_id"] = trace_id
        token = set_current_trace_id(trace_id)

        async def _send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[TRACE_ID_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, _send_with_trace_id)
        finally:
            reset_current_trace_id(token)


class TenantMiddleware(BaseObject):
    """租户解析全局中间件（纯 ASGI）：解析链 → 请求态与租户上下文；未知 / 停用租户就地拒绝。

    - 来源次序（首个命中即止）：子域名（按注册表 `domain` 查）→ `X-Tenant-ID`（按 `code` 查）
      → token 租户位（请求态，认证阶段写入）；
    - 豁免路径（`[tenant].exempt_paths`，精确匹配）不解析、不设置上下文；
    - 无来源按 `[tenant].allow_demo_fallback` 回落演示租户（dev/test）或拒绝（prod）；
    - 解析失败（`BizError`）就地返回统一错误响应，不进入下游。
    """

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state: dict[str, object] = scope.setdefault("state", {})
        app = scope.get("app")
        app_state = getattr(app, "state", None)
        settings = getattr(app_state, "settings", None)
        source = getattr(app_state, "tenant_source", None)
        headers = Headers(scope=scope)
        try:
            tenant = await resolve_request_tenant(
                path=str(scope.get("path", "")),
                host=headers.get("host"),
                header=headers.get("X-Tenant-ID"),
                token_tenant=cast("str | None", state.get("tenant_id")),
                source=source,
                exempt_paths=settings.tenant.exempt_paths if settings is not None else DEFAULT_EXEMPT_PATHS,
                allow_demo_fallback=settings.tenant.allow_demo_fallback if settings is not None else True,
            )
        except BizError as exc:
            await build_error_response(scope, exc)(scope, receive, send)
            return

        state["tenant"] = tenant
        tenant_token = set_tenant_context(tenant)
        code_token = set_current_tenant(tenant.tenant_code if tenant else None)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_tenant(code_token)
            reset_tenant_context(tenant_token)


class ReadOnlyMiddleware(BaseObject):
    """只读标记中间件（纯 ASGI）：按 HTTP 方法设置 `read_only` 上下文（GET/HEAD/OPTIONS 只读）。

    路由显式覆盖：只读数据集 / 强制从库接口声明 `Depends(get_read_db)`，写 / 事务声明
    `Depends(get_write_db)` 或 `Depends(get_uow)`。
    """

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = set_read_only(is_read_method(scope.get("method")))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_read_only(token)


class RequestLoggingMiddleware(BaseObject):
    """请求日志中间件（纯 ASGI）：request_id / client_ip 上下文 + 单行访问日志（慢请求升 WARNING）。"""

    def __init__(self, app: ASGIApp, slow_request_ms: int = 1000) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
            slow_request_ms: 慢请求阈值（毫秒，取自 `[log].slow_request_ms`）。
        """
        self.app = app
        self.slow_request_ms = slow_request_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        request_token: Token[str | None] = set_current_request_id(request_id)
        client_token: Token[str | None] = set_current_client_ip(_client_ip(scope))
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_code = 0

        async def _send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, _send_with_status)
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._log_request(scope, status_code, duration_ms)
            reset_current_client_ip(client_token)
            reset_current_request_id(request_token)

    def _log_request(self, scope: Scope, status_code: int, duration_ms: float) -> None:
        """输出单行访问日志（排除清单内不记；超阈值升 WARNING）。

        链路 id 从请求态读取（`TraceIdMiddleware` 已复位上下文，请求态不受复位影响）。
        """
        path = str(scope.get("path", ""))
        if path in _EXCLUDED_PATHS:
            return
        logger = get_logger("app.request")
        fields: dict[str, object] = {
            "method": scope.get("method", ""),
            "path": path,
            "status": status_code,
            "duration_ms": duration_ms,
        }
        state: Mapping[str, object] = scope.get("state", {})
        if trace_id := state.get("trace_id"):
            fields["trace_id"] = trace_id
        if duration_ms >= self.slow_request_ms:
            logger.warning("slow_request", **fields)
        else:
            logger.info("request", **fields)


class EdgeGuardMiddleware(BaseObject):
    """边缘请求净化与信任边界中间件（纯 ASGI，先于租户解析）。

    - **无条件剥除**客户端伪造身份头（`STRIPPED_HEADERS`：用户 / 租户 / scope / 服务身份 / 网关标记）；
    - **信任**（`app.state.edge` 判定通过）时按 `EdgeIdentity` 回写规范身份头（含租户头），
      置请求态 `edge_identity` / `edge_trusted` 与 `current_user_id` 上下文；
    - **旁路防护**：`[edge].require_gateway_identity` 开且非豁免路径缺失可信身份 → 就地 401（不进入下游）；
    - **租户身份**：信任模式（旁路开关开）下剥离客户端 `X-Tenant-ID`，只采信网关注入的租户头；
      未开启时保持既有「客户端自选租户」行为不回归；
    - 未装配（`settings` / 信任插件缺失）按「未启用 + 不信任」处理：仍剥伪造头、不拒绝。
    """

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state: dict[str, object] = scope.setdefault("state", {})
        app_state = getattr(scope.get("app"), "state", None)
        settings = getattr(app_state, "settings", None)
        edge_settings = getattr(settings, "edge", None)
        trust: BaseEdgeTrust = getattr(app_state, "edge", None) or NullEdgeTrust()
        enforced = bool(getattr(edge_settings, "require_gateway_identity", False))
        exempt_paths = (
            edge_settings.exempt_paths
            if edge_settings is not None and getattr(edge_settings, "exempt_paths", None)
            else DEFAULT_EDGE_EXEMPT_PATHS
        )
        exempt = is_exempt_path(str(scope.get("path", "")), exempt_paths)

        decision = trust.evaluate(_raw_headers(scope))
        trusted = decision.trusted and decision.identity is not None
        if enforced and not exempt and not trusted:
            await build_error_response(scope, AuthError("未携带网关可信身份（网关旁路或未认证）"))(scope, receive, send)
            return

        identity = decision.identity if trusted else None
        drops = {
            GATEWAY_IDENTITY_HEADER.lower(),
            USER_ID_HEADER.lower(),
            USER_SCOPES_HEADER.lower(),
            SERVICE_IDENTITY_HEADER.lower(),
        }
        if enforced or trusted:
            drops.add(TENANT_ID_HEADER.lower())
        _rewrite_headers(scope, drops=drops, sets=_identity_headers(identity))

        state["edge_identity"] = identity
        state["edge_trusted"] = trusted
        user_token = set_current_user_id(identity.user_id if identity is not None else None)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user_id(user_token)


def _raw_headers(scope: Scope) -> dict[str, str]:
    """把 ASGI 原始头转为映射（值按 latin-1 解码，HTTP 头为 ascii 兼容）。"""
    return {key.decode("latin-1"): value.decode("latin-1") for key, value in scope.get("headers", [])}


def _identity_headers(identity: EdgeIdentity | None) -> dict[str, str]:
    """按可信身份生成规范身份头（缺失项不注入）。"""
    if identity is None:
        return {}
    headers: dict[str, str] = {}
    if identity.user_id is not None:
        headers[USER_ID_HEADER] = str(identity.user_id)
    if identity.tenant_code:
        headers[TENANT_ID_HEADER] = identity.tenant_code
    if identity.scopes:
        headers[USER_SCOPES_HEADER] = ",".join(identity.scopes)
    if identity.service_identity:
        headers[SERVICE_IDENTITY_HEADER] = identity.service_identity
    return headers


def _rewrite_headers(scope: Scope, *, drops: set[str], sets: Mapping[str, str]) -> None:
    """重建请求头：按小写名剥除 `drops`，再追加 `sets`（规范身份头）。"""
    kept = [(key, value) for key, value in scope.get("headers", []) if key.decode("latin-1").lower() not in drops]
    kept.extend((name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in sets.items())
    scope["headers"] = kept


def _client_ip(scope: Scope) -> str | None:
    """解析来源 IP（`X-Forwarded-For` 首值 → 连接地址）。"""
    forwarded = Headers(scope=scope).get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return str(client[0]) if client else None
