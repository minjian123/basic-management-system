"""schemas 层用户偏好请求 / 响应契约（占位路由 `/api/v1/preferences/{key}`）。"""

from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class PreferenceValueRequest(BaseSchema):
    """偏好写入请求：`{value}`。"""

    value: Any = Field(default=None, description="偏好值（JSON 可序列化的任意结构）")


class PreferenceResponse(BaseSchema):
    """偏好响应：`{key, value}`。"""

    key: str = Field(description="偏好键（域.键，如 list.user_form）")
    value: Any = Field(default=None, description="偏好值")
