"""个人中心偏好（语言 / 时区）请求与响应契约。

口径（需求 06-2）：

- **部分更新**：请求里未出现的字段＝不修改；显式 `null`＝清空（读取时按缺省派生）。
- 响应同时给**存值**与**生效值**：存值可空，生效值是服务端按缺省规则派生的结果，前端不必重算。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema

__all__ = ["ProfilePreferenceRequest", "ProfilePreferenceResponse"]


class ProfilePreferenceRequest(BaseSchema):
    """偏好设置请求（部分更新语义）。"""

    locale: str | None = Field(
        default=None,
        max_length=16,
        description="语言偏好（须已登记且启用；null 表示清空回退系统默认语言）",
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="时区偏好（IANA 标识，如 Asia/Shanghai；null 表示清空回退缺省时区）",
    )


class ProfilePreferenceResponse(BaseSchema):
    """偏好读取响应（存值 + 生效值）。"""

    locale: str | None = Field(default=None, description="语言偏好存值（未设置为 null）")
    timezone: str | None = Field(default=None, description="时区偏好存值（未设置为 null）")
    effective_locale: str = Field(description="生效语言（未设置或该语言停用时为系统默认语言）")
    effective_timezone: str = Field(description="生效时区（未设置时按生效语言派生）")
