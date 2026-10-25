"""租户管理面请求 / 响应契约（任务 `04_01`）。

集合字段一律以内联 `Annotated[集合类, CONTRACT_COLLECTION]` 声明（防契约 `$defs` 漂移）；
雪花 ID 经 `BaseSchema` 统一按字符串序列化。
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema
from bms_core.schemas.pagination import BasePageResponse

TenantStatus = Literal["provisioning", "active", "suspended"]
"""租户状态取值。"""

TenantModuleStatus = Literal["enabled", "disabled", "not_opened"]
"""租户模块展示状态（`not_opened` 为目录有、开通清单无）。"""

TenantModuleAction = Literal["enabled", "disabled"]
"""模块开关目标状态。"""

_CODE_PATTERN = "^[a-z][a-z0-9_]{1,31}$"
_DOMAIN_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"


class TenantCreateRequest(BaseSchema):
    """开通租户请求（code / name / domain + 模块勾选清单）。"""

    code: str = Field(min_length=2, max_length=32, pattern=_CODE_PATTERN, description="租户编码（全小写；库名基）")
    name: str = Field(min_length=1, max_length=128, description="租户名称")
    domain: str | None = Field(default=None, max_length=255, description="子域名（如 acme.bms.example.com）")
    expire_at: datetime | None = Field(default=None, description="到期时间（UTC）")
    modules: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[str](),
        description="开通模块勾选清单（仅可勾选产品模块；基础能力恒开通）",
    )


class TenantUpdateRequest(BaseSchema):
    """修改租户请求（名称 / 域名 / 到期时间；`code` 不可改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="租户名称")
    domain: str | None = Field(default=None, max_length=255, pattern=_DOMAIN_PATTERN, description="子域名")
    expire_at: datetime | None = Field(default=None, description="到期时间（UTC）")


class TenantQuotaItem(BaseSchema):
    """配额项（限额与用量）。"""

    quota_key: str = Field(description="配额维度（user_count / storage_bytes / open_calls）")
    limit_value: int = Field(ge=0, description="限额")
    used_value: int = Field(ge=0, description="已用量")


class TenantQuotaUpdateItem(BaseSchema):
    """配额配置项。"""

    quota_key: str = Field(description="配额维度（user_count / storage_bytes / open_calls）")
    limit_value: int = Field(ge=0, description="新限额")


class TenantQuotaUpdateRequest(BaseSchema):
    """配额配置请求（整组覆盖；未列出的维度保持原值）。"""

    items: Annotated[ConcurrentStableList[TenantQuotaUpdateItem], CONTRACT_COLLECTION] = Field(description="配额项清单")


class TenantModuleItem(BaseSchema):
    """租户模块项（目录 + 开通清单合并视图）。"""

    module_key: str = Field(description="模块标识")
    name: str = Field(description="模块名称")
    table_prefix: str = Field(description="表前缀")
    errcode_segment: str | None = Field(default=None, description="错误码段")
    optional: bool = Field(description="是否可勾选产品模块（基础能力恒开通）")
    status: TenantModuleStatus = Field(description="状态（enabled / disabled / not_opened）")
    opened_at: datetime | None = Field(default=None, description="最近开通时间（UTC）")


class TenantModuleUpdateRequest(BaseSchema):
    """租户模块开关请求。"""

    status: TenantModuleAction = Field(description="目标状态（enabled / disabled）")


class TenantModuleOption(BaseSchema):
    """开通向导模块选项（目录快照）。"""

    module_key: str = Field(description="模块标识")
    name: str = Field(description="模块名称")
    table_prefix: str = Field(description="表前缀")
    errcode_segment: str | None = Field(default=None, description="错误码段")
    service_group: str = Field(description="归属分组（foundation / capability / product）")
    catalog_status: str = Field(description="目录状态（enabled / disabled / planned）")
    optional: bool = Field(description="是否可勾选（产品模块且目录已启用）")


class TenantListItem(BaseSchema):
    """租户列表项。"""

    id: int = Field(description="租户主键")
    code: str = Field(description="租户编码")
    name: str = Field(description="租户名称")
    domain: str | None = Field(default=None, description="子域名")
    status: TenantStatus = Field(description="状态")
    expire_at: datetime | None = Field(default=None, description="到期时间（UTC）")
    modules: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[str](), description="已开通模块标识"
    )
    created_at: datetime = Field(description="创建时间（UTC）")
    version: int = Field(description="乐观锁版本")


class TenantList(BasePageResponse[TenantListItem]):
    """租户分页列表。"""


class TenantDetail(BaseSchema):
    """租户详情（含配额与模块）。"""

    id: int = Field(description="租户主键")
    code: str = Field(description="租户编码")
    name: str = Field(description="租户名称")
    domain: str | None = Field(default=None, description="子域名")
    status: TenantStatus = Field(description="状态")
    expire_at: datetime | None = Field(default=None, description="到期时间（UTC）")
    quotas: Annotated[ConcurrentStableList[TenantQuotaItem], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[TenantQuotaItem](), description="配额与用量"
    )
    modules: Annotated[ConcurrentStableList[TenantModuleItem], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[TenantModuleItem](), description="模块清单（含未开通）"
    )
    created_at: datetime = Field(description="创建时间（UTC）")
    updated_at: datetime = Field(description="更新时间（UTC）")
    version: int = Field(description="乐观锁版本")


class TenantProvisionResult(BaseSchema):
    """开通结果（初始管理员口令仅本次返回）。"""

    tenant: TenantDetail = Field(description="租户详情")
    admin_username: str = Field(description="初始系统管理员账号")
    initial_password: str = Field(description="初始口令（仅本次返回；首登强制改密）")


class ModuleStatusResponse(BaseSchema):
    """租户模块状态集（内部契约；模块门禁用）。"""

    enabled: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[str](), description="已开通且启用的模块标识"
    )
    disabled: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[str](), description="已开通但停用的模块标识"
    )
    version: int = Field(description="清单版本号（变更即递增）")


class QuotaConsumeRequest(BaseSchema):
    """配额占用 / 校验请求（内部契约）。"""

    tenant_id: int = Field(description="租户主键")
    quota_key: str = Field(description="配额维度（user_count / storage_bytes / open_calls）")
    amount: int = Field(gt=0, description="占用数量（正数）")


class QuotaReleaseRequest(BaseSchema):
    """配额释放请求（内部契约）。"""

    tenant_id: int = Field(description="租户主键")
    quota_key: str = Field(description="配额维度")
    amount: int = Field(gt=0, description="释放数量（正数）")


class QuotaResult(BaseSchema):
    """配额操作结果（内部契约）。"""

    allowed: bool = Field(description="是否放行（无配额行视为不限制）")
    used_value: int = Field(ge=0, description="操作后的已用量")
    limit_value: int | None = Field(default=None, description="限额（无配额行为空）")


class TenantModuleOptionList(BaseSchema):
    """开通向导模块选项清单。"""

    items: Annotated[ConcurrentStableList[TenantModuleOption], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[TenantModuleOption](), description="模块选项"
    )


class TenantModuleItemList(BaseSchema):
    """租户模块清单（三态）。"""

    items: Annotated[ConcurrentStableList[TenantModuleItem], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[TenantModuleItem](), description="模块项"
    )


class TenantQuotaItemList(BaseSchema):
    """租户配额与用量清单。"""

    items: Annotated[ConcurrentStableList[TenantQuotaItem], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[TenantQuotaItem](), description="配额项"
    )
