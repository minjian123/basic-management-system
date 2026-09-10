"""demo 示例模块：请求/响应模型。"""

from pydantic import BaseModel, Field


class DemoCreateRequest(BaseModel):
    """创建 demo 请求。"""

    name: str = Field(min_length=1, max_length=64, description="demo 名称")


class DemoUpdateRequest(BaseModel):
    """更新 demo 请求。"""

    name: str = Field(min_length=1, max_length=64, description="demo 名称")


class DemoResponse(BaseModel):
    """demo 响应。"""

    id: int
    name: str
