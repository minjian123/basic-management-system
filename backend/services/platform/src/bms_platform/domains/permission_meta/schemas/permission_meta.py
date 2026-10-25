"""权限元数据契约：业务码 / 动作码 / 权限码的请求与响应模型（继承 `BaseSchema`）。

- 归属业务域 `permission_meta`；集合字段一律 `Annotated[集合类, CONTRACT_COLLECTION]`（出口经基座规整为内置容器）；
- 菜单 / 表单 / 按钮 / 字段契约见 `domains/menu_form/schemas/menu.py`。
"""

from typing import Annotated, Literal

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema

I18nNames = Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION]
"""多语言名称映射（locale → 文案）。"""

EnabledStatus = Literal["enabled", "disabled"]
"""启用状态取值。"""


class BusinessCreateRequest(BaseSchema):
    """新增业务码请求（`code` 创建后只读）。"""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="业务码（小写单词 / kebab-case；创建后只读）",
    )
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称映射（locale → 文案）；必含请求语言文案")


class BusinessUpdateRequest(BaseSchema):
    """更新业务码请求（`code` 不可改，只改名称与状态）。"""

    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称映射（locale → 文案）；必含请求语言文案")


class ActionCreateRequest(BaseSchema):
    """新增动作码请求（`code` 创建后只读）。"""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="动作码（全局动词 / kebab-case；创建后只读）",
    )
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称映射（locale → 文案）；必含请求语言文案")


class ActionUpdateRequest(BaseSchema):
    """更新动作码请求（`code` 不可改，只改名称与状态）。"""

    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称映射（locale → 文案）；必含请求语言文案")


class PermissionCreateRequest(BaseSchema):
    """手工新增权限码组合（组合创建后只读）。"""

    business_id: int = Field(gt=0, description="业务码 ID")
    action_id: int = Field(gt=0, description="动作码 ID")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")


class PermissionUpdateRequest(BaseSchema):
    """更新权限码（组合不可换绑，仅状态）。"""

    status: EnabledStatus = Field(description="状态（enabled/disabled）")


class PermissionGenerateRequest(BaseSchema):
    """批量补生成缺失权限码组合请求（范围为空 = 全部启用项）。"""

    business_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="限定业务码 ID 清单（空 = 全部启用业务码）"
    )
    action_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="限定动作码 ID 清单（空 = 全部启用动作码）"
    )
    include_disabled: bool = Field(default=False, description="是否包含停用的业务 / 动作码")


class PermissionGenerateResult(BaseSchema):
    """批量补生成结果计数。"""

    created: int = Field(description="新建组合数")
    restored: int = Field(description="恢复软删除组合数")
    skipped: int = Field(description="已存在跳过数")


class BusinessItem(BaseSchema):
    """业务码行（纯资源维度）。"""

    id: int = Field(description="业务码主键")
    code: str = Field(description="业务码")
    name: str = Field(description="名称（默认文案）")
    status: str = Field(description="状态（enabled/disabled）")
    permission_count: int = Field(default=0, description="该业务码下的权限码数量（含停用）")
    i18n: I18nNames = Field(description="多语言名称（locale → 文案）")


class BusinessList(BaseSchema):
    """业务码清单。"""

    items: Annotated[ConcurrentStableList[BusinessItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="业务码行列表"
    )


class ActionItem(BaseSchema):
    """动作码行（全局动词维度）。"""

    id: int = Field(description="动作码主键")
    code: str = Field(description="动作码")
    name: str = Field(description="名称（默认文案）")
    status: str = Field(description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称（locale → 文案）")


class ActionList(BaseSchema):
    """动作码清单。"""

    items: Annotated[ConcurrentStableList[ActionItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="动作码行列表"
    )


class PermissionItem(BaseSchema):
    """权限码行（业务码 × 动作码组合，真正权限码）。"""

    id: int = Field(description="权限码主键")
    code: str = Field(description="权限码（业务码:动作码）")
    name: str = Field(default="", description="权限码名称（业务名·动作名，按 locale 本地化）")
    business_id: int = Field(description="业务码 ID")
    business_code: str = Field(description="业务码")
    action_id: int = Field(description="动作码 ID")
    action_code: str = Field(description="动作码")
    status: str = Field(description="状态（enabled/disabled）")


class PermissionList(BaseSchema):
    """权限码清单。"""

    items: Annotated[ConcurrentStableList[PermissionItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="权限码行列表"
    )
