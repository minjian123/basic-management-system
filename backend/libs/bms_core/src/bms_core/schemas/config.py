"""系统参数内部读取端点的请求 / 响应契约。

- `ConfigResolveRequest`：批量取参数请求（参数键序列）。
- `ConfigResolveResponse`：批量取参数响应（仅返回存在的键）。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema

__all__ = ["ConfigResolveRequest", "ConfigResolveResponse"]


class ConfigResolveRequest(BaseSchema):
    """批量取参数请求。"""

    keys: list[str] = Field(default_factory=list[str], description="参数键序列")


class ConfigResolveResponse(BaseSchema):
    """批量取参数响应（只含存在的键）。"""

    values: dict[str, str] = Field(default_factory=dict[str, str], description="参数键 → 值（仅存在的键）")
