"""servicecall 能力域真实实现：`HttpServiceClient`（httpx 驱动，东西向直连不经网关）。

调用链：公开契约边界校验 → 出站身份处理（剥离入站 `Authorization`；按开关附自签服务 JWT）→ 调用侧限流 →
熔断放行 → httpx 请求（显式超时）→ 结果记录 / 重试 → 返回响应或抛 `ServiceUnavailableError`。韧性三件套
**复用**既有基座：`BaseCircuitBreaker`（放行 / 记录）、`BaseFallbackPolicy`（失败动作）、`BaseRateLimiter`（配额）。

**进程内直调**（07C `02_02`）：`request.local` 为真且应用已登记本地 ASGI（`bind_local_app`）时，
请求直接进入本应用 ASGI 栈（`httpx.ASGITransport`），不经网络、不重试、不参与熔断——同进程调用失败
是代码缺陷，重试只会重复副作用；路径 / 中间件 / 鉴权语义完全保留（仍经 `validate_service_request`
与出站身份处理）。

口径：外部 access token（用户 token）**一律不透传内部**——出站无条件剥离 `Authorization`；开启
`attach_service_token` 时改附 BMS 自签服务 JWT（`service_token` 能力域）。
"""

import asyncio
from typing import NoReturn, cast
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI
from starlette.types import ASGIApp

from bms_core.circuit.base import BaseCircuitBreaker
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.serialization import normalize_collections
from bms_core.fallback.base import BaseFallbackPolicy, FallbackAction
from bms_core.oauth.token import BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.servicecall.base import (
    BaseServiceClient,
    ServiceRequest,
    ServiceResponse,
    build_service_url,
    resolve_rate_limit_key,
    service_dependency,
    validate_service_request,
)

__all__ = ["AUTHORIZATION_HEADER", "HttpServiceClient"]

AUTHORIZATION_HEADER = "authorization"
"""授权头（小写；出站剥离入站授权头后按需附服务 JWT）。"""

LOCAL_BASE_URL = "http://local"
"""直调基址（ASGI 传输只取路径与查询串，主机名仅占位、不发包）。"""


