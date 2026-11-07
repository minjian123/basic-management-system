"""请求操作审计中间件（纯 ASGI）：捕获操作上下文 → 脱敏 → 写发件箱（06_01）。

- **记录范围**：`[audit_log].record_methods`（缺省写方法）全记；读方法由端点声明
  `scope["state"]["audit_read"] = True` 另记；探针 / 文档 / `[audit_log].exclude_paths` 不记。
- **action**：`require_permission` 把权限码写入 `scope["state"]["audit_action"]`（拒绝也留痕）；
  未挂权限码的端点回落 `{module}:{方法动词}`（`POST→create` / `PUT|PATCH→update` / `DELETE→delete` / `GET→query`）。
- **参数**：仅 `application/json` / `application/x-www-form-urlencoded` 且体积不超
  `[audit_log].max_param_bytes` 时缓冲请求体（原样回放下游）；超限 / multipart 只记路径与查询串。
- **脱敏**：查询串与请求体统一经 `core.logging.mask_sensitive`（内置名单 ∪ `[log]` 追加），敏感值 `***`。
- **失败不阻塞**：发件箱写入失败只告警；未捕获异常记录 `error_msg` 后原样抛出。
"""

from __future__ import annotations

import json
import time
from json import JSONDecodeError
from typing import cast
from urllib.parse import parse_qsl

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bms_core.api.middleware import BaseMiddleware
from bms_core.audit.emit import AuditEventEmitter
from bms_core.audit.events import build_operation_event
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.config import AuditLogSettings, Settings
from bms_core.core.context import get_current_user_id, get_scope_context
from bms_core.core.logging import mask_sensitive
from bms_core.db.tenant import TenantContext

__all__ = ["ADD_VERB", "OperationAuditMiddleware"]

_EXCLUDED_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/docs", "/redoc", "/openapi.json"})
"""探针与文档路径（任何级别不记）。"""

_JSON_TYPE = "application/json"
_FORM_TYPE = "application/x-www-form-urlencoded"

ADD_VERB: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict(
    {
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
        "GET": "query",
    }
)
"""无权限码端点的动作回落（HTTP 方法 → 动词）。"""


def _client_ip(scope: Scope) -> str | None:
    """解析来源 IP（`X-Forwarded-For` 首值 → 连接地址）。"""
    forwarded = Headers(scope=scope).get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return str(client[0]) if client else None


def _summary_path(scope: Scope) -> str:
    """取路由模板路径（无匹配回落原始路径）。"""
    route = scope.get("route")
    return str(getattr(route, "path", "") or scope.get("path", ""))


def _module_of(scope: Scope, action: str | None) -> tuple[str, str]:
    """解析模块与动作。

    Args:
        scope: ASGI 作用域。
        action: 权限码（请求态记录；可为空）。

    Returns:
        tuple[str, str]: （模块，动作）。
    """
    if action:
        business, _, verb = action.partition(":")
        if business:
            return business, action if verb else f"{business}:{ADD_VERB.get(str(scope.get('method')), 'query')}"
    path = str(scope.get("path", ""))
    segments = [segment for segment in path.split("/") if segment and segment not in {"api", "v1"}]
    module = segments[0] if segments else "unknown"
    verb = ADD_VERB.get(str(scope.get("method", "")).upper(), "query")
    return module, f"{module}:{verb}"


