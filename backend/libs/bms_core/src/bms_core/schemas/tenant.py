"""租户自助占位路由的请求 / 响应契约（与 `app/tenant/` 能力域契约字段一一对应）。

- `TenantSwitchRequest`：切换请求（对应能力域 `switch(code)` 入参）。
- `TenantSummaryResponse` / `TenantSelfOverviewResponse`：租户摘要与自助概览响应。
- `TenantSwitchResponse`：切换结果响应（对应能力域 `TenantSwitchResult`）。
- `TenantBrandResponse`：品牌信息响应（对应能力域 `TenantBrand`）。

口径：路由契约与能力域契约**字段名一致**，由路由层显式映射（不隐式透传字典），保证 OpenAPI 契约稳定；
字段一律 snake_case（前端 camelCase 契约由宿主数据通路注入层映射）。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema

__all__ = [
    "TenantBrandResponse",
    "TenantSelfOverviewResponse",
    "TenantSummaryResponse",
    "TenantSwitchRequest",
    "TenantSwitchResponse",
]


class TenantSummaryResponse(BaseSchema):
    """租户摘要响应。"""

    id: str = Field(description="租户标识（字符串）")
    name: str = Field(description="租户名称")
    code: str | None = Field(default=None, description="租户编码")
    logo: str | None = Field(default=None, description="租户 Logo 地址")
    role_name: str | None = Field(default=None, description="该租户下的角色名")


class TenantSelfOverviewResponse(BaseSchema):
    """租户自助概览响应。"""

    tenants: list[TenantSummaryResponse] = Field(
        default_factory=list[TenantSummaryResponse], description="我加入的租户列表"
    )
    current_code: str | None = Field(default=None, description="当前租户编码")
    multi_tenant: bool = Field(default=False, description="是否多租户（租户列表长度 > 1）")


class TenantSwitchRequest(BaseSchema):
    """切换租户请求：`{code}`。"""

    code: str = Field(min_length=1, description="目标租户编码")


class TenantSwitchResponse(BaseSchema):
    """切换结果响应。"""

    tenant_code: str = Field(description="目标租户编码")
    db_key: str = Field(description="目标数据源键（按租户编码派生）")
    applied: bool = Field(default=True, description="切换是否已生效")
    mode: str = Field(default="token", description="本次切换生效方式（token / session）")
    reissue_token: bool = Field(default=False, description="是否要求调用方重取令牌")
    token: str | None = Field(default=None, description="新令牌（需重发且已签发时非空）")


class TenantBrandResponse(BaseSchema):
    """品牌信息响应（未配置项为 null，由消费方回退）。"""

    name: str | None = Field(default=None, description="品牌名称")
    logo: str | None = Field(default=None, description="Logo 地址")
    favicon: str | None = Field(default=None, description="favicon 地址")
    primary_color: str = Field(description="品牌主色（十六进制）")
    default_mode: str = Field(description="租户默认主题模式（light / dark / system）")
    login_bg: str | None = Field(default=None, description="登录页背景图")
    allow_user_accent: bool = Field(description="是否允许用户覆盖强调色")
    disable_dark: bool = Field(description="是否禁用暗色")
