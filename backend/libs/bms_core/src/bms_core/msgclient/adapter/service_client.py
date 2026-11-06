"""`BaseServiceClient` 的消息平台实现：`call(ServiceRequest)` 走 `/rpc/{service}/{method}`（07B `06_01` 步 2）。

**只做翻译，不做韧性**：重试 / 退避 / 预算 / 熔断 / 幂等键全在 `bms_core.msgclient`（04-4）；
本类负责端口字段 → 帧字段（方法名归一化、请求体、`query.<name>` 透传、身份与租户）、以及帧错误 →
bms 异常的分派。适配层再包一层重试循环会让重试次数相乘、`backoff_ms` 失真。

**`local` 被忽略**：`ServiceRequest.local` 的语义是「目标在本进程，走 ASGI 直连」——
RPC 通道没有对应能力（那需要本服务在 RPC 注册表里注册方法，属后续阶段）。忽略而不是报错：
报错会让所有带 `mode=local` 的调用在切换时直接失败，而多数 `local` 调用在远端同样可达。
差异已登记（详细设计 §3.9.4「本轮已知差异」）。

**流式不暴露**：`RpcStream` 不进重试层，端口也没有流式方法；多出来一个 `stream()` 只会诱导
业务代码依赖具体实现。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.msgclient.adapter.mapping import method_of, query_headers, request_payload, to_bms_error
from bms_core.msgclient.adapter.policy import circuit_scope, deadline_ms_of, release_circuit, retry_policy_of
from bms_core.msgclient.rpc import RpcCallError, RpcClient
from bms_core.oauth.token import BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.servicecall.base import (
    AUTHORIZATION_HEADER,
    BaseServiceClient,
    ServiceRequest,
    ServiceResponse,
    resolve_rate_limit_key,
    validate_service_request,
)
from bms_core.tracing.base import current_trace_id

__all__ = ["MsgServiceClient"]

_STATUS_OK = 200
"""RPC 成功响应对应的 `ServiceResponse.status_code`（非 2xx 在帧层已成错误帧，不会走到回填）。"""


class MsgServiceClient(BaseServiceClient):
    """服务间同步调用实现（消息平台 RPC 通道）。

    - 端口校验与 `http` 通道同一道闸（`validate_service_request`）：目标须在服务目录启用、
      路径须属 `/api/v1` 公开面、策略合法；越界即 `ParamError`，不发起调用。
    - 韧性依赖经构造注入：`RpcClient`（含实例地址 / 传输 / 熔断）、限流器、服务 JWT 签发者。
    - 生命周期：`aclose()` 释放底层传输（经 `ResourceManager` 逆序回收）。
    """

    plugin_name: str = "msg"

    def __init__(
        self,
        *,
        rpc_client: RpcClient,
        rate_limiter: BaseRateLimiter,
        token_issuer: BaseServiceTokenIssuer | None = None,
        attach_service_token: bool = False,
        caller: str = "",
        tenant: str | None = None,
    ) -> None:
        """初始化。

        Args:
            rpc_client: RPC 客户端（实例地址、传输、重试与熔断已由工厂装配）。
            rate_limiter: 调用侧限流器（复用 `BaseRateLimiter`）。
            token_issuer: 服务 JWT 签发者（开启出站换券时按**调用方**服务标识签发；缺省不附）。
            attach_service_token: 出站附服务 JWT 开关（与 `http` 通道同款，默认关）。
            caller: 调用方服务标识（服务 JWT 的 `sub` / `service`；空串时不附令牌）。
            tenant: 缺省租户编码（逐调用 `request.tenant_id` 优先）。
        """
        self._rpc = rpc_client
        self._rate_limiter = rate_limiter
        self._token_issuer = token_issuer
        self._attach_service_token = attach_service_token
        self._caller = caller
        self._tenant = tenant

    async def aclose(self) -> None:
        """释放底层传输（连接池 / 后台任务；幂等）。"""
        await self._rpc.aclose()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """发起服务间同步调用（经 RPC 一元通道）。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 调用响应（`status_code` 恒 200，`content` 为结果帧载荷）。

        Raises:
            ParamError: 目标服务 / 路径 / 策略非法，或请求体二选一冲突（10001）。
            RateLimitError: 调用侧限流超限（10005）或服务端限流码 `350005`。
            BizError: 服务端业务拒绝（保留原始码）。
            ServiceUnavailableError: 下游不可达 / 超时 / 重试耗尽 / 熔断断开 / 服务端 bug（10007）。
        """
        validate_service_request(request)
        policy = request.policy
        if policy.rate_limit is not None:
            await self._rate_limiter.require(resolve_rate_limit_key(request), policy.rate_limit)
        headers = await self._outbound_headers(request)
        token = circuit_scope(policy)
        try:
            reply = await self._rpc.call(
                request.service,
                method_of(request.path),
                request_payload(request),
                headers,
                trace_id=current_trace_id(),
                caller=self._caller or None,
                deadline_ms=deadline_ms_of(policy),
                tenant=request.tenant_id or self._tenant,
                policy=retry_policy_of(policy),
            )
        except RpcCallError as exc:
            raise to_bms_error(exc) from exc
        finally:
            release_circuit(token)
        return ServiceResponse(
            status_code=_STATUS_OK,
            headers=ConcurrentStableFrozenDict[str, str](reply.headers),
            content=reply.payload,
        )

    async def _outbound_headers(self, request: ServiceRequest) -> ConcurrentStableDict[str, str]:
        """构造帧头：剥离入站授权头 → 透传查询串 → 按开关附服务 JWT。

        东西向服务身份取**调用方**服务标识（`self._caller`）——目标服务的入站校验按
        `require_service("<调用方>")` 白名单判定；`caller` 未注入时不附令牌（不冒充目标服务）。

        Args:
            request: 调用请求。

        Returns:
            ConcurrentStableDict[str, str]: 帧头（外部 access token 一律不透传）。
        """
        headers: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for name, value in (request.headers or {}).items():
            if name.lower() == AUTHORIZATION_HEADER:
                continue
            headers.set(name, value)
        for name, value in query_headers(request.query).items():
            headers.set(name, value)
        if self._attach_service_token and self._token_issuer is not None and self._caller:
            # 惰性导入：`collaboration.domain_scope` 经 `grant` 反依赖 `servicecall.base`，顶层导入成环
            from bms_core.collaboration.domain_scope import instance_domains

            token = await self._token_issuer.issue(
                ServiceTokenSpec(
                    service=self._caller,
                    scopes=request.policy.scopes,
                    tenant_id=request.tenant_id or self._tenant,
                    domains=instance_domains(),
                )
            )
            if token.access_token:
                headers.set("Authorization", f"Bearer {token.access_token}")
        return headers
