"""core 层异常体系：统一业务异常基类与常用子类。

错误码段位（与《架构设计 · 接口与集成》「错误码分段」节一致，一经发布稳定不变）：

- `1xxxx` 通用（参数校验 / 资源不存在 / 冲突 / 系统内部）
- `2xxxx` 认证、`3xxxx` 用户与组织…… 其余段位随对应模块登记

`http_status` 承载传输层语义（404 / 401 / 403 / 409 / 500），其余业务失败统一 200。
"""


class BizError(Exception):
    """业务异常基类：携带业务错误码、可选消息、HTTP 状态与数据。"""

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
            code: 业务错误码。
            message: 提示信息（缺省由前端按 `error.{code}` 映射）。
            http_status: HTTP 状态码（默认 200，业务失败统一）。
            data: 随附数据（可选）。
        """
        super().__init__(message or f"error.{code}")
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data


class InternalError(BizError):
    """系统内部错误（未预期）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(10000, message, http_status=500, data=data)


class ParamError(BizError):
    """参数 / 校验失败。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(10001, message, http_status=200, data=data)


class NotFoundError(BizError):
    """资源不存在。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(10002, message, http_status=404, data=data)


class ConflictError(BizError):
    """业务冲突（唯一键 / 状态）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(10003, message, http_status=200, data=data)


class ConcurrentConflictError(BizError):
    """并发冲突（乐观锁 / 重试超限）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(10004, message, http_status=409, data=data)


class AuthError(BizError):
    """认证失效。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(20001, message, http_status=401, data=data)


class PermissionError(BizError):
    """权限不足。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(30001, message, http_status=403, data=data)
