"""平台服务 schemas 层：账号锁定相关契约（内部扫描 + 管理面）。"""

from datetime import datetime

from pydantic import Field

from bms_core.schemas.base import BaseSchema


class InactiveScanRequest(BaseSchema):
    """不活跃账号扫描请求（空体；租户经服务 JWT `tenant` claim 解析）。"""


class InactiveScanResult(BaseSchema):
    """不活跃账号扫描结果。"""

    scanned: int = Field(description="扫描候选账号数")
    locked: int = Field(description="本次锁定账号数")


class ManualLockRequest(BaseSchema):
    """手动锁定请求（写 `manual` 型；租户经登录态解析）。"""

    user_id: int = Field(description="用户主键")
    reason: str = Field(default="", max_length=255, description="锁定原因")


class LockItem(BaseSchema):
    """锁定记录行契约（列表 / 详情 / 手动锁定 / 解锁统一）。"""

    id: int = Field(description="锁定记录主键")
    user_id: int = Field(description="用户主键")
    username: str = Field(default="", description="用户登录账号（`sys_user` 同库回显；用户已不存在为空串）")
    name: str = Field(default="", description="用户昵称 / 显示名（同库回显；用户已不存在为空串）")
    lock_type: str = Field(description="锁定类型（fail_limit/inactive/manual）")
    reason: str | None = Field(default=None, description="锁定原因")
    locked_at: datetime = Field(description="锁定时间（UTC）")
    locked_by: int | None = Field(default=None, description="锁定操作人（系统触发为 NULL）")
    expire_at: datetime | None = Field(default=None, description="锁定到期时间（UTC；NULL=需手动解锁）")
    unlock_at: datetime | None = Field(default=None, description="解锁时间（UTC；NULL=未解锁）")
    unlock_by: int | None = Field(default=None, description="解锁操作人（自动解锁为 NULL）")
    unlock_mode: str | None = Field(default=None, description="解锁方式（manual/auto；NULL=未解锁）")
