"""租户自助与品牌能力域：我的租户 / 切换 / 品牌契约（真实取数与令牌换发随认证与租户管理阶段回补）。

- 取值集合：主题模式 `THEME_MODES`（亮色 / 暗色 / 跟随系统）、租户状态 `TENANT_STATUSES`
  （启用 / 停用）、切换生效方式 `TENANT_SWITCH_MODES`（经重发令牌 / 经会话内切换）。
- 默认品牌主色 `DEFAULT_BRAND_PRIMARY_COLOR`：未配置品牌时的回退主色。
- 数据源键助手 `build_tenant_db_key`：由租户编码派生数据源键（`tenant_{code}`）。
- 数据契约：`TenantSummary`（租户摘要）/ `TenantSelfOverview`（自助概览）/ `TenantSwitchResult`
  （切换结果）/ `TenantBrand`（品牌信息）。
- `BaseTenantSelfService`（`key = "tenant_self_service"`）：异步 `my_tenants` / `switch` / `brand`。
- 提供者 `get_tenant_self_service`（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：**当前租户的权威来源仍是租户解析链（子域名 → 请求头 → token，优先级不变）**——本契约不参与解析、
不读请求上下文，当前租户编码由调用方经入参传入；切换结果以「生效方式 + 是否需重发令牌 + 令牌」表达语义、
**不绑定传输**（令牌签发归认证阶段），切换后客户端经子域名或请求头携带目标租户、解析链次序不变。品牌信息
随租户配置提供，**登录前可用**（登录页需要）；未配置项回退平台默认。业务与前端只经本出口取租户自助数据，
**不自建租户列表 / 切换 / 品牌读取**。真实取数 / 令牌换发 / 品牌来源 / 平台超管租户管理随 RBAC、认证与
租户管理阶段回补。
"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request
from pydantic import Field

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.db.tenant import build_tenant_db_key
from bms_core.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_BRAND_PRIMARY_COLOR",
    "TENANT_STATUSES",
    "TENANT_SWITCH_MODES",
    "THEME_MODES",
    "BaseTenantSelfService",
    "TenantBrand",
    "TenantSelfOverview",
    "TenantSummary",
    "TenantSwitchResult",
    "build_tenant_db_key",
    "get_tenant_self_service",
]

THEME_MODES: tuple[str, ...] = ("light", "dark", "system")
"""品牌默认主题模式取值（亮色 / 暗色 / 跟随系统）。"""

TENANT_STATUSES: tuple[str, ...] = ("active", "suspended")
"""租户状态取值（启用 / 停用），对齐租户注册表状态列。"""

TENANT_SWITCH_MODES: tuple[str, ...] = ("token", "session")
"""切换生效方式取值（经重发令牌 / 经会话内切换），供实现侧校验。"""

DEFAULT_BRAND_PRIMARY_COLOR = "#1677ff"
"""平台默认品牌主色（未配置品牌时回退；与前端未配置时的回退主色一致）。"""


class TenantSummary(BaseSchema):
    """租户摘要（展示所需最小字段；标识以字符串输出，规避 JS 精度丢失）。"""

    id: str = Field(description="租户标识（真实实现回填租户主键字符串；占位以租户编码充当）")
    name: str = Field(description="租户名称")
    code: str | None = Field(default=None, description="租户编码")
    logo: str | None = Field(default=None, description="租户 Logo 地址")
    role_name: str | None = Field(default=None, description="该租户下的角色名")


class TenantSelfOverview(BaseSchema):
    """租户自助概览：我加入的租户列表 + 当前租户 + 是否多租户。"""

    tenants: list[TenantSummary] = Field(default_factory=list[TenantSummary], description="我加入的租户列表")
    current_code: str | None = Field(default=None, description="当前租户编码（由调用方从解析链上下文传入）")
    multi_tenant: bool = Field(default=False, description="是否多租户（租户列表长度 > 1）")


class TenantSwitchResult(BaseSchema):
    """切换结果：目标租户 / 数据源键 / 生效情况（令牌签发归认证阶段）。"""

    tenant_code: str = Field(description="目标租户编码")
    db_key: str = Field(description="目标数据源键（按租户编码派生）")
    applied: bool = Field(default=True, description="切换是否已生效")
    mode: str = Field(default="token", description="本次切换生效方式（token 经重发令牌 / session 经会话内切换）")
    reissue_token: bool = Field(default=False, description="是否要求调用方重取令牌")
    token: str | None = Field(default=None, description="新令牌（需重发且已签发时非空）")


class TenantBrand(BaseSchema):
    """品牌信息（未配置项留空，由消费方回退）。"""

    name: str | None = Field(default=None, description="品牌名称（页面标题 / 侧栏 / 登录页）")
    logo: str | None = Field(default=None, description="品牌 Logo 地址")
    favicon: str | None = Field(default=None, description="favicon 地址")
    primary_color: str = Field(default=DEFAULT_BRAND_PRIMARY_COLOR, description="品牌主色（十六进制）")
    default_mode: str = Field(default="system", description="租户默认主题模式（light / dark / system）")
    login_bg: str | None = Field(default=None, description="登录页背景图")
    allow_user_accent: bool = Field(default=True, description="是否允许用户覆盖强调色")
    disable_dark: bool = Field(default=False, description="是否禁用暗色")


class BaseTenantSelfService(BasePluggable, ABC):
    """租户自助契约：我的租户 / 切换租户 / 品牌信息。"""

    key: str = "tenant_self_service"
    plugin_key: str = "tenant_self_service"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def my_tenants(self, *, current_code: str | None = None) -> TenantSelfOverview:
        """取「我加入的租户」概览。

        Args:
            current_code: 当前租户编码（调用方从解析链上下文传入；实现负责标注）。

        Returns:
            TenantSelfOverview: 租户列表 + 当前租户编码 + 是否多租户。
        """

    @abstractmethod
    async def switch(self, code: str) -> TenantSwitchResult:
        """切换到目标租户（结果经令牌 / 会话生效，解析链优先级不变）。

        Args:
            code: 目标租户编码。

        Returns:
            TenantSwitchResult: 切换结果（生效方式 / 是否需重发令牌 / 令牌）。
        """

    @abstractmethod
    async def brand(self, *, code: str | None = None) -> TenantBrand:
        """取品牌信息（缺省当前租户；未命中回退平台默认品牌）。

        Args:
            code: 租户编码（None 表示当前租户）。

        Returns:
            TenantBrand: 品牌信息（名称 / 标识 / 主题等）。
        """


def get_tenant_self_service(request: Request) -> BaseTenantSelfService:
    """取应用级租户自助服务（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTenantSelfService: 应用装配的租户自助服务实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTenantSelfService",
        resolve_plugin(
            "tenant_self_service",
            settings.tenant_self_service.provider,
            expected_version=BaseTenantSelfService.contract_version,
        ),
    )
