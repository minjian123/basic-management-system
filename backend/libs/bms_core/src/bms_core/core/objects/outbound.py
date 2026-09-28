"""值对象体系 · 出站 HTTP 链层：出站响应。

**链结构（按公共段成层，本次 1 层）**：

- `BaseHttpResponseContract`（公共段 `status_code` + `headers` + `content`）——外部 HTTP 调用与
  服务间调用响应共用三元组。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseHttpResponseContract"]


@dataclass(frozen=True)
class BaseHttpResponseContract(BaseValueObject):
    """出站响应契约（角色链层）：HTTP 响应的**三元组**统一读面。

    公共段：`status_code`（状态码）+ `headers`（响应头）+ `content`（响应体）——外部出站调用
    （`HttpResponse`）与服务间调用（`ServiceResponse`）共用；重试判定、错误映射与日志按同一组字段读取。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("status_code", "headers", "content")
