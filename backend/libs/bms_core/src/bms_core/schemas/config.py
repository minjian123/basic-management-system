"""系统参数内部读取端点的请求 / 响应契约。

- `ConfigResolveRequest`：批量取参数请求（参数键序列）。
- `ConfigResolveResponse`：批量取参数响应（仅返回存在的键）。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)

__all__ = ["ConfigResolveRequest", "ConfigResolveResponse"]


class ConfigResolveRequest(BaseSchema):
    """批量取参数请求。"""

    keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="参数键序列"
    )


class ConfigResolveResponse(BaseSchema):
    """批量取参数响应（只含存在的键）。"""

    values: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="参数键 → 值（仅存在的键）"
    )
