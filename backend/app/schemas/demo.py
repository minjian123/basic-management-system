"""demo 示例模块：请求/响应模型（继承 BaseSchema）。"""

from pydantic import Field

from app.schemas.base import BaseSchema


class DemoCreateRequest(BaseSchema):
    """创建 demo 请求。"""

    name: str = Field(min_length=1, max_length=64, description="demo 名称")


class DemoUpdateRequest(BaseSchema):
    """更新 demo 请求。"""

    name: str = Field(min_length=1, max_length=64, description="demo 名称")


class DemoResponse(BaseSchema):
    """demo 响应。"""

    id: int
    name: str
