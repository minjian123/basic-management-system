"""登录审计记录器护栏（06_01）：失败原因映射 / 事件载荷。"""

from typing import cast

import pytest

from bms_core.core.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    CaptchaVerifyError,
    LoginFailedError,
    RateLimitError,
    ServiceUnavailableError,
)
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.events.base import EventEnvelope
from bms_identity.domains.auth.services import audit as audit_module
from bms_identity.domains.auth.services.audit import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    LoginAuditRecorder,
    classify_login_error,
)

pytestmark = pytest.mark.kiwi_id(2407)


def test_classify_login_error_branches() -> None:
    """异常 → 失败原因：六类业务异常 + 兜底。"""
    assert classify_login_error(RateLimitError()) == "rate_limited"
    assert classify_login_error(CaptchaVerifyError()) == "captcha_invalid"
    assert classify_login_error(AccountLockedError()) == "account_locked"
    assert classify_login_error(AccountDisabledError()) == "account_disabled"
    assert classify_login_error(LoginFailedError()) == "bad_credentials"
    assert classify_login_error(ServiceUnavailableError()) == "backend_unavailable"
    assert classify_login_error(ValueError("x")) == "internal_error"


class _FakeEmitter:
    """记录型发射器替身。"""

    def __init__(self, **kwargs: object) -> None:
        del kwargs
        self.events: list[EventEnvelope] = []  # bare-collections:allow（测试断言容器）

    async def emit(self, event: EventEnvelope) -> bool:
        """记录事件。"""
        self.events.append(event)
        return True


async def test_recorder_builds_login_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功 / 失败两种事件：状态、失败原因、租户位与链路 id 正确。"""
    created: list[_FakeEmitter] = []  # bare-collections:allow（测试记录容器）

    def _factory(**kwargs: object) -> _FakeEmitter:
        emitter = _FakeEmitter(**kwargs)
        created.append(emitter)
        return emitter

    monkeypatch.setattr(audit_module, "AuditEventEmitter", _factory)
    from bms_core.core.config import get_settings

    recorder = LoginAuditRecorder(
        registry=cast("EngineRegistry", object()),
        session_factory=cast("SessionFactory", object()),
        settings=get_settings(),
    )
    assert await recorder.record(
        username="alice",
        tenant_id="1001",
        user_id=7,
        ip="10.0.0.1",
        user_agent="pytest",
        status=STATUS_SUCCESS,
        trace_id="trace-1",
    )
    success = created[0].events[0]
    assert success.payload["username"] == "alice"
    assert success.payload["status"] == STATUS_SUCCESS
    assert success.tenant_id == "1001"
    assert success.trace_id == "trace-1"
    assert "fail_reason" not in success.payload

    assert await recorder.record(
        username="alice",
        tenant_id="1001",
        user_id=None,
        ip=None,
        user_agent=None,
        status=STATUS_FAILED,
        fail_reason="bad_credentials",
    )
    failed = created[0].events[1]
    assert failed.payload["status"] == STATUS_FAILED
    assert failed.payload["fail_reason"] == "bad_credentials"
    assert "user_id" not in failed.payload
