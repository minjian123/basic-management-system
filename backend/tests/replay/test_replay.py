"""防重放基座契约测试（Kiwi 43）：编排顺序 / 超窗 / 签名 / nonce 去重 / 占位语义 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_replay_guard
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import AuthError
from app.core.security import SIGNATURE_HEADER, SignatureCodec
from app.main import create_app, lifespan
from app.replay.base import NONCE_HEADER, REPLAY_WINDOW, TIMESTAMP_HEADER, BaseReplayGuard, ReplayDecision, ReplayReason
from app.replay.null import NullReplayGuard

SECRET = "s3cr3t-of-client"
CODEC = SignatureCodec()
NOW = 1_800_000_000
METHOD = "POST"
PATH = "/api/open/orders"
NONCE = "nonce-abc-1"
BODY = '{"amount":100}'
TIMESTAMP = NOW


def _signature(
    *,
    method: str = METHOD,
    path: str = PATH,
    timestamp: int = TIMESTAMP,
    nonce: str = NONCE,
    secret: str = SECRET,
    body: str = BODY,
) -> str:
    """按开放接口串料口径计算签名。"""
    return CODEC.sign(secret=secret, method=method, path=path, timestamp=timestamp, nonce=nonce, body=body)


class RecordingGuard(BaseReplayGuard):
    """测试用记录型守卫：记录 nonce 占用调用，占用结果可控。"""

    def __init__(self, *, allow_nonce: bool = True) -> None:
        super().__init__()
        self.claimed: list[str] = []
        self._allow_nonce = allow_nonce

    async def claim_nonce(self, nonce: str, *, ttl: int = REPLAY_WINDOW) -> bool:
        """记录调用并返回预设结果。"""
        self.claimed.append(nonce)
        return self._allow_nonce


class MemoryGuard(BaseReplayGuard):
    """测试用进程内去重守卫（模拟 Redis SETNX 首次占用语义）。"""

    def __init__(self) -> None:
        super().__init__()
        self._claimed: set[str] = set()

    async def claim_nonce(self, nonce: str, *, ttl: int = REPLAY_WINDOW) -> bool:
        """首次占用返回 True，重复返回 False。"""
        if nonce in self._claimed:
            return False
        self._claimed.add(nonce)
        return True


async def _verify(
    guard: BaseReplayGuard,
    *,
    method: str = METHOD,
    path: str = PATH,
    timestamp: int = TIMESTAMP,
    nonce: str = NONCE,
    signature: str | None = None,
    secret: str = SECRET,
    body: str = BODY,
    now: int = NOW,
) -> ReplayDecision:
    """按默认参数调用 `verify`（签名缺省按入参实时计算），允许覆盖任一参数。"""
    return await guard.verify(
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        signature=signature
        if signature is not None
        else _signature(method=method, path=path, timestamp=timestamp, nonce=nonce, secret=secret, body=body),
        secret=secret,
        body=body,
        now=now,
    )


@pytest.mark.kiwi_id(43)
def test_inheritance_key_and_constants() -> None:
    """契约继承链、能力域标识与请求头 / 窗口 / 原因枚举常量。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseReplayGuard, BaseCapability)
    assert issubclass(NullReplayGuard, BaseReplayGuard)
    assert issubclass(NullReplayGuard, BaseNullObject)
    assert BaseReplayGuard.key == "replay_guard"

    guard = NullReplayGuard()
    assert guard.placeholder is True
    assert REPLAY_WINDOW == 300
    assert (TIMESTAMP_HEADER, NONCE_HEADER, SIGNATURE_HEADER) == ("X-Timestamp", "X-Nonce", "X-Signature")
    assert [reason.value for reason in ReplayReason] == ["expired", "bad_signature", "replayed"]