class HttpServiceClient(BaseServiceClient):
    """服务间同步调用实现：httpx 发起请求，显式超时 / 重试 / 熔断 / 限流。

    - `transport` 供测试注入（`httpx.MockTransport` / `ASGITransport`）；默认真实网络。
    - 惰性建连：首次调用才创建 `httpx.AsyncClient`，`aclose()` 释放（经 `ResourceManager` 逆序回收）。
    - 韧性依赖经构造注入（装配工厂解析 `resolve_plugin` 实例）。
    - 本地直调：`bind_local_app()` 登记本应用后，`request.local` 的调用走 ASGI 传输（另一条惰性连接）。
    """

    plugin_name: str = "http"

    def __init__(
        self,
        *,
        circuit_breaker: BaseCircuitBreaker,
        fallback_policy: BaseFallbackPolicy,
        rate_limiter: BaseRateLimiter,
        base_url_template: str,
        token_issuer: BaseServiceTokenIssuer | None = None,
        attach_service_token: bool = False,
        caller: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            circuit_breaker: 熔断器（复用 `BaseCircuitBreaker`）。
            fallback_policy: 降级策略（复用 `BaseFallbackPolicy`）。
            rate_limiter: 限流器（复用 `BaseRateLimiter`）。
            base_url_template: 基址模板（占位 `{service}`）。
            token_issuer: 服务 JWT 签发者（开启出站换券时按**调用方**服务标识签发；缺省不附）。
            attach_service_token: 出站附服务 JWT 开关（默认关；生产开启）。
            caller: 调用方服务标识（服务 JWT 的 `sub` / `service`；东西向身份取调用方，
                空串时不附令牌——装配方须注入本服务标识）。
            transport: httpx 传输（缺省真实网络；测试注入替身）。
        """
        self._circuit = circuit_breaker
        self._fallback = fallback_policy
        self._rate_limiter = rate_limiter
        self._base_url_template = base_url_template
        self._token_issuer = token_issuer
        self._attach_service_token = attach_service_token
        self._caller = caller
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._local_app: ASGIApp | None = None
        self._local_client: httpx.AsyncClient | None = None

    def bind_local_app(self, app: FastAPI) -> None:
        """登记本进程应用（`request.local` 的调用直连本应用 ASGI 栈）。

        重复登记以后者为准；登记后惰性创建直调连接（首次直调才建）。已建连接在下次登记时作废
        （旧连接绑定旧应用，留着只会把请求送错应用）。

        Args:
            app: 应用实例。
        """
        self._local_app = app
        self._local_client = None

    async def aclose(self) -> None:
        """释放 httpx 连接（含直调连接；幂等）。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._local_client is not None:
            await self._local_client.aclose()
            self._local_client = None

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """发起服务间同步调用（见能力域口径）。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 调用响应（非 2xx 原样返回）。

        Raises:
            ParamError: 目标服务 / 路径 / 策略非法（10001）。
            RateLimitError: 调用侧限流超限（10005）。
            ServiceUnavailableError: 下游不可达 / 超时 / 重试耗尽 / 熔断断开（10007）。
        """
        validate_service_request(request)
        policy = request.policy
        dependency = service_dependency(request.service)
        if policy.rate_limit is not None:
            await self._rate_limiter.require(resolve_rate_limit_key(request), policy.rate_limit)
        if request.local and self._local_app is not None:
            return await self._send_local(request)
        if policy.circuit_breaker and not await self._circuit.allow(dependency):
            await self._unavailable(request, dependency, reason="circuit_open")
        url = build_service_url(request, self._base_url_template)
        headers = await self._outbound_headers(request)
        attempts = policy.max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._send(request, url, headers)
            except httpx.HTTPError as exc:
                if attempt + 1 < attempts:
                    await self._backoff(request, attempt)
                    continue
                if policy.circuit_breaker:
                    await self._circuit.record_failure(dependency)
                await self._unavailable(request, dependency, reason="transport", exc=exc)
            if response.status_code in policy.retry_statuses:
                if attempt + 1 < attempts:
                    await self._backoff(request, attempt)
                    continue
                if policy.circuit_breaker:
                    await self._circuit.record_failure(dependency)
                await self._unavailable(request, dependency, reason="status")
            if policy.circuit_breaker:
                await self._circuit.record_success(dependency)
            return response
        raise AssertionError("服务间调用重试循环不可达")  # pragma: no cover

    async def _outbound_headers(self, request: ServiceRequest) -> ConcurrentStableDict[str, str]:
        """构造出站请求头：剥离入站 `Authorization`，按开关附自签服务 JWT。

        东西向服务身份取**调用方**服务标识（`self._caller`）——目标服务的入站校验按
        `require_service("<调用方>")` 白名单判定；`caller` 未注入时不附令牌（不冒充目标服务）。

        Args:
            request: 调用请求。

        Returns:
            ConcurrentStableDict[str, str]: 出站请求头（外部 token 一律不透传）。
        """
        headers = ConcurrentStableDict(
            {name: value for name, value in (request.headers or {}).items() if name.lower() != AUTHORIZATION_HEADER}
        )
        if self._attach_service_token and self._token_issuer is not None and self._caller:
            # 惰性导入：`collaboration.domain_scope` 经 `grant` 反依赖 `servicecall.base`，顶层导入成环
            from bms_core.collaboration.domain_scope import instance_domains

            token = await self._token_issuer.issue(
                ServiceTokenSpec(
                    service=self._caller,
                    scopes=request.policy.scopes,
                    tenant_id=request.tenant_id,
                    domains=instance_domains(),
                )
            )
            if token.access_token:
                headers.set("Authorization", f"Bearer {token.access_token}")
        return headers

    async def _send(
        self, request: ServiceRequest, url: str, headers: ConcurrentStableDict[str, str]
    ) -> ServiceResponse:
        """执行单次 httpx 请求（显式超时；JSON 体与原始体二选一）。

        Args:
            request: 调用请求。
            url: 目标地址。
            headers: 出站请求头（已剥离入站授权头 / 已附服务 JWT）。

        Returns:
            ServiceResponse: 响应。

        Raises:
            httpx.HTTPError: 传输层 / 超时错误。
        """
        client = self._ensure_client()
        kwargs = self._request_kwargs(request, headers)
        response = await client.request(request.method.upper(), url, **kwargs)  # pyright: ignore[reportArgumentType]
        return _to_service_response(response)

    async def _send_local(self, request: ServiceRequest) -> ServiceResponse:
        """进程内直调：请求直接进入本应用 ASGI 栈（不重试、不参与熔断）。

        Args:
            request: 调用请求（`local=True`）。

        Returns:
            ServiceResponse: 本应用返回的响应（非 2xx 原样返回，与远程调用口径一致）。

        Raises:
            ServiceUnavailableError: 直调链路本身失败（10007 / 503）。
        """
        headers = await self._outbound_headers(request)
        url = f"{LOCAL_BASE_URL}{request.path}"
        if request.query:
            url = f"{url}?{urlencode(request.query)}"
        kwargs = self._request_kwargs(request, headers)
        local_client = self._ensure_local_client()
        try:
            response = await local_client.request(request.method.upper(), url, **kwargs)  # pyright: ignore[reportArgumentType]
        except httpx.HTTPError as exc:
            # 同进程调用失败属代码缺陷（应用内异常），重试只会重复副作用 → 直接按不可用上抛
            await self._unavailable(request, service_dependency(request.service), reason="local", exc=exc)
        return _to_service_response(response)

    def _request_kwargs(
        self, request: ServiceRequest, headers: ConcurrentStableDict[str, str]
    ) -> ConcurrentStableDict[str, object]:
        """构造 httpx 请求参数（超时 / 头 / 体；远程与直调共用）。

        Args:
            request: 调用请求。
            headers: 出站请求头（已剥离入站授权头 / 已附服务 JWT）。

        Returns:
            ConcurrentStableDict[str, object]: httpx 请求关键字参数。
        """
        kwargs: ConcurrentStableDict[str, object] = ConcurrentStableDict({"timeout": request.policy.timeout})
        if headers:
            kwargs.set("headers", dict(headers))
        if request.json_body is not None:
            # 请求体常为集合体系对象（`ConcurrentStableDict` 等），标准 `json.dumps` 不认（非 `dict` 子类）
            # → 出站前归一为内建容器（2026-10-04 本地链路实测修复）。
            kwargs.set("json", normalize_collections(request.json_body))
        elif request.content is not None:
            kwargs.set("content", request.content)
        return kwargs

    def _ensure_client(self) -> httpx.AsyncClient:
        """惰性创建 httpx 客户端（复用连接）。

        Returns:
            httpx.AsyncClient: 客户端实例。
        """
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self._transport)
        return self._client

    def _ensure_local_client(self) -> httpx.AsyncClient:
        """惰性创建直调客户端（ASGI 传输；绑定本应用，不发包）。

        Returns:
            httpx.AsyncClient: 直调客户端实例。
        """
        if self._local_client is None:
            self._local_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=cast("ASGIApp", self._local_app)))
        return self._local_client

    async def _backoff(self, request: ServiceRequest, attempt: int) -> None:
        """指数退避等待（退避基数为 0 时不等待）。

        Args:
            request: 调用请求（取退避基数）。
            attempt: 已完成的尝试序号（从 0 起）。
        """
        base = request.policy.retry_backoff
        if base > 0:
            await asyncio.sleep(base * (2**attempt))

    async def _unavailable(
        self,
        request: ServiceRequest,
        dependency: str,
        *,
        reason: str,
        exc: BaseException | None = None,
    ) -> NoReturn:
        """解析降级动作并抛服务不可用（动作随 `data` 回传，调用方按动作处理）。

        Args:
            request: 调用请求。
            dependency: 依赖标识（`service:<key>`）。
            reason: 失败原因（transport / status / circuit_open）。
            exc: 触发降级的异常（可选）。

        Raises:
            ServiceUnavailableError: 服务不可用（10007 / 503）。
        """
        action = FallbackAction.RAISE
        try:
            action = await self._fallback.resolve(dependency, exc=exc)
        except Exception:
            action = FallbackAction.RAISE
        raise ServiceUnavailableError(
            f"服务不可用：{request.service}（{reason}）",
            data={
                "service": request.service,
                "dependency": dependency,
                "reason": reason,
                "fallback": action.value,
            },
        )


def _to_service_response(response: httpx.Response) -> ServiceResponse:
    """把 httpx 响应转成契约响应（远程与直调共用）。

    Args:
        response: httpx 响应。

    Returns:
        ServiceResponse: 服务间调用响应。
    """
    return ServiceResponse(
        status_code=response.status_code,
        headers=ConcurrentStableFrozenDict(response.headers),
        content=response.content,
    )
