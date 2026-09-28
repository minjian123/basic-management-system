"""值对象体系 · 租户链层：链路中携带的租户视图。

**链结构（按公共段成层，本次 1 层）**：

- `BaseTenantViewContract`（公共段 `name` + `domain` + `status` + `tenant_id`）——租户展示信息与归属。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseTenantViewContract"]


@dataclass(frozen=True)
class BaseTenantViewContract(BaseValueObject):
    """租户视图契约（角色链层）：会话 / 授权链路中携带的租户展示信息与归属。

    公共段：`name` + `domain` + `status` + `tenant_id`（名称、域名、状态、租户主键）。

    说明：租户**代码**字段名历史不统一（`TenantContext.tenant_code` / `TenantSnapshot.code`；
    全库 `tenant_code` 出现 99 处 / 53 文件）——经消费方评估**不重命名字段**，改由本层
    `CODE_FIELD` 声明承载字段（调用方按 `CODE_FIELD` 取用）。

    > 本层**不提供**统一读取属性：`code` 会与 `TenantSnapshot.code`（dataclass 字段）同名冲突，
    > 而本仓库约定不使用 `pyright: ignore`（pyright 严格模式 0 错误），故只做映射声明。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("name", "domain", "status", "tenant_id")
    CODE_FIELD: ClassVar[str] = ""
    """本类承载租户代码的字段名（成员声明）。"""
