"""自定义图标占位路由的请求 / 响应契约（与 `app/icon/` 能力域契约字段一一对应）。

- `IconCreateRequest` / `IconUpdateRequest`：图标新增 / 更新请求（更新全字段可选，None 表示不变）。
- `IconResponse` / `IconListResponse`：图标定义与清单响应。
- `IconDeleteResponse`：删除结果响应（`{deleted}`）。

口径：路由契约与能力域契约**字段名一致**，由路由层显式映射（不隐式透传字典），保证 OpenAPI 契约稳定；
字段一律 snake_case（前端 camelCase 契约由宿主数据通路注入层映射）；图标键格式由路由层显式校验，
故此处只约束长度、不重复声明格式。
"""

from pydantic import Field

from app.schemas.base import BaseSchema

__all__ = [
    "IconCreateRequest",
    "IconDeleteResponse",
    "IconListResponse",
    "IconResponse",
    "IconUpdateRequest",
]


class IconCreateRequest(BaseSchema):
    """图标新增请求：`{code, name, category, tags?, svg}`。"""

    code: str = Field(min_length=1, max_length=64, description="图标键（kebab-case，租户内唯一）")
    name: str = Field(min_length=1, max_length=128, description="图标名称")
    category: str = Field(min_length=1, description="图标分组（分类）")
    tags: list[str] = Field(default_factory=list[str], description="标签（搜索用）")
    svg: str = Field(min_length=1, description="SVG 内容（内联）")


class IconUpdateRequest(BaseSchema):
    """图标更新请求：`{name?, category?, tags?, svg?, status?}`（None 表示该项不变）。"""

    name: str | None = Field(default=None, max_length=128, description="图标名称")
    category: str | None = Field(default=None, description="图标分组")
    tags: list[str] | None = Field(default=None, description="标签（搜索用）")
    svg: str | None = Field(default=None, description="SVG 内容")
    status: str | None = Field(default=None, description="状态（active 启用 / disabled 停用）")


class IconResponse(BaseSchema):
    """图标定义响应。"""

    id: str = Field(description="图标标识（字符串化主键；非业务标识）")
    code: str = Field(description="图标键（契约唯一业务标识）")
    name: str = Field(description="图标名称")
    category: str = Field(description="图标分组")
    tags: list[str] = Field(description="标签（搜索用）")
    svg: str = Field(description="SVG 内容")
    status: str = Field(description="状态（active 启用 / disabled 停用）")
    icon_key: str = Field(description="图标键派生值（custom:{图标键}）")


class IconListResponse(BaseSchema):
    """图标清单响应。"""

    icons: list[IconResponse] = Field(description="图标清单")


class IconDeleteResponse(BaseSchema):
    """图标删除结果响应。"""

    deleted: bool = Field(description="是否删除了既有图标")
