"""服务间同步调用能力域测试（Kiwi 2169）：公开契约边界 / 超时重试 / 熔断 / 限流 / 占位 / 依赖解析。"""

import json
from collections.abc import Callable
from typing import Annotated, cast

import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from support_app import ApplicationFactory, lifespan

from bms_core.api.deps import get_service_client
from bms_core.circuit.base import BaseCircuitBreaker, CircuitState
from bms_core.circuit.null import NullCircuitBreaker
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.exceptions import ParamError, RateLimitError, ServiceUnavailableError
from bms_core.fallback.base import BaseFallbackPolicy, FallbackAction
from bms_core.fallback.null import NullFallbackPolicy
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.base import OAuthToken
from bms_core.oauth.token import BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitDecision, RateLimitRule
from bms_core.ratelimit.null import NullRateLimiter
from bms_core.servicecall.base import (
    DEFAULT_CALL_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    BaseServiceClient,
    ServiceCallPolicy,
    ServiceRequest,
    ServiceResponse,
    build_service_url,
    service_dependency,
    validate_service_request,
)
from bms_core.servicecall.http import HttpServiceClient
from bms_core.servicecall.null import NullServiceClient

_BASE_TEMPLATE = "http://{service}:8000"


class RecordingCircuit(BaseCircuitBreaker):
    """可观测熔断替身（记录放行 / 成功 / 失败）。"""

    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.successes: list[str] = []
        self.failures: list[str] = []

    async def allow(self, dependency: str) -> bool:
        return self.allowed

    async def record_success(self, dependency: str) -> None:
        self.successes.append(dependency)

    async def record_failure(self, dependency: str) -> None:
        self.failures.append(dependency)

    async def state(self, dependency: str) -> CircuitState:
        return CircuitState.CLOSED


class StubFallback(BaseFallbackPolicy):
    """固定动作降级替身。"""

    def __init__(self, action: FallbackAction = FallbackAction.RAISE) -> None:
        self.action = action

    async def resolve(self, dependency: str, *, exc: BaseException | None = None) -> FallbackAction:
        return self.action


class ExplodingFallback(BaseFallbackPolicy):
    """降级解析故障替身（模拟降级策略自身异常）。"""

    async def resolve(self, dependency: str, *, exc: BaseException | None = None) -> FallbackAction:
        raise RuntimeError("fallback down")


class StubRateLimiter(BaseRateLimiter):
    """固定判定限流替身。"""

    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.checked: list[str] = []

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        self.checked.append(key)
        return RateLimitDecision(allowed=self.allowed, limit=rule.limit, remaining=0, reset_after=rule.window)


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    circuit: BaseCircuitBreaker | None = None,
    fallback: BaseFallbackPolicy | None = None,
    rate_limiter: BaseRateLimiter | None = None,
    token_issuer: BaseServiceTokenIssuer | None = None,
    attach_service_token: bool = False,
) -> HttpServiceClient:
    """构造带 MockTransport 的 HttpServiceClient（缺省占位韧性）。"""
    return HttpServiceClient(
        circuit_breaker=circuit or NullCircuitBreaker(),
        fallback_policy=fallback or NullFallbackPolicy(),
        rate_limiter=rate_limiter or NullRateLimiter(),
        base_url_template=_BASE_TEMPLATE,
        token_issuer=token_issuer,
        attach_service_token=attach_service_token,
        transport=httpx.MockTransport(handler),
    )


def _request(**overrides: object) -> ServiceRequest:
    """构造标准调用请求（platform 服务公开路径）。"""
    base: dict[str, object] = {"service": "platform", "method": "GET", "path": "/api/v1/modules"}
    base.update(overrides)
    return ServiceRequest(**base)  # pyright: ignore[reportArgumentType]


