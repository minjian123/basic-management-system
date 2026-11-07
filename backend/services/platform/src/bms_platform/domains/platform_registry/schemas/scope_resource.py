"""schemas 层作用域资源类型契约（07D `01_01`）：运营视图记录 + 运营态变更请求。

字段与 `sys_scope_resource_type` 对齐（表结构以表文件为准）。**两态分开表达**：`status` 是产品声明态
（声明通道写），`admin_status` 是平台运营态（停用接口写）；`effective_status` 为派生值（两者同时启用
才 `enabled`），供运营面直读，不需要调用方自己算。

运营态变更的「谁在何时停用」不在响应里重复下发——审计链是唯一出处（`sys_scope_resource_type`
纳入 `AuditCapturer`，按记录主键可查）。
"""

from typing import Annotated

from pydantic import Field

from bms_core.schemas.base import BaseSchema


class ScopeResourceTypeResponse(BaseSchema):
    """作用域资源类型记录响应（与 `sys_scope_resource_type` 业务字段对齐）。"""

    resource_type_key: str
    name: str
    name_pattern: str
    max_length: int
    retention_days: int
    removal_policy: str
    product_key: str
    status: str
    admin_status: str
    effective_status: str
    declaration_version: int


class ScopeResourceTypeStatusRequest(BaseSchema):
    """运营态变更请求（幂等：与现值一致时不写库、不记审计）。"""

    admin_status: Annotated[str, Field(min_length=1, max_length=16, description="运营态（enabled / disabled）")]
