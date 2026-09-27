"""认证与身份服务 schemas 层：外部 IdP 配置管理面契约（CRUD / 启停 / 连通性）。

- 响应 `config` 为**脱敏后**对象（密钥引用只返前缀 `env:***`）；`secret_configured` 供前端展示。
- `idp_key` 格式由请求契约约束（非法走参数校验 `10001`）；`status` / `type` 语义校验在服务层（`20064`）。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema

_IDP_KEY_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
"""租户内标识 slug（小写字母 / 数字开头，允许 `-` / `_`）。"""


class IdpProviderItem(BaseSchema):
    """IdP 配置列表 / 详情项（`config` 已脱敏，密钥引用不返明文）。"""

    id: int = Field(description="主键")
    name: str = Field(description="显示名")
    idp_key: str = Field(description="租户内标识 slug")
    type: str = Field(description="协议类型（oidc / cas / wecom / dingtalk）")
    icon: str = Field(default="", description="图标（可空）")
    config: dict[str, object] = Field(default_factory=dict[str, object], description="脱敏后的协议配置对象")
    secret_configured: bool = Field(default=False, description="是否已配置密钥引用")
    status: str = Field(description="状态（enabled/disabled）")
    sort: int = Field(default=0, description="登录页排序")


class IdpProviderCreateRequest(BaseSchema):
    """新建 IdP 配置请求。"""

    name: str = Field(min_length=1, max_length=64, description="显示名")
    idp_key: str = Field(pattern=_IDP_KEY_PATTERN, description="租户内标识 slug")
    type: str = Field(description="协议类型（oidc / cas / wecom / dingtalk）")
    icon: str = Field(default="", max_length=255, description="图标（可空）")
    config: dict[str, object] = Field(default_factory=dict[str, object], description="协议配置对象")
    status: str = Field(default="enabled", description="状态（enabled/disabled，缺省 enabled）")
    sort: int = Field(default=0, description="登录页排序")


class IdpProviderUpdateRequest(BaseSchema):
    """修改 IdP 配置请求（局部更新；`type` / `idp_key` 不可改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=64, description="显示名")
    icon: str | None = Field(default=None, max_length=255, description="图标")
    config: dict[str, object] | None = Field(default=None, description="协议配置对象（全量替换）")
    sort: int | None = Field(default=None, description="登录页排序")


class IdpProviderStatusRequest(BaseSchema):
    """启停请求。"""

    status: str = Field(description="目标状态（enabled/disabled）")


class IdpProviderTestRequest(BaseSchema):
    """草稿连通性测试请求（不落库）。"""

    type: str = Field(description="协议类型")
    config: dict[str, object] = Field(default_factory=dict[str, object], description="协议配置对象")
    idp_key: str = Field(default="draft", description="租户内标识（派生回调地址用；可占位）")


class IdpProviderTestResult(BaseSchema):
    """连通性测试结果（摘要诊断，不含敏感信息）。"""

    reachable: bool = Field(description="端点是否可达 / 凭据是否有效")
    protocol: str = Field(default="", description="协议类型")
    status: int | None = Field(default=None, description="命中的 HTTP 状态码（可选）")
    detail: str = Field(default="", description="摘要诊断（不含原始报文 / 密钥）")