@pytest.mark.kiwi_id(2169)
def test_inheritance_and_defaults() -> None:
    """契约继承链、能力键与策略默认值。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseServiceClient, BaseCapability)
    assert issubclass(HttpServiceClient, BaseServiceClient)
    assert issubclass(NullServiceClient, BaseNullObject)
    assert BaseServiceClient.key == "service_client"
    assert DEFAULT_CALL_TIMEOUT == 5.0
    assert DEFAULT_MAX_RETRIES == 2
    policy = ServiceCallPolicy()
    assert policy.timeout == 5.0
    assert policy.max_retries == 2
    assert policy.circuit_breaker is True
    assert policy.rate_limit is None


@pytest.mark.kiwi_id(2169)
def test_build_url_and_dependency() -> None:
    """基址模板拼装（含查询串）与依赖标识。"""
    url = build_service_url(_request(query={"page": "1", "size": "20"}), _BASE_TEMPLATE)
    assert url == "http://platform:8000/api/v1/modules?page=1&size=20"
    assert service_dependency("platform") == "service:platform"


@pytest.mark.kiwi_id(2169)
def test_validate_public_contract_boundary() -> None:
    """公开契约边界：非 /api/v1 路径 / 未登记服务 / 非法策略一律 ParamError。"""
    validate_service_request(_request())
    with pytest.raises(ParamError):
        validate_service_request(_request(path="/internal/secret"))
    with pytest.raises(ParamError):
        validate_service_request(_request(service="ghost"))
    with pytest.raises(ParamError):
        validate_service_request(_request(service="workflow"))
    with pytest.raises(ParamError):
        validate_service_request(_request(policy=ServiceCallPolicy(timeout=0)))
    with pytest.raises(ParamError):
        validate_service_request(_request(policy=ServiceCallPolicy(max_retries=-1)))
    with pytest.raises(ParamError):
        validate_service_request(_request(method=""))


@pytest.mark.kiwi_id(2169)
def test_response_payload_handles_non_json() -> None:
    """响应体为空 / 非 JSON 时 `payload()` 返回 None。"""
    assert ServiceResponse(status_code=200).payload() is None
    assert ServiceResponse(status_code=200, content=b"not-json").payload() is None
    assert ServiceResponse(status_code=200, content=b"\xff\xfe").payload() is None


@pytest.mark.kiwi_id(2169)
async def test_retry_on_status_then_success() -> None:
    """命中可重试状态码时重试，恢复后返回成功响应。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503 if attempts["n"] == 1 else 200, json={"ok": True})

    client = _client(handler)
    response = await client.call(_request(policy=ServiceCallPolicy(max_retries=1, retry_backoff=0.0)))
    await client.aclose()
    assert response.status_code == 200
    assert response.payload() == {"ok": True}
    assert attempts["n"] == 2


@pytest.mark.kiwi_id(2169)
async def test_transport_timeout_exhausts_and_raises() -> None:
    """transport 异常重试耗尽：抛服务不可用（10007）、计熔断失败、尝试次数为 max_retries + 1。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectTimeout("timeout", request=request)

    circuit = RecordingCircuit()
    fallback = StubFallback(FallbackAction.DEGRADE)
    client = _client(handler, circuit=circuit, fallback=fallback)
    with pytest.raises(ServiceUnavailableError) as excinfo:
        await client.call(_request(policy=ServiceCallPolicy(max_retries=2, retry_backoff=0.0)))
    await client.aclose()
    assert attempts["n"] == 3
    assert circuit.failures == ["service:platform"]
    assert excinfo.value.code == 10007
    assert excinfo.value.data == {
        "service": "platform",
        "dependency": "service:platform",
        "reason": "transport",
        "fallback": "degrade",
    }


@pytest.mark.kiwi_id(2169)
async def test_retry_status_exhausted_raises() -> None:
    """可重试状态码重试耗尽：抛服务不可用并计熔断失败。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503)

    circuit = RecordingCircuit()
    client = _client(handler, circuit=circuit)
    with pytest.raises(ServiceUnavailableError) as excinfo:
        await client.call(_request(policy=ServiceCallPolicy(max_retries=1, retry_backoff=0.0)))
    await client.aclose()
    assert attempts["n"] == 2
    assert circuit.failures == ["service:platform"]
    assert excinfo.value.data is not None


