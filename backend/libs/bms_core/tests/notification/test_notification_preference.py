"""通知偏好能力域：默认值 / 渠道开关 / 免打扰 / null 与 http 实现（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

import json
from datetime import datetime
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.notification.preference import (
    NotificationPreference,
    default_notification_preference,
    get_notification_preference_store,
)
from bms_core.notification.preference_http import HttpNotificationPreferenceStore, _parse_payload
from bms_core.notification.preference_null import NullNotificationPreferenceStore
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

pytestmark = pytest.mark.kiwi_id(2517)

_NOW = datetime(2026, 11, 16, 12, 0, 0)


class _Client:
    """服务间客户端替身。"""

    def __init__(self, response: ServiceResponse | None = None, *, fail: bool = False) -> None:
        self._response = response
        self._fail = fail

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        del request
        if self._fail:
            raise ServiceUnavailableError("down")
        assert self._response is not None
        return self._response


def _response(payload: object, status: int = 200) -> ServiceResponse:
    return ServiceResponse(status_code=status, content=json.dumps(payload).encode())


def test_default_preference() -> None:
    """默认全渠道开启、免打扰关闭。"""
    pref = default_notification_preference()
    assert pref.channels == {"inbox": True, "email": True, "sms": True}
    assert pref.dnd_enabled is False
    assert pref.in_quiet_hours(_NOW) is False


def test_channel_enabled_defaults_true_for_missing() -> None:
    """缺键按开启。"""
    pref = NotificationPreference(channels=ConcurrentStableFrozenDict({"inbox": False}))
    assert pref.channel_enabled("inbox") is False
    assert pref.channel_enabled("email") is True
    assert pref.channel_enabled("sms") is True


def test_quiet_hours_cross_midnight() -> None:
    """跨午夜时段（22:00–08:00）判定。"""
    pref = NotificationPreference(dnd_enabled=True, dnd_start="22:00", dnd_end="08:00", timezone="UTC")
    assert pref.in_quiet_hours(datetime(2026, 11, 16, 23, 0)) is True
    assert pref.in_quiet_hours(datetime(2026, 11, 16, 7, 0)) is True
    assert pref.in_quiet_hours(datetime(2026, 11, 16, 12, 0)) is False


def test_quiet_hours_same_day() -> None:
    """同日时段（09:00–17:00）判定。"""
    pref = NotificationPreference(dnd_enabled=True, dnd_start="09:00", dnd_end="17:00", timezone="UTC")
    assert pref.in_quiet_hours(datetime(2026, 11, 16, 10, 0)) is True
    assert pref.in_quiet_hours(datetime(2026, 11, 16, 20, 0)) is False


def test_quiet_hours_invalid_or_disabled() -> None:
    """未启用 / 起止相同 / 时间非法 / 时区非法均不命中。"""
    assert NotificationPreference(dnd_enabled=False, dnd_start="22:00", dnd_end="08:00").in_quiet_hours(_NOW) is False
    assert NotificationPreference(dnd_enabled=True, dnd_start="10:00", dnd_end="10:00").in_quiet_hours(_NOW) is False
    assert NotificationPreference(dnd_enabled=True, dnd_start="bad", dnd_end="08:00").in_quiet_hours(_NOW) is False
    assert (
        NotificationPreference(
            dnd_enabled=True, dnd_start="00:00", dnd_end="23:59", timezone="Mars/Base"
        ).in_quiet_hours(datetime(2026, 11, 16, 0, 0))
        is True
    )


async def test_null_store_returns_default() -> None:
    """null 实现恒默认。"""
    pref = await NullNotificationPreferenceStore().load(1001)
    assert pref == default_notification_preference()


async def test_http_store_parses_values() -> None:
    """http 实现解析渠道 / 免打扰 / 时区。"""
    payload = {
        "data": {
            "values": {
                "notify.channels": {"inbox": False, "email": True, "sms": True, "bad": False},
                "notify.dnd": {"enabled": True, "start": "22:00", "end": "08:00"},
            },
            "timezone": "Asia/Shanghai",
        }
    }
    store = HttpNotificationPreferenceStore(client=cast("BaseServiceClient", _Client(_response(payload))))
    pref = await store.load(1001)
    assert pref.channel_enabled("inbox") is False
    assert pref.dnd_enabled is True
    assert pref.timezone == "Asia/Shanghai"


async def test_http_store_falls_back_on_failures() -> None:
    """不可达 / 非 2xx / 载荷非法均回落默认。"""
    unavailable = HttpNotificationPreferenceStore(client=cast("BaseServiceClient", _Client(fail=True)))
    assert await unavailable.load(1) == default_notification_preference()

    responses = (
        _response({"data": {}}, status=500),
        _response({"data": "bad"}),
        _response({"data": {"values": "x"}}),
    )
    for response in responses:
        store = HttpNotificationPreferenceStore(client=cast("BaseServiceClient", _Client(response)))
        assert await store.load(1) == default_notification_preference()


def test_provider_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖提供者按配置解析（打桩 resolve_plugin）。"""
    from types import SimpleNamespace

    import bms_core.notification.preference as module

    sentinel = object()
    monkeypatch.setattr(module, "resolve_plugin", lambda *args, **kwargs: sentinel)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(
        notification_preference=SimpleNamespace(provider="http")
    ))))
    assert get_notification_preference_store(cast("object", request)) is sentinel  # pyright: ignore[reportArgumentType]


def test_parse_payload_rejects_bad_shapes() -> None:
    """解析器对非映射 / 非法 dnd 回落默认。"""
    assert _parse_payload(["bad"]) == default_notification_preference()
    assert _parse_payload({"data": {"values": {"notify.dnd": {"enabled": "yes", "start": 1}}}}) == (
        default_notification_preference()
    )
