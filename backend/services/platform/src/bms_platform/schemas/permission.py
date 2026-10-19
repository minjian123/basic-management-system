"""平台服务 schemas 层：权限内部契约（失效 + 数据来源只读出口，`02_04` / `04_01`）。

两条只读出口供 identity 侧「经契约取数」的数据来源实现使用（`04_01` 下沉后算法在基座、
数据仍在 platform）：

- `PermissionSubjectRequest` / `PermissionSubjectResult`：按用户返回聚合所需**原始数据**；
- `PermissionMetadataResult`：返回菜单 → 表单、权限码 id → 权限码两类索引。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)


class PermissionInvalidateRequest(BaseSchema):
    """权限快照失效请求（服务间内部契约）。"""

    user_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="受影响用户主键（空 = 全租户版本 +1）"
    )


class PermissionInvalidateResult(BaseSchema):
    """权限快照失效结果（服务间内部契约）。"""

    version: int = Field(description="递增后的租户权限版本号")


class PermissionSubjectRequest(BaseSchema):
    """按用户取聚合输入的请求（服务间内部契约）。"""

    user_id: int = Field(description="用户主键")


class PermissionGrantItem(BaseSchema):
    """授权行（授权类型 + 目标主键）。"""

    perm_type: str = Field(description="授权类型：menu / form / permission")
    target_id: int = Field(description="目标主键（按 perm_type 解释）")


class PermissionDataScopeItem(BaseSchema):
    """数据范围规则（字典类型 + 策略 + 规则行）。"""

    data_source_key: str = Field(description="字典类型主键（字符串化）")
    policy_type: str = Field(description="策略类型：select / region / match / extension")
    config: Annotated[ConcurrentStableList[ConcurrentStableDict[str, object]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="规则行（原样，交策略求值器解析）"
    )


class PermissionFieldItem(BaseSchema):
    """字段权限收窄项（未列出即全开）。"""

    form_id: int = Field(description="表单主键")
    field_key: str = Field(description="字段键")
    visible: bool = Field(description="读时是否返回")
    editable: bool = Field(description="写时是否接受")


class PermissionSubjectResult(BaseSchema):
    """按用户取回的聚合输入（服务间内部契约）。"""

    role_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="主体链收敛后的角色主键集合"
    )
    role_types: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="角色主键（字符串化）→ 角色类型"
    )
    grants: Annotated[ConcurrentStableList[PermissionGrantItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="授权行列表"
    )
    data_scope_rules: Annotated[ConcurrentStableList[PermissionDataScopeItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="数据范围规则列表"
    )
    field_perms: Annotated[ConcurrentStableList[PermissionFieldItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段权限收窄项（空 = 全开）"
    )


class PermissionMetadataResult(BaseSchema):
    """权限元数据索引（服务间内部契约）。"""

    version: int = Field(description="元数据版本号")
    menu_forms: Annotated[ConcurrentStableDict[str, ConcurrentStableList[int]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="菜单主键（字符串化）→ 关联表单主键列表"
    )
    permission_codes: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="权限码主键（字符串化）→ 权限码字符串"
    )
