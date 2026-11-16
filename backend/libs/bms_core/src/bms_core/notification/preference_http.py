"""通知偏好读取真实实现（`http`）：经 `service_client` 读 platform 内部端点。

- **权威侧是 platform 服务**（其租户库存 `sys_user_preference` 与 `sys_user.timezone`），
  通知服务不直连其库。
- **契约**：`POST /api/v1/platform/internal/preferences/resolve`（服务 JWT，`tenant_id` claim 透传租户）。
- **降级（不抛业务错）**：不可达 / 超时 / 熔断 / 非 2xx / 响应体非法 → 返回默认偏好（全渠道开启、无免打扰）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION
from bms_core.notification.preference import (
    NOTIFY_PREF_CHANNELS,
    NOTIFY_PREF_DND,
    BaseNotificationPreferenceStore,
    NotificationPreference,
    default_notification_preference,
)
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = ["NOTIFY_PREFERENCE_SERVICE", "PREFERENCE_RESOLVE_PATH", "HttpNotificationPreferenceStore"]

NOTIFY_PREFERENCE_SERVICE = "platform"
"""偏好数据权威服务标识（`sys_user_preference` 所有者）。"""

PREFERENCE_RESOLVE_PATH = "/api/v1/platform/internal/preferences/resolve"
"""内部按用户批量取偏好契约路径。"""

_LOGGER = get_logger("bms")


class HttpNotificationPreferenceStore(BaseNotificationPreferenceStore):
    """跨服务通知偏好读取（不可达回落默认）。"""

    plugin_name: str = "http"
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def load(self, user_id: int) -> NotificationPreference:
        """读取指定用户偏好（契约调用 + 降级）。

        Args:
            user_id: 收件用户主键。

        Returns:
            NotificationPreference: 通知偏好；调用失败返回默认偏好。
        """
        request = ServiceRequest(
            service=NOTIFY_PREFERENCE_SERVICE,
            method="POST",
            path=PREFERENCE_RESOLVE_PATH,
            tenant_id=get_current_tenant_id(),
            json_body=ConcurrentStableFrozenDict(
                {
                    "user_id": str(user_id),
                    "keys": ConcurrentStableFrozenList((NOTIFY_PREF_CHANNELS, NOTIFY_PREF_DND)),
                }
            ),
        )
        try:
            response = await self._client.call(request)
        except ServiceUnavailableError:
            _LOGGER.warning("通知偏好跨服务读取降级", user_id=user_id)
            return default_notification_preference()
        if not 200 <= response.status_code < 300:
            _LOGGER.warning("通知偏好跨服务读取失败", user_id=user_id, status=response.status_code)
            return default_notification_preference()
        return _parse_payload(response.payload())


def _parse_payload(payload: object) -> NotificationPreference:
    """解析内部端点响应（非法即回落默认）。

    Args:
        payload: 响应体。

    Returns:
        NotificationPreference: 通知偏好。
    """
    if not isinstance(payload, Mapping):
        return default_notification_preference()
    data = cast("Mapping[str, object]", payload).get("data")
    if not isinstance(data, Mapping):
        return default_notification_preference()
    raw = cast("Mapping[str, object]", data)
    values = raw.get("values")
    value_map: ConcurrentStableFrozenDict[str, object] = (
        ConcurrentStableFrozenDict(cast("Mapping[str, object]", values))
        if isinstance(values, Mapping)
        else ConcurrentStableFrozenDict()
    )
    channels = _parse_channels(value_map.get(NOTIFY_PREF_CHANNELS))
    dnd = _parse_dnd(value_map.get(NOTIFY_PREF_DND))
    timezone = raw.get("timezone")
    return NotificationPreference(
        channels=channels,
        dnd_enabled=dnd[0],
        dnd_start=dnd[1],
        dnd_end=dnd[2],
        timezone=timezone if isinstance(timezone, str) and timezone else None,
    )


def _parse_channels(raw: object) -> ConcurrentStableFrozenDict[str, bool]:
    """解析渠道开关（缺键按开启，未知键忽略）。

    Args:
        raw: 原始值。

    Returns:
        ConcurrentStableFrozenDict[str, bool]: 渠道开关。
    """
    result: ConcurrentStableDict[str, bool] = ConcurrentStableDict({"inbox": True, "email": True, "sms": True})
    if isinstance(raw, Mapping):
        for key, value in cast("Mapping[object, object]", raw).items():
            name = str(key)
            if name in result and isinstance(value, bool):
                result.set(name, value)
    return ConcurrentStableFrozenDict(result)


def _parse_dnd(raw: object) -> tuple[bool, str, str]:
    """解析免打扰配置（非法即关闭）。

    Args:
        raw: 原始值。

    Returns:
        tuple[bool, str, str]: （是否启用, 开始, 结束）。
    """
    if not isinstance(raw, Mapping):
        return False, "00:00", "00:00"
    mapping = cast("Mapping[str, object]", raw)
    enabled = mapping.get("enabled")
    start = mapping.get("start")
    end = mapping.get("end")
    if not isinstance(enabled, bool) or not isinstance(start, str) or not isinstance(end, str):
        return False, "00:00", "00:00"
    return enabled, start, end
