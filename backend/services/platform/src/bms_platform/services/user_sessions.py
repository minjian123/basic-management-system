"""平台服务 services 层：用户会话失效通道（跨服务调用 identity；需求 07-2）。

口径（《02_01 详细设计》§4.2 / §5）：

- **通道**：identity 内部端点 `POST /api/v1/identity/internal/sessions/revoke-user`
  （`require_service("platform")`，服务间直连不经网关）；identity 侧复用阶段六既有的
  `SessionService.revoke_user_sessions`（refresh 吊销 + Redis 会话标记删除）；
- **时机**：一律在**写事务提交之后**调用（跨服务调用不可回滚，不与库内事务混同）；
- **失败处置**：**不阻断主流程**，返回 `False` 并由调用方以 `session_revoked=false` 暴露 +
  error 日志（运维按需重试，见详细设计 §8 开放项 1）。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_id_str
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

_logger = logging.getLogger(__name__)

IDENTITY_SERVICE_KEY = "identity"
"""identity 服务标识（服务目录登记名）。"""

REVOKE_USER_SESSIONS_PATH = "/api/v1/identity/internal/sessions/revoke-user"
"""identity 内部端点：按用户撤销全部在线会话。"""

REASON_USER_DISABLED = "user_disabled"
"""撤销原因：管理员停用账号。"""

REASON_USER_DELETED = "user_deleted"
"""撤销原因：管理员删除（软删）账号。"""

REASON_PASSWORD_RESET = "password_reset"
"""撤销原因：管理员重置密码（与认证域找回密码同因）。"""

REASONS: tuple[str, ...] = (REASON_USER_DISABLED, REASON_USER_DELETED, REASON_PASSWORD_RESET)
"""撤销原因取值。"""


class UserSessionClient(BaseFrameworkObject):
    """用户会话失效客户端（跨服务；尽力而为语义）。"""

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间同步调用客户端（附服务令牌 `aud=service`）。
        """
        self._client = client

    async def revoke_user_sessions(self, user_id: int, *, reason: str) -> bool:
        """失效某用户全部在线会话。

        Args:
            user_id: 用户主键。
            reason: 撤销原因（`REASONS` 之一，落 identity 侧会话撤销留痕）。

        Returns:
            bool: 是否调用成功（`False` = 跨服务不可达 / 非 200，主流程不阻断）。
        """
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        body.set("user_id", user_id)
        body.set("reason", reason)
        request = ServiceRequest(
            service=IDENTITY_SERVICE_KEY,
            method="POST",
            path=REVOKE_USER_SESSIONS_PATH,
            json_body=body,
            tenant_id=current_tenant_id_str(),
        )
        try:
            response = await self._client.call(request)
        except Exception as exc:  # 跨服务异常（不可达 / 超时 / 熔断 / 限流）一律按失败处置
            _logger.error(
                "撤销用户会话失败（跨服务不可达）",
                extra={"user_id": user_id, "reason": reason, "error": repr(exc)},
            )
            return False
        if response.status_code != 200:
            _logger.error(
                "撤销用户会话失败（下游非 200）",
                extra={"user_id": user_id, "reason": reason, "status_code": response.status_code},
            )
            return False
        revoked = _read_revoked(response.payload())
        _logger.info(
            "已失效用户会话",
            extra={"user_id": user_id, "reason": reason, "revoked": revoked},
        )
        return True


def _read_revoked(payload: object) -> int:
    """从内部端点响应体取 `data.revoked`（缺字段 / 类型异常回落 0）。

    Args:
        payload: 响应体 JSON（`ServiceResponse.payload()` 产物）。

    Returns:
        int: 撤销的在线会话数（解析失败为 0）。
    """
    row = cast("Any", payload)
    if not isinstance(row, dict):
        return 0
    data = cast("Any", row).get("data")
    if not isinstance(data, dict):
        return 0
    raw = cast("Any", data).get("revoked")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    return 0
