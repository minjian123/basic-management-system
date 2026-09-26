"""认证与身份服务 schemas 层：会话管理（列表 / 详情 / 强制踢出）请求与响应契约。

- `SESSION_REVOKED_EVENT`：踢出广播事件名（与实时推送能力域 `REALTIME_EVENTS` 一致）。
- `SessionItem`：会话行契约（列表与详情共用；已撤销会话 `revoked_at` 非空）。
- `KickResult`：强制踢出结果（会话 id + 撤销时间 + 原因）。
"""

from datetime import datetime

from pydantic import Field

from bms_core.schemas.base import BaseSchema

SESSION_REVOKED_EVENT = "session.revoked"
"""会话失效广播事件名（`BaseRealtimePublisher` 占位，阶段八接真实 Socket.IO）。"""


class SessionItem(BaseSchema):
    """会话行（用户 / 设备 / IP / 登录与过期时间 / 撤销时间）。"""

    session_id: str = Field(description="会话 id（= JWT jti）")
    user_id: int = Field(description="用户 ID（用户名由前端经 org 名称接口回显）")
    device: str | None = Field(default=None, description="设备标识（User-Agent 摘要）")
    ip: str | None = Field(default=None, description="登录 IP")
    login_at: datetime = Field(description="登录时间（UTC）")
    expires_at: datetime = Field(description="refresh 过期时间（UTC）")
    revoked_at: datetime | None = Field(default=None, description="撤销时间（UTC；NULL=有效）")


class KickResult(BaseSchema):
    """强制踢出结果。"""

    session_id: str = Field(description="被踢出的会话 id")
    revoked_at: datetime = Field(description="撤销时间（UTC）")
    reason: str = Field(default="kick", description="撤销原因（kick / max_active / logout）")
