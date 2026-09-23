"""servicecall 能力域真实实现：`HttpServiceClient`（httpx 驱动，东西向直连不经网关）。

调用链：公开契约边界校验 → 调用侧限流 → 熔断放行 → httpx 请求（显式超时）→ 结果记录 / 重试 →
返回响应或抛 `ServiceUnavailableError`。韧性三件套**复用**既有基座：
`BaseCircuitBreaker`（放行 / 记录）、`BaseFallbackPolicy`（失败动作）、`BaseRateLimiter`（配额）。
"""

import asyncio
from typing import NoReturn

import httpx

from bms_core.circuit.base import BaseCircuitBreaker
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.fallback.base import BaseFallbackPolicy, FallbackAction
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

__all__ = ["HttpServiceClient"]


class HttpServiceClient(BaseServiceClient):
    """服务间同步调用实现：httpx 发起请求，显式超时 / 重试 / 熔断 / 限流。

    - `transport` 供测试注入（`httpx.MockTransport` / `ASGITransport`）；默认真实网络。
    - 惰性建连：首次调用才创建 `httpx.AsyncClient`，`aclose()` 释放（经 `ResourceManager` 逆序回收）。
    - 韧性依赖经构造注入（装配工厂解析 `resolve_plugin` 实例）。
    """

    plugin_name: str = "http"

    def __init__(
        self,
        *,
        circuit_breaker: BaseCircuitBreaker,
        fallback_policy: BaseFallbackPolicy,
        rate_limiter: BaseRateLimiter,
        base_url_template: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            circuit_breaker: 熔断器（复用 `BaseCircuitBreaker`）。
            fallback_policy: 降级策略（复用 `BaseFallbackPolicy`）。
            rate_limiter: 限流器（复用 `BaseRateLimiter`）。
            base_url_template: 基址模板（占位 `{service}`）。
            transport: httpx 传输（缺省真实网络；测试注入替身）。
        """
        self._circuit = circuit_breaker
        self._fallback = fallback_policy
        self._rate_limiter = rate_limiter
        self._base_url_template = base_url_template
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        """释放 httpx 连接（幂等）。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

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
        if policy.circuit_breaker and not await self._circuit.allow(dependency):
            await self._unavailable(request, dependency, reason="circuit_open")
        url = build_service_url(request, self._base_url_template)
        attempts = policy.max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._send(request, url)
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

    async def _send(self, request: ServiceRequest, url: str) -> ServiceResponse:
        """执行单次 httpx 请求（显式超时；JSON 体与原始体二选一）。

        Args:
            request: 调用请求。
            url: 目标地址。

        Returns:
            ServiceResponse: 响应。

        Raises:
            httpx.HTTPError: 传输层 / 超时错误。
        """
        client = self._ensure_client()
        kwargs: dict[str, object] = {"timeout": request.policy.timeout}
        if request.headers:
            kwargs["headers"] = dict(request.headers)
        if request.json_body is not None:
            kwargs["json"] = request.json_body
        elif request.content is not None:
            kwargs["content"] = request.content
        response = await client.request(request.method.upper(), url, **kwargs)  # pyright: ignore[reportArgumentType]
        return ServiceResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
        )

    def _ensure_client(self) -> httpx.AsyncClient:
        """惰性创建 httpx 客户端（复用连接）。

        Returns:
            httpx.AsyncClient: 客户端实例。
        """
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self._transport)
        return self._client

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
