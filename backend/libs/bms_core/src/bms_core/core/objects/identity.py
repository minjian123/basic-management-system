"""值对象体系 · 身份链层：请求侧调用方身份与身份源回读画像。

**链结构（按公共段成层，本次 2 层平级）**：

- `BaseRequestIdentityContract`（公共段 `subject` + `user_id` + `scopes` + `service_identity` + `session_id`）
  ——请求上下文解析出的调用方身份；
- `BaseIdentityProfileContract`（公共段 `subject` + `username` + `name` + `email`）——身份源回读的用户画像。

**公共段口径**：层以 `COMMON_FIELDS` 声明公共段（成员必须同时具备这些字段），字段仍由成员自身声明；
可空性 / 具体类型由成员各自约定（层只约束**字段存在与语义**）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseIdentityProfileContract", "BaseRequestIdentityContract"]


@dataclass(frozen=True)
class BaseRequestIdentityContract(BaseValueObject):
    """请求身份契约（角色链层）：单次请求上下文中解析出的调用方身份。

    公共段：`subject` + `user_id` + `scopes` + `service_identity` + `session_id`
    （主体、用户主键、授权范围、服务身份、会话标识——调用方身份的统一可读面）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("subject", "user_id", "scopes", "service_identity", "session_id")


@dataclass(frozen=True)
class BaseIdentityProfileContract(BaseValueObject):
    """身份画像契约（角色链层）：内部 / 外部身份源回读的用户画像。

    公共段：`subject` + `username` + `name` + `email`（主体、登录名、姓名、邮箱）。

    说明：**可空性不统一**（`IdentityUser.name` 与两类的 `email` 可空，`ExternalIdentity.name` 非空）——
    层只约定字段存在与语义，可空性由成员声明。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("subject", "username", "name", "email")
