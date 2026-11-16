"""内部偏好读取端点的请求 / 响应契约。"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)

__all__ = ["InternalPreferenceResolveRequest", "InternalPreferenceResolveResponse"]


class InternalPreferenceResolveRequest(BaseSchema):
    """按用户批量取偏好请求。"""

    user_id: str = Field(description="用户主键（雪花 id 十进制字符串）")
    keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="偏好键序列"
    )


class InternalPreferenceResolveResponse(BaseSchema):
    """按用户批量取偏好响应（只含存在的键）。"""

    values: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="偏好键 → 值（仅存在的键）"
    )
    timezone: str | None = Field(default=None, description="用户时区（IANA；未设置为空）")