@pytest.mark.kiwi_id(2169)
async def test_circuit_open_fast_fails_without_request() -> None:
    """熔断断开：不发起请求、快速失败、降级动作随 data 回传。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200)

    circuit = RecordingCircuit(allowed=False)
    client = _client(handler, circuit=circuit, fallback=StubFallback(FallbackAction.DEFAULT))
    with pytest.raises(ServiceUnavailableError) as excinfo:
        await client.call(_request())
    await client.aclose()
    assert attempts["n"] == 0
    data = excinfo.value.data
    assert isinstance(data, dict) and data["reason"] == "circuit_open" and data["fallback"] == "default"


@pytest.mark.kiwi_id(2169)
async def test_rate_limit_blocks_before_request() -> None:
    """调用侧限流超限：抛限流异常（10005）、不发起请求。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200)

    limiter = StubRateLimiter(allowed=False)
    client = _client(handler, rate_limiter=limiter)
    with pytest.raises(RateLimitError):
        await client.call(_request(policy=ServiceCallPolicy(rate_limit=RateLimitRule(limit=1))))
    await client.aclose()
    assert attempts["n"] == 0
    assert limiter.checked == ["bms:global:rate:service:platform"]


@pytest.mark.kiwi_id(2169)
async def test_non_retryable_status_returned_as_is() -> None:
    """非重试状态码（4xx）原样返回并计熔断成功（服务可达）。"""
    circuit = RecordingCircuit()
    client = _client(lambda request: httpx.Response(404, json={"code": 10002}), circuit=circuit)
    response = await client.call(_request())
    await client.aclose()
    assert isinstance(response, ServiceResponse)
    assert response.status_code == 404
    assert circuit.successes == ["service:platform"]


@pytest.mark.kiwi_id(2169)
async def test_null_client_always_succeeds() -> None:
    """占位实现恒定成功、不外呼。"""
    response = await NullServiceClient().call(_request())
    assert response.status_code == 200
    assert response.payload() is None


@pytest.mark.kiwi_id(2169)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位客户端；路由经 get_service_client 取到同一实例。"""
    app: FastAPI = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.service_client, NullServiceClient)
        assert isinstance(app.state.circuit_breaker, NullCircuitBreaker)

        @app.get("/service-client")
        async def info(  # pyright: ignore[reportUnusedFunction]
            client: Annotated[BaseServiceClient, Depends(get_service_client)],
        ) -> dict[str, str]:
            return {"key": client.key, "type": type(client).__name__}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get("/service-client")
        assert response.status_code == 200
        assert response.json() == {"key": "service_client", "type": "NullServiceClient"}


@pytest.mark.kiwi_id(2169)
async def test_headers_content_and_circuit_disabled() -> None:
    """请求头 / 原始体透传；关闭熔断时不记录结果。"""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["content"] = request.content
        return httpx.Response(200)

    circuit = RecordingCircuit()
    client = _client(handler, circuit=circuit)
    response = await client.call(
        _request(
            method="POST",
            headers={"X-Test": "1"},
            content=b"raw-body",
            policy=ServiceCallPolicy(circuit_breaker=False),
        )
    )
    await client.aclose()
    assert response.status_code == 200
    headers = cast("dict[str, str]", captured["headers"])
    assert headers.get("x-test") == "1"
    assert captured["content"] == b"raw-body"
    assert circuit.successes == []


@pytest.mark.kiwi_id(2169)
async def test_json_body_sent() -> None:
    """JSON 请求体经 httpx `json` 发送。"""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return httpx.Response(200)

    client = _client(handler)
    response = await client.call(_request(method="POST", json_body={"name": "演示"}))
    await client.aclose()
    assert response.status_code == 200
    assert json.loads(cast("bytes", captured["content"])) == {"name": "演示"}


@pytest.mark.kiwi_id(2169)
async def test_transport_failure_without_circuit() -> None:
    """关闭熔断时 transport 失败不记录熔断、仍抛服务不可用。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    circuit = RecordingCircuit()
    client = _client(handler, circuit=circuit)
    with pytest.raises(ServiceUnavailableError):
        await client.call(_request(policy=ServiceCallPolicy(max_retries=0, circuit_breaker=False)))
    await client.aclose()
    assert circuit.failures == []


@pytest.mark.kiwi_id(2169)
async def test_status_retry_exhausted_without_circuit() -> None:
    """关闭熔断时重试状态码耗尽不记录熔断、仍抛服务不可用。"""
    circuit = RecordingCircuit()
    client = _client(lambda request: httpx.Response(503), circuit=circuit)
    with pytest.raises(ServiceUnavailableError):
        await client.call(_request(policy=ServiceCallPolicy(max_retries=1, circuit_breaker=False, retry_backoff=0.0)))
    await client.aclose()
    assert circuit.failures == []