def _mask_query(raw: str) -> str | None:
    """查询串脱敏（解析为映射后序列化）。

    Args:
        raw: 原始查询串（不含 `?`）。

    Returns:
        str | None: 脱敏后的 JSON 字符串；空串返回 None。
    """
    if not raw:
        return None
    pairs = parse_qsl(raw, keep_blank_values=True)
    if not pairs:
        return None
    masked = mask_sensitive({key: value for key, value in pairs})
    return json.dumps(masked, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mask_body(content_type: str, body: bytes) -> str | None:
    """请求体脱敏（JSON / 表单）。

    Args:
        content_type: 小写化的 Content-Type（已去参数）。
        body: 请求体字节。

    Returns:
        str | None: 脱敏后的 JSON 字符串；非支持类型 / 解析失败返回 None。
    """
    if not body:
        return None
    text = body.decode("utf-8", errors="replace")
    if content_type == _JSON_TYPE:
        try:
            loaded: object = json.loads(text)
        except JSONDecodeError:
            return None
        masked = mask_sensitive(loaded)
        return json.dumps(masked, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if content_type == _FORM_TYPE:
        pairs = parse_qsl(text, keep_blank_values=True)
        masked = mask_sensitive({key: value for key, value in pairs})
        return json.dumps(masked, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return None


class OperationAuditMiddleware(BaseMiddleware):
    """操作审计中间件：响应结束后把一条审计事件写入发件箱。"""

    def __init__(self, app: ASGIApp, *, settings: AuditLogSettings, app_settings: Settings) -> None:
        """初始化。

        Args:
            app: 下游 ASGI 应用。
            settings: 审计日志参数（`[audit_log]`）。
            app_settings: 应用配置（中间件构造发件箱时取实现选择）。
        """
        self.app = app
        self._settings = settings
        self._app_settings = app_settings
        self._emitter: AuditEventEmitter | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP / 关闭 / 排除路径直通）。

        Args:
            scope: ASGI 作用域。
            receive: ASGI 接收通道。
            send: ASGI 发送通道。
        """
        if scope["type"] != "http" or not self._track(scope):
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        headers = Headers(scope=scope)
        content_type = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        content_length = self._content_length(headers)
        capture_body = content_type in {_JSON_TYPE, _FORM_TYPE} and content_length <= self._settings.max_param_bytes
        chunks: ConcurrentStableList[bytes] = ConcurrentStableList()
        captured = 0
        overflow = False
        start = time.perf_counter()
        status = 0
        error: str | None = None

        async def _receive() -> Message:
            nonlocal captured, overflow
            message = await receive()
            if message["type"] == "http.request" and capture_body and not overflow:
                chunk = cast("bytes", message.get("body", b""))
                if chunk:
                    captured += len(chunk)
                    if captured > self._settings.max_param_bytes:
                        overflow = True
                        chunks.clear()
                    else:
                        chunks.append(chunk)
            return message

        async def _send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, _receive if capture_body else receive, _send)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            await self._emit(
                scope,
                method=method,
                status=status,
                start=start,
                content_type=content_type,
                body=b"" if overflow else b"".join(chunks),
                error=error,
            )

    def _track(self, scope: Scope) -> bool:
        """是否需要跟踪该请求（排除探针 / 文档 / 配置排除路径）。"""
        if not self._settings.enabled:
            return False
        path = str(scope.get("path", ""))
        if path in _EXCLUDED_PATHS:
            return False
        return not any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._settings.exclude_paths)

    @staticmethod
    def _content_length(headers: Headers) -> int:
        """取 Content-Length（缺失按 0 处理，交由实际累计判超限）。"""
        raw = headers.get("content-length")
        if not raw:
            return 0
        try:
            return int(raw)
        except ValueError:
            return 0

    def _emitter_for(self, scope: Scope) -> AuditEventEmitter | None:
        """懒建发射器（应用 state 在首个请求时已就绪）。"""
        if self._emitter is not None:
            return self._emitter
        app = scope.get("app")
        state = getattr(app, "state", None)
        registry = getattr(state, "engine_registry", None)
        factory = getattr(state, "session_factory", None)
        if registry is None or factory is None:  # pragma: no cover - 装配缺失属编码错误，按不记处理
            return None
        self._emitter = AuditEventEmitter(
            registry=registry,
            session_factory=factory,
            settings=self._app_settings,
        )
        return self._emitter

    async def _emit(
        self,
        scope: Scope,
        *,
        method: str,
        status: int,
        start: float,
        content_type: str,
        body: bytes,
        error: str | None,
    ) -> None:
        """组装并发射一条操作审计事件（失败只告警）。"""
        state = cast("dict[str, object]", scope.get("state") or {})
        if method not in self._settings.record_methods and not state.get("audit_read"):
            return
        emitter = self._emitter_for(scope)
        if emitter is None:  # pragma: no cover - 同 _emitter_for
            return
        tenant = state.get("tenant")
        tenant_id = (
            str(tenant.tenant_id) if isinstance(tenant, TenantContext) and tenant.tenant_id is not None else None
        )
        if tenant_id is None and state.get("tenant_id") is not None:
            tenant_id = str(state["tenant_id"])
        action_value = state.get("audit_action")
        action = action_value if isinstance(action_value, str) and action_value else None
        module, action = _module_of(scope, action)
        if status == 0 and error is not None:
            status = 500  # 异常未转响应（无 response.start）：按 500 记录
        error_msg = error if error is not None else (f"HTTP {status}" if status >= 400 else None)
        cost = round((time.perf_counter() - start) * 1000)
        identity = state.get("edge_identity")
        identity_user = getattr(identity, "user_id", None)
        user_id = identity_user if isinstance(identity_user, int) else get_current_user_id()
        scope_context = get_scope_context()
        event = build_operation_event(
            tenant_id=tenant_id,
            user_id=user_id,
            username=None,
            module=module,
            action=action,
            method=method,
            path=_summary_path(scope),
            query=_mask_query(str(scope.get("query_string", b"").decode("latin-1"))),
            params=_mask_body(content_type, body),
            ip=_client_ip(scope),
            user_agent=Headers(scope=scope).get("user-agent"),
            cost_time=cost,
            status=status,
            error_msg=error_msg,
            trace_id=cast("str | None", state.get("trace_id")),
            module_key=scope_context.module_key if scope_context is not None else None,
            resource_key=scope_context.resource_key if scope_context is not None else None,
        )
        await emitter.emit(event)
