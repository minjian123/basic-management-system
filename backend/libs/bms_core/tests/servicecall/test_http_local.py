"""进程内直调（07C `02_02`；Kiwi 2369）：`mode=local` 的调用走本应用 ASGI 栈。

覆盖详细设计 §4.7：直调成功且不发包、出站身份复用、未登记应用回落 HTTP、
直调不重试不熔断、传输异常按不可用上抛、重复登记以后者为准、释放后可重建。
"""

import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bms_core.circuit.base import BaseCircuitBreaker, CircuitState
from bms_core.circuit.null import NullCircuitBreaker
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.fallback.null import NullFallbackPolicy
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.base import OAuthToken
from bms_core.oauth.token import BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.ratelimit.null import NullRateLimiter
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_core.servicecall.http import HttpServiceClient

pytestmark = pytest.mark.kiwi_id(2369)

_BASE_TEMPLATE = "http://{service}:8000"
_PATH = "/api/v1/demo/ping"
"""直调目标路径（`/api/v1` 前缀是公开契约面的硬要求）。"""


class _RecordingCircuit(BaseCircuitBreaker):
    """可观测熔断替身：记录放行 / 成功 / 失败（验证直调不参与熔断）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.successes: ConcurrentStableList[str] = ConcurrentStableList()
        self.failures: ConcurrentStableList[str] = ConcurrentStableList()

    async def allow(self, dependency: str) -> bool:
        """恒定放行。

        Args:
            dependency: 依赖标识（未使用）。

        Returns:
            bool: True。
        """
        del dependency
        return True

    async def record_success(self, dependency: str) -> None:
        """记录成功。

        Args:
            dependency: 依赖标识。
        """
        self.successes.add(dependency)

    async def record_failure(self, dependency: str) -> None:
        """记录失败。

        Args:
            dependency: 依赖标识。
        """
        self.failures.add(dependency)

    async def state(self, dependency: str) -> CircuitState:
        """恒定闭合。

        Args:
            dependency: 依赖标识（未使用）。

        Returns:
            CircuitState: 闭合。
        """
        del dependency
        return CircuitState.CLOSED


def _app(*, status_code: int = 200, raise_exc: BaseException | None = None, tag: str = "a") -> FastAPI:
    """构造最小应用（端点回显收到的身份头，可注入异常模拟传输故障）。

    Args:
        status_code: 端点状态码。
        raise_exc: 非空时端点抛该异常（模拟直调链路故障）。
        tag: 应用标识（验证重复登记替换）。

    Returns:
        FastAPI: 应用实例。
    """
    app = FastAPI()

    @app.get(_PATH)
    async def ping(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """回显应用标识与入站身份头。

        Args:
            request: 请求对象。

        Returns:
            JSONResponse: `{tag, authorization}`。
        """
        if raise_exc is not None:
            raise raise_exc
        return JSONResponse(
            {"tag": tag, "authorization": request.headers.get("authorization", "")},
            status_code=status_code,
        )

    return app


def _client(
    *,
    local_app: FastAPI | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    circuit: BaseCircuitBreaker | None = None,
    token_issuer: BaseServiceTokenIssuer | None = None,
    attach_service_token: bool = False,
) -> HttpServiceClient:
    """构造服务间调用客户端（缺省占位韧性；可注入本地应用 / 传输替身 / 身份签发）。

    Args:
        local_app: 已登记的本地应用（None 表示未登记）。
        transport: 远程调用传输替身（None 表示真实网络）。
        circuit: 熔断器（None 取占位实现）。
        token_issuer: 服务 JWT 签发者（None 表示不签发）。
        attach_service_token: 是否附服务 JWT。

    Returns:
        HttpServiceClient: 客户端实例。
    """
    client = HttpServiceClient(
        circuit_breaker=circuit or NullCircuitBreaker(),
        fallback_policy=NullFallbackPolicy(),
        rate_limiter=NullRateLimiter(),
        base_url_template=_BASE_TEMPLATE,
        token_issuer=token_issuer,
        attach_service_token=attach_service_token,
        caller="identity",
        transport=transport,
    )
    if local_app is not None:
        client.bind_local_app(local_app)
    return client


def _request(**overrides: object) -> ServiceRequest:
    """构造直调请求（缺省 `local=True`）。

    Args:
        overrides: 字段覆盖。

    Returns:
        ServiceRequest: 调用请求。
    """
    base: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"service": "identity", "method": "GET", "path": _PATH, "local": True}
    )
    base.update(overrides.items())
    return ServiceRequest(**base)  # pyright: ignore[reportArgumentType]


async def test_local_request_reaches_application_without_network() -> None:
    """已登记本地应用：直调命中本应用端点（未注入传输，能成功即证明未走网络）；连接复用。"""
    client = _client(local_app=_app(tag="local"))

    first = await client.call(_request())
    second = await client.call(_request())

    assert first.status_code == 200
    assert json.loads(first.content) == {"tag": "local", "authorization": ""}
    assert second.content == first.content


async def test_local_request_reuses_outbound_identity() -> None:
    """直调复用出站身份处理：入站 `Authorization` 被剥离，按开关附本服务签发 JWT。"""
    client = _client(local_app=_app(), token_issuer=_TokenIssuer(), attach_service_token=True)

    response = await client.call(
        _request(headers=ConcurrentStableFrozenDict({"Authorization": "Bearer user-token", "X-Trace": "t1"}))
    )

    assert json.loads(response.content)["authorization"] == "Bearer service-jwt"


async def test_local_request_falls_back_to_http_without_bound_app() -> None:
    """未登记本地应用：`local=True` 仍按普通 HTTP 发出（自调用本服务，行为同改造前）。"""
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.add(str(request.url))
        return httpx.Response(200, content=b"remote")

    response = await _client(transport=httpx.MockTransport(handler)).call(_request())

    assert response.content == b"remote"
    assert seen.to_list() == [f"http://identity:8000{_PATH}"]


async def test_local_request_does_not_retry_or_touch_circuit() -> None:
    """直调非 2xx 原样返回：不重试（503 只发生一次）、不记录熔断成功 / 失败。"""
    circuit = _RecordingCircuit()
    client = _client(local_app=_app(status_code=503), circuit=circuit)

    response = await client.call(_request())

    assert response.status_code == 503
    assert list(circuit.failures) == []
    assert list(circuit.successes) == []


async def test_local_request_transport_error_raises_unavailable() -> None:
    """直调链路抛传输异常：按服务不可用上抛（10007），不静默吞掉。"""
    client = _client(local_app=_app(raise_exc=httpx.ReadTimeout("boom")))

    with pytest.raises(ServiceUnavailableError) as captured:
        await client.call(_request())

    assert captured.value.code == 10007


async def test_rebinding_replaces_local_application() -> None:
    """重复登记以后者为准：旧连接作废，请求打到新应用。"""
    client = _client(local_app=_app(tag="first"))
    assert json.loads((await client.call(_request())).content)["tag"] == "first"

    client.bind_local_app(_app(tag="second"))

    assert json.loads((await client.call(_request())).content)["tag"] == "second"


async def test_close_releases_local_connection_and_can_rebuild() -> None:
    """`aclose()` 释放直调连接后仍可再次直调（惰性重建），重复关闭幂等。"""
    client = _client(local_app=_app())
    await client.call(_request())

    await client.aclose()
    await client.aclose()

    assert (await client.call(_request())).status_code == 200


async def test_local_request_keeps_query_string() -> None:
    """直调保留查询串（路径语义与远程调用一致）。"""
    app = FastAPI()

    @app.get(_PATH)
    async def ping(page: str = "") -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """回显查询参数。

        Args:
            page: 页码。

        Returns:
            JSONResponse: `{page}`。
        """
        return JSONResponse({"page": page})

    response = await _client(local_app=app).call(_request(query=ConcurrentStableFrozenDict({"page": "2"})))

    assert json.loads(response.content) == {"page": "2"}


class _TokenIssuer(BaseServiceTokenIssuer):
    """服务 JWT 签发替身：记录签发规格并固定返回占位令牌。"""

    plugin_name = "local_stub"

    def __init__(self) -> None:
        """初始化空签发记录。"""
        self.specs: ConcurrentStableList[ServiceTokenSpec] = ConcurrentStableList()

    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        """返回占位令牌。

        Args:
            spec: 签发规格。

        Returns:
            OAuthToken: 占位令牌。
        """
        self.specs.add(spec)
        return OAuthToken(access_token="service-jwt")

    def jwks(self) -> ConcurrentStableDict[str, object]:
        """公钥集（占位为空）。

        Returns:
            ConcurrentStableDict[str, object]: 空密钥集。
        """
        return ConcurrentStableDict({"keys": []})

    def verify(self, token: str) -> IdentityClaims:
        """校验令牌（占位恒返回固定身份）。

        Args:
            token: 令牌串（未使用）。

        Returns:
            IdentityClaims: 固定身份声明。
        """
        del token
        return IdentityClaims(subject="stub")


def test_service_response_conversion_shared() -> None:
    """远程与直调共用响应转换（头 / 体 / 状态码原样保留）。"""
    from bms_core.servicecall.http import _to_service_response  # pyright: ignore[reportPrivateUsage]

    response = _to_service_response(httpx.Response(201, headers={"x-a": "1"}, content=b"ok"))

    assert (response.status_code, response.content) == (201, b"ok")
    assert isinstance(response, ServiceResponse)
    assert response.headers["x-a"] == "1"
