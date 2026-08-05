"""通用响应契约。

统一响应 {code, message, data}：code=0 成功，非 0 业务错误码（见 core/errors.py）；
分页响应 {list, total, page, size}（规划 API 设计规范节）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    """统一响应结构。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


class PageResponse[T](BaseModel):
    """分页响应结构。"""

    list: list[T]
    total: int
    page: int
    size: int


def ok(data: Any = None, message: str = "ok") -> ApiResponse[Any]:
    """成功响应快捷构造（code=0）。"""
    return ApiResponse(code=0, message=message, data=data)
