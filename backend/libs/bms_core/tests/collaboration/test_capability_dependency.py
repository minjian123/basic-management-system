"""入站能力授权依赖（`require_capability`，07B `02_04`；Kiwi 编号归 `05_01` 统一登记）。

直接调用依赖协程（不经 ASGI 链路，避免与全局异常处理器耦合），覆盖详细设计 §5 用例 9~11 的
依赖层语义：有授权放行、无授权 403（30001，消息含能力名与消费方）、授权过期标注、凭证缺失 /
非 Bearer / 服务标识为空 / 无效令牌一律 401（20001）、网关代发票据按未授权拒绝、打点维度正确。
"""

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime

import pytest

from bms_core.api.capability import require_capability
from bms_core.collaboration import (
    METRIC_CAPABILITY_CALL,
    METRIC_CAPABILITY_DENIED,
    CapabilityGrant,
    register_capability_grant_source,
    reset_capability_grants,
)
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError, PermissionError
from bms_core.oauth.verify import VerifiedToken
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    reset_collaboration_records,
)
from tests_support.metrics import RecordingMetrics

CAPABILITY = "demo.org.user-roles"


class _StubVerifier:
    """令牌校验替身：按令牌串返回服务身份。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回身份声明。

        Args:
            token: 令牌串（`platform` / `gateway` / `blank` / 其余视为无效）。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001 / 401）。
        """
        del audience
        if token == "platform":
            return VerifiedToken(subject="platform", service="platform", token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        if token == "blank":
            return VerifiedToken(subject="", service="", token_type="service")
        raise AuthError("invalid")


class _Source:
    """授权视图来源替身。"""

    def __init__(self, grants: ConcurrentStableList[CapabilityGrant]) -> None:
        """初始化。

        Args:
            grants: 每次加载返回的授权记录。
        """
        self._grants = grants

    async def load(
        self, *, provider: str | None = None, consumer: str | None = None
    ) -> ConcurrentStableList[CapabilityGrant]:
        """返回预置记录。

        Args:
            provider: 提供方业务域（未使用）。
            consumer: 消费方服务键（未使用）。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 授权记录。
        """
        del provider, consumer
        return self._grants


def _dependency() -> Callable[..., Awaitable[VerifiedToken]]:
    """构造能力授权依赖（被测对象）。

    Returns:
        Callable[..., Awaitable[VerifiedToken]]: 依赖协程。
    """
    return require_capability(CAPABILITY)


@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    """每例复位能力目录与授权视图，并登记夹具能力。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_capability_grants()
    register_collaboration_records(
        (
            CollaborationRecord(
                name=CAPABILITY,
                domain="org",
                kind="read",
                contract_version="0.1.0",
                path="/api/v1/demo/user-roles",
                product_key="demo",
                frontend_prefix="demo",
            ),
        )
    )
    yield
    reset_collaboration_records()
    reset_capability_grants()


@pytest.mark.anyio
async def test_dependency_allows_granted_consumer() -> None:
    """有有效分配：返回服务身份声明，并计 `call_total{result=allowed}`（不计越权）。"""
    register_capability_grant_source(_Source(ConcurrentStableList([_grant()])))
    metrics = RecordingMetrics()

    verified = await _dependency()(verifier=_StubVerifier(), metrics=metrics, authorization="Bearer platform")

    assert verified.service == "platform"
    labels = metrics.labels_of(METRIC_CAPABILITY_CALL)[-1]
    assert labels is not None and labels["result"] == "allowed"
    assert list(metrics.counter_values(METRIC_CAPABILITY_DENIED)) == []


@pytest.mark.anyio
async def test_dependency_rejects_unauthorized_expired_and_gateway() -> None:
    """无授权 / 已过期 / 网关代发票据一律 403（30001）；消息含能力名、消费方与原因。"""
    register_capability_grant_source(
        _Source(
            ConcurrentStableList(
                [
                    _grant(consumer="mdm"),
                    _grant(consumer="gateway"),
                    _grant(consumer="platform", expire_at=datetime(2020, 1, 1, tzinfo=UTC)),
                ]
            )
        )
    )
    metrics = RecordingMetrics()

    with pytest.raises(PermissionError) as expired:
        await _dependency()(verifier=_StubVerifier(), metrics=metrics, authorization="Bearer platform")
    with pytest.raises(PermissionError) as gateway:
        await _dependency()(verifier=_StubVerifier(), metrics=metrics, authorization="Bearer gateway")

    assert expired.value.code == 30001
    assert CAPABILITY in str(expired.value) and "授权已过期" in str(expired.value)
    assert "网关" in str(gateway.value)
    assert metrics.counter_values(METRIC_CAPABILITY_DENIED) == [1.0]


@pytest.mark.anyio
async def test_dependency_rejects_missing_or_invalid_credentials() -> None:
    """凭证缺失 / 非 Bearer / 服务标识为空 / 无效令牌：一律 401（20001），不进入授权判定。"""
    register_capability_grant_source(_Source(ConcurrentStableList([_grant()])))
    metrics = RecordingMetrics()

    for header in (None, "Basic xxx", "Bearer blank", "Bearer bogus"):
        with pytest.raises(AuthError):
            await _dependency()(verifier=_StubVerifier(), metrics=metrics, authorization=header)

    assert list(metrics.counter_values(METRIC_CAPABILITY_CALL)) == []


def _grant(consumer: str = "platform", *, expire_at: datetime | None = None) -> CapabilityGrant:
    """构造授权记录。

    Args:
        consumer: 消费方标识。
        expire_at: 有效期截止。

    Returns:
        CapabilityGrant: 授权记录。
    """
    return CapabilityGrant(
        capability_name=CAPABILITY,
        consumer_key=consumer,
        source="declared",
        status="enabled",
        expire_at=expire_at,
        note="用例",
    )