@pytest.mark.kiwi_id(43)
async def test_verify_expired_window() -> None:
    """时间戳超窗拒绝（短路在签名与 nonce 之前）。"""
    guard = RecordingGuard()
    early = await _verify(guard, timestamp=NOW - REPLAY_WINDOW - 1)
    assert (early.allowed, early.reason) == (False, ReplayReason.EXPIRED)
    late = await _verify(guard, timestamp=NOW + REPLAY_WINDOW + 1)
    assert (late.allowed, late.reason) == (False, ReplayReason.EXPIRED)
    assert guard.claimed == []


@pytest.mark.kiwi_id(43)
async def test_verify_bad_signature() -> None:
    """签名不符拒绝（串料含方法 / 路径 / 时间戳 / nonce / 体，改任一即失败）。"""
    guard = RecordingGuard()
    wrong_secret = await _verify(guard, secret="other-secret", signature=_signature())
    assert (wrong_secret.allowed, wrong_secret.reason) == (False, ReplayReason.BAD_SIGNATURE)
    wrong_body = await _verify(guard, signature=_signature(body="{}"))
    assert (wrong_body.allowed, wrong_body.reason) == (False, ReplayReason.BAD_SIGNATURE)
    wrong_path = await _verify(guard, signature=_signature(path="/api/open/other"))
    assert (wrong_path.allowed, wrong_path.reason) == (False, ReplayReason.BAD_SIGNATURE)
    assert guard.claimed == []


@pytest.mark.kiwi_id(43)
async def test_verify_replayed_nonce() -> None:
    """窗口内 nonce 重复拒绝（首次放行、再次 replayed）。"""
    guard = MemoryGuard()
    first = await _verify(guard)
    assert (first.allowed, first.reason) == (True, None)
    second = await _verify(guard)
    assert (second.allowed, second.reason) == (False, ReplayReason.REPLAYED)


@pytest.mark.kiwi_id(43)
async def test_null_guard_window_and_signature_enforced() -> None:
    """占位守卫：时间窗与签名真实生效，nonce 去重不拦截（不连 Redis）。"""
    guard = NullReplayGuard()
    assert (await _verify(guard, timestamp=NOW - REPLAY_WINDOW + 1)).allowed is True
    assert (await _verify(guard, timestamp=NOW - REPLAY_WINDOW - 1)).reason is ReplayReason.EXPIRED
    assert (await _verify(guard, secret="wrong", signature=_signature())).reason is ReplayReason.BAD_SIGNATURE
    assert (await _verify(guard)).allowed is True
    assert (await _verify(guard)).allowed is True


@pytest.mark.kiwi_id(43)
async def test_require_raises_auth_error() -> None:
    """强制校验失败抛 AuthError（20001 / 401）；合法签名放行时不抛。"""
    guard = NullReplayGuard()
    allowed = await guard.require(
        method=METHOD,
        path=PATH,
        timestamp=TIMESTAMP,
        nonce=NONCE,
        signature=_signature(),
        secret=SECRET,
        body=BODY,
        now=NOW,
    )
    assert allowed.allowed is True

    with pytest.raises(AuthError) as excinfo:
        await guard.require(
            method=METHOD,
            path=PATH,
            timestamp=TIMESTAMP,
            nonce=NONCE,
            signature=_signature(secret="other-secret"),
            secret=SECRET,
            body=BODY,
            now=NOW,
        )
    assert excinfo.value.code == 20001
    assert excinfo.value.http_status == 401


@pytest.mark.kiwi_id(43)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位守卫；路由经 get_replay_guard 取到同一实例并完成校验。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.replay_guard, NullReplayGuard)

        @app.post("/open-probe")
        async def open_probe(  # pyright: ignore[reportUnusedFunction]
            guard: Annotated[BaseReplayGuard, Depends(get_replay_guard)],
        ) -> dict[str, object]:
            decision = await _verify(guard)
            return {"key": guard.key, "type": type(guard).__name__, "allowed": decision.allowed}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/open-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "replay_guard", "type": "NullReplayGuard", "allowed": True}
