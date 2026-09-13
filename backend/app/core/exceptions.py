"""core 层异常体系：统一业务异常基类与常用子类。

- `BizError` 继承 `BaseObject`（纳入 L0 继承体系，统一序列化 / 字符串输出），同时是 `Exception`。
- 错误码统一登记于 `app/core/error_codes.py`（段位见《架构设计 · 接口与集成》「错误码分段」节）。
- `http_status` 承载传输层语义（404 / 401 / 403 / 409 / 500），其余业务失败统一 200。
"""

from app.core.base import BaseObject
from app.core.error_codes import ErrorCode


class BizError(BaseObject, Exception):
    """业务异常基类：携带业务错误码、可选消息、HTTP 状态与数据。"""

    code: int
    message: str | None
    http_status: int
    data: object | None

    def __init__(
        self,
        code: int,
        message: str | None = None,
        *,
        http_status: int = 200,
        data: object | None = None,
    ) -> None:
        """初始化业务异常。

        Args:
            code: 业务错误码（`ErrorCode` 或模块自定义码）。
            message: 提示信息（缺省由前端按 `error.{code}` 映射）。
            http_status: HTTP 状态码（默认 200，业务失败统一）。
            data: 随附数据（可选）。
        """
        super().__init__(message or f"error.{int(code)}")
        self.code = int(code)
        self.message = message
        self.http_status = http_status
        self.data = data

    def __str__(self) -> str:
        """字符串输出：优先消息，缺省回落 i18n key。"""
        return self.message or f"error.{self.code}"


class InternalError(BizError):
    """系统内部错误（未预期）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.INTERNAL, message, http_status=500, data=data)


class ParamError(BizError):
    """参数 / 校验失败。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.PARAM, message, data=data)


class NotFoundError(BizError):
    """资源不存在。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.NOT_FOUND, message, http_status=404, data=data)


class ConflictError(BizError):
    """业务冲突（唯一键 / 状态）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CONFLICT, message, data=data)


class ConcurrentConflictError(BizError):
    """并发冲突（乐观锁 / 重试超限）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CONCURRENT_CONFLICT, message, http_status=409, data=data)


class AuthError(BizError):
    """认证失效。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.AUTH, message, http_status=401, data=data)


class PermissionError(BizError):
    """权限不足。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.PERMISSION, message, http_status=403, data=data)
