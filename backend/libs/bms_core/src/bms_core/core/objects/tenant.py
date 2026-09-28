"""值对象体系 · 租户链层：链路中携带的租户视图。

**链结构（按公共段成层，本次 1 层）**：

- `BaseTenantViewContract`（公共段 `code` + `name` + `domain` + `status` + `tenant_id`）——租户展示信息与归属。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseTenantViewContract"]


@dataclass(frozen=True)
class BaseTenantViewContract(BaseValueObject):
    """租户视图契约（角色链层）：会话 / 授权链路中携带的租户展示信息与归属。

    公共段：`code` + `name` + `domain` + `status` + `tenant_id`（租户**自身**编码、名称、域名、状态、主键）。

    说明：租户编码按「编码命名规则」（《后端开发规范》命名节）——租户视图对象承载的是租户**自身**
    编码，统一叫 `code`（与 `TenantSnapshot.code` / `sys_tenant.code` 一致）；引用租户编码的字段
    （`EdgeIdentity.tenant_code` 等）才用 `tenant_code`。本层**不提供**统一读取属性（`code` 会与
    `TenantSnapshot.code` dataclass 字段同名冲突），成员直接声明 `code` 字段。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("code", "name", "domain", "status", "tenant_id")
