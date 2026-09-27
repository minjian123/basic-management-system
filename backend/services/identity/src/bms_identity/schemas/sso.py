"""认证与身份服务 schemas 层：SSO 入口 / 回调与服务间概要契约。"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema
from bms_core.schemas.service import ServiceDto


class SsoProviderItem(BaseSchema):
    """SSO 入口清单项（前端按此渲染登录方式）。"""

    idp_key: str = Field(description="IdP 标识（租户内稳定 slug；路由参数）")
    name: str = Field(description="显示名")
    icon: str = Field(default="", description="图标（可空）")
    type: str = Field(description="协议类型（oidc / cas / wecom / dingtalk）")
    sort: int = Field(default=0, description="排序值（升序）")


class SsoProviderList(BaseSchema):
    """SSO 入口清单响应体。"""

    items: list[SsoProviderItem] = Field(default_factory=list[SsoProviderItem], description="可用 IdP 清单")


class SsoCallbackResult(BaseSchema):
    """SSO 回调成功回退响应体（未配置 `success_redirect` 时的 JSON 形态）。"""

    tenant: str = Field(description="登录生效租户编码")


class OrgProfileUser(ServiceDto):
    """org 内部用户概要（按 id 取数）。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    status: str = Field(default="", description="账号状态（enabled / disabled）")
    locale: str | None = Field(default=None, description="语言偏好")
    timezone: str | None = Field(default=None, description="时区偏好")


class OrgProfileResult(ServiceDto):
    """org 内部用户概要查询契约 DTO。"""

    found: bool = Field(default=False, description="用户是否存在")
    user: OrgProfileUser | None = Field(default=None, description="用户概要（found=true 时返回）")


class OrgUserCreateResult(ServiceDto):
    """org 内部 JIT 建号结果契约 DTO（撞名 `created=false`）。"""

    created: bool = Field(default=False, description="是否建号成功")
    reason: str | None = Field(default=None, description="未建号原因（username_conflict）")
    user: OrgProfileUser | None = Field(default=None, description="新建用户概要（created=true 时返回）")


class SsoIdentityItem(BaseSchema):
    """SSO 身份绑定项（`sso:bind` 只读端点）。"""

    idp_key: str = Field(description="映射键（{tenant_code}:{provider_key}）")
    external_id: str = Field(description="外部身份主体（OIDC 取 sub）")
    tenant_id: str = Field(description="租户编码")


class SsoIdentityList(BaseSchema):
    """SSO 身份绑定清单响应体。"""

    items: list[SsoIdentityItem] = Field(default_factory=list[SsoIdentityItem], description="绑定清单")
