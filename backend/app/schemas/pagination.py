"""schemas 层公共分页契约：页码与游标分页的请求 / 响应基类。

分页请求继承排序契约 `BaseSortQuery`，列表接口天然带统一排序参数（见 `app/schemas/sorting.py`）。

- 页码分页**限深**：`page ≤ [pagination].max_page`（默认 100），超限按参数非法拒绝（10001）；
  大数据量列表走游标分页（keyset，键集随 `app/schemas/cursor.py`），不受页码限深影响；
- 游标为 keyset 令牌（排序键 + 主键），首页不传，逐页由响应 `next_cursor` 回传。
"""

from pydantic import Field, field_validator

from app.core.config import get_settings
from app.schemas.base import BaseSchema
from app.schemas.sorting import BaseSortQuery


class BasePageQuery(BaseSortQuery):
    """页码分页请求（含排序参数；页码限深）。"""

    page: int = Field(default=1, ge=1, description="页码（从 1 起；上限取 [pagination].max_page）")
    size: int = Field(default=20, ge=1, le=200, description="每页条数（默认 20，上限 200）")

    @field_validator("page")
    @classmethod
    def _within_depth(cls, value: int) -> int:
        """页码限深校验（超限按参数非法；大数据量请用游标分页）。

        Args:
            value: 页码。

        Returns:
            int: 页码（校验通过）。

        Raises:
            ValueError: 页码超出 `[pagination].max_page`。
        """
        max_page = get_settings().pagination.max_page
        if value > max_page:
            raise ValueError(f"页码超出上限（page ≤ {max_page}；大数据量列表请用游标分页）")
        return value


class BasePageResponse[ItemT](BaseSchema):
    """页码分页响应。"""

    list: list[ItemT]
    total: int
    page: int
    size: int


class BaseCursorQuery(BaseSortQuery):
    """游标分页请求（日志 / 审计等大数据量场景，含排序参数）。"""

    cursor: str | None = Field(default=None, description="keyset 游标（首页为空；由响应 next_cursor 回传）")
    limit: int = Field(default=20, ge=1, le=200, description="每批条数（默认 20，上限 200）")


class BaseCursorResponse[ItemT](BaseSchema):
    """游标分页响应。"""

    list: list[ItemT]
    next_cursor: str | None
    has_more: bool
