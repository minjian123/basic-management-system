"""schemas 层公共分页契约：页码与游标分页的请求 / 响应基类。"""

from pydantic import Field

from app.schemas.base import BaseSchema


class BasePageQuery(BaseSchema):
    """页码分页请求。"""

    page: int = Field(default=1, ge=1, description="页码（从 1 起）")
    size: int = Field(default=20, ge=1, le=200, description="每页条数（默认 20，上限 200）")


class BasePageResponse[ItemT](BaseSchema):
    """页码分页响应。"""

    list: list[ItemT]
    total: int
    page: int
    size: int


class BaseCursorQuery(BaseSchema):
    """游标分页请求（日志 / 审计等大数据量场景）。"""

    cursor: str | None = Field(default=None, description="游标（首页为空）")
    limit: int = Field(default=20, ge=1, le=200, description="每批条数（默认 20，上限 200）")


class BaseCursorResponse[ItemT](BaseSchema):
    """游标分页响应。"""

    list: list[ItemT]
    next_cursor: str | None
    has_more: bool
