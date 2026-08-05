"""请求级上下文（contextvars）。

request_id 与租户标识经 contextvars 贯穿请求全链路：
中间件写入，日志处理器（structlog.contextvars.merge_contextvars）与数据源路由读取。
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_code_var: ContextVar[str | None] = ContextVar("tenant_code", default=None)
tenant_id_var: ContextVar[int | None] = ContextVar("tenant_id", default=None)


def set_request_id(request_id: str) -> None:
    """写入当前请求的 request_id。"""
    request_id_var.set(request_id)


def get_request_id() -> str | None:
    """读取当前请求的 request_id。"""
    return request_id_var.get()


def set_tenant(tenant_code: str | None, tenant_id: int | None = None) -> None:
    """写入当前请求的租户上下文（tenant_id 阶段三 sys_tenant 表就绪后使用）。"""
    tenant_code_var.set(tenant_code)
    tenant_id_var.set(tenant_id)


def get_tenant_code() -> str | None:
    """读取当前请求的租户编码；平台级请求返回 None。"""
    return tenant_code_var.get()


def get_tenant_id() -> int | None:
    """读取当前请求的租户 ID（阶段三启用）。"""
    return tenant_id_var.get()
