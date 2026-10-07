"""认证与身份服务 schemas 层：SSO 入口 / 回调与服务间概要契约。"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema
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

    items: Annotated[ConcurrentStableList[SsoProviderItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="可用 IdP 清单"
    )


class SsoAuthorizeInfo(BaseSchema):
    """SSO 授权 URL 响应体（前端渲染二维码 / 初始化平台内嵌登录组件用）。"""

    authorize_url: str = Field(description="外部授权入口 URL")
    state: str = Field(description="流程状态（一次性；回调校验）")
    expires_in: int = Field(description="流程状态有效期（秒）")


class SsoCallbackResult(BaseSchema):
    """SSO 回调成功回退响应体（未配置 `success_redirect` 时的 JSON 形态）。"""

    tenant: str = Field(description="登录生效租户编码")


class PlatformProfileUser(ServiceDto):
    """platform 内部用户概要（按 id 取数）。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    status: str = Field(default="", description="账号状态（enabled / disabled）")
    locale: str | None = Field(default=None, description="语言偏好")
    timezone: str | None = Field(default=None, description="时区偏好")
    pwd_reset_required: bool = Field(default=False, description="是否需强制改密（密码超有效期）")


class PlatformProfileResult(ServiceDto):
    """platform 内部用户概要查询契约 DTO。"""

    found: bool = Field(default=False, description="用户是否存在")
    user: PlatformProfileUser | None = Field(default=None, description="用户概要（found=true 时返回）")


class PlatformUserCreateResult(ServiceDto):
    """platform 内部 JIT 建号结果契约 DTO（撞名 `created=false`）。"""

    created: bool = Field(default=False, description="是否建号成功")
    reason: str | None = Field(default=None, description="未建号原因（username_conflict）")
    user: PlatformProfileUser | None = Field(default=None, description="新建用户概要（created=true 时返回）")


class SsoIdentityItem(BaseSchema):
    """SSO 身份绑定项（`sso:bind` 只读端点）。"""

    idp_key: str = Field(description="映射键（{tenant_id}:{provider_key}）")
    external_id: str = Field(description="外部身份主体（OIDC 取 sub）")
    tenant_id: str = Field(description="租户主键（雪花 id 字符串）")


class SsoIdentityList(BaseSchema):
    """SSO 身份绑定清单响应体。"""

    items: Annotated[ConcurrentStableList[SsoIdentityItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="绑定清单"
    )
