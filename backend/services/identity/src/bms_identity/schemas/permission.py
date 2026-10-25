"""认证与身份服务 schemas 层：platform 权限数据只读契约（`04_01` 下沉后 identity 侧取数用）。

契约形状与 platform 侧 `bms_platform.domains.permission_meta.schemas.permission` 的响应体一致——两侧同源
（`04_01` 把算法下沉基座后，identity 取的是**原始数据**，在本地跑同一引擎）。
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


class PlatformPermissionGrant(BaseSchema):
    """授权行（授权类型 + 目标主键）。"""

    perm_type: str = Field(description="授权类型：menu / form / permission")
    target_id: int = Field(description="目标主键（按 perm_type 解释）")


class PlatformPermissionDataScope(BaseSchema):
    """数据范围规则（字典类型 + 策略 + 规则行）。"""

    data_source_key: str = Field(description="字典类型主键（字符串化）")
    policy_type: str = Field(description="策略类型：select / region / match / extension")
    config: Annotated[ConcurrentStableList[ConcurrentStableDict[str, object]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="规则行（原样，交策略求值器解析）"
    )


class PlatformPermissionField(BaseSchema):
    """字段权限收窄项（未列出即全开）。"""

    form_id: int = Field(description="表单主键")
    field_key: str = Field(description="字段键")
    visible: bool = Field(description="读时是否返回")
    editable: bool = Field(description="写时是否接受")


class PlatformPermissionSubject(BaseSchema):
    """按用户取回的聚合输入（platform 内部只读契约响应）。"""

    role_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="主体链收敛后的角色主键集合"
    )
    role_types: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="角色主键（字符串化）→ 角色类型"
    )
    grants: Annotated[ConcurrentStableList[PlatformPermissionGrant], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="授权行列表"
    )
    data_scope_rules: Annotated[ConcurrentStableList[PlatformPermissionDataScope], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="数据范围规则列表"
    )
    field_perms: Annotated[ConcurrentStableList[PlatformPermissionField], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段权限收窄项（空 = 全开）"
    )


class PlatformPermissionMetadata(BaseSchema):
    """权限元数据索引（platform 内部只读契约响应）。"""

    version: int = Field(default=0, description="元数据版本号")
    menu_forms: Annotated[ConcurrentStableDict[str, ConcurrentStableList[int]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="菜单主键（字符串化）→ 关联表单主键列表"
    )
    permission_codes: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="权限码主键（字符串化）→ 权限码字符串"
    )