@pytest.mark.kiwi_id(2169)
async def test_backoff_waits_between_retries() -> None:
    """重试间隔按退避基数等待（>0 时进入等待分支）。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503 if attempts["n"] == 1 else 200)

    client = _client(handler)
    response = await client.call(_request(policy=ServiceCallPolicy(max_retries=1, retry_backoff=0.001)))
    await client.aclose()
    assert response.status_code == 200
    assert attempts["n"] == 2


@pytest.mark.kiwi_id(2169)
async def test_fallback_resolution_error_degrades_to_raise() -> None:
    """降级策略自身异常不掩盖原失败：动作回落 RAISE。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client(handler, fallback=ExplodingFallback())
    with pytest.raises(ServiceUnavailableError) as excinfo:
        await client.call(_request(policy=ServiceCallPolicy(max_retries=0, retry_backoff=0.0)))
    await client.aclose()
    data = excinfo.value.data
    assert isinstance(data, dict) and data["fallback"] == "raise"


class StubTokenIssuer(BaseServiceTokenIssuer):
    """记录签发请求并固定返回占位服务 JWT 的替身。"""

    plugin_name = "stub"

    def __init__(self) -> None:
        self.specs: list[ServiceTokenSpec] = []

    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        self.specs.append(spec)
        return OAuthToken(access_token="service-jwt")

    def jwks(self) -> dict[str, object]:
        return {"keys": []}

    def verify(self, token: str) -> IdentityClaims:
        return IdentityClaims(subject="stub")


@pytest.mark.kiwi_id(2180)
async def test_outbound_strips_inbound_authorization() -> None:
    """出站无条件剥离入站 `Authorization`（外部 token 不透传），其余头保留。"""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200)

    client = _client(handler, token_issuer=StubTokenIssuer(), attach_service_token=False)
    response = await client.call(_request(headers={"Authorization": "Bearer user-token", "X-Test": "1"}))
    await client.aclose()
    assert response.status_code == 200
    headers = cast("dict[str, str]", captured["headers"])
    assert "authorization" not in headers
    assert headers.get("x-test") == "1"


@pytest.mark.kiwi_id(2180)
async def test_outbound_attaches_service_token_when_enabled() -> None:
    """开启出站换券：剥离入站 `Authorization` 并按目标服务附自签服务 JWT。"""
    captured: dict[str, object] = {}
    issuer = StubTokenIssuer()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200)

    client = _client(handler, token_issuer=issuer, attach_service_token=True)
    response = await client.call(
        _request(headers={"authorization": "Bearer user-token"}, policy=ServiceCallPolicy(scopes=("user:read",)))
    )
    await client.aclose()
    assert response.status_code == 200
    headers = cast("dict[str, str]", captured["headers"])
    assert headers.get("authorization") == "Bearer service-jwt"
    assert issuer.specs == [ServiceTokenSpec(service="platform", scopes=("user:read",))]


@pytest.mark.kiwi_id(2180)
async def test_outbound_without_issuer_still_strips() -> None:
    """开关开启但签发者未就绪：仅剥除不透传，不带服务身份（不整体失败）。"""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200)

    client = _client(handler, token_issuer=None, attach_service_token=True)
    response = await client.call(_request(headers={"Authorization": "Bearer user-token"}))
    await client.aclose()
    assert response.status_code == 200
    headers = cast("dict[str, str]", captured["headers"])
    assert "authorization" not in headers


class BlankTokenIssuer(StubTokenIssuer):
    """返回空令牌的替身（覆盖空 token 不附头的分支）。"""

    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        self.specs.append(spec)
        return OAuthToken(access_token="")


@pytest.mark.kiwi_id(2180)
async def test_outbound_blank_token_not_attached() -> None:
    """签发者返回空令牌时不附加 `Authorization`（仍剥离入站授权头）。"""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200)

    client = _client(handler, token_issuer=BlankTokenIssuer(), attach_service_token=True)
    response = await client.call(_request(headers={"Authorization": "Bearer user-token"}))
    await client.aclose()
    assert response.status_code == 200
    headers = cast("dict[str, str]", captured["headers"])
    assert "authorization" not in headers
