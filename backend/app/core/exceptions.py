"""core 层异常体系：统一业务异常基类、段位基类与常用子类。

- `BizError` 继承 `BaseObject`（纳入 L0 继承体系，统一序列化 / 字符串输出），同时是 `Exception`。
- **段位基类**（按错误码段位分基）：`GeneralError`（1xxxx 通用）、`AuthError`（2xxxx 认证）、
  `UserOrgError`（3xxxx 用户与组织）、`ConfigError`（4xxxx 系统配置）、`FileError`（5xxxx 文件）、
  `OpenTenantError`（8xxxx 开放 / 租户 / SSO）；新增同段位错误码继承对应段位基。
- **段内子段基类**（同段位内的能力域细分）：`CaptchaError`（认证段验证码 `201xx` 子段）、
  `PrintError`（文件段打印与导出 PDF `502xx` 子段）；新增子段错误码继承对应子段基，
  子类构造时预置码位与 HTTP 状态。
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


class GeneralError(BizError):
    """通用段（`1xxxx`）异常基类。"""


class InternalError(GeneralError):
    """系统内部错误（未预期）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.INTERNAL, message, http_status=500, data=data)


class ParamError(GeneralError):
    """参数 / 校验失败。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.PARAM, message, data=data)


class NotFoundError(GeneralError):
    """资源不存在。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.NOT_FOUND, message, http_status=404, data=data)


class ConflictError(GeneralError):
    """业务冲突（唯一键 / 状态）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CONFLICT, message, data=data)


class ConcurrentConflictError(GeneralError):
    """并发冲突（乐观锁 / 重试超限）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CONCURRENT_CONFLICT, message, http_status=409, data=data)


class AuthError(BizError):
    """认证段（`2xxxx`）异常基类；本阶段码位 `20001`（认证失效）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.AUTH, message, http_status=401, data=data)


class CaptchaError(AuthError):
    """验证码段（认证段内 `201xx` 子段）异常基类；子类在构造时预置码位与 HTTP 状态。"""


class CaptchaVerifyError(CaptchaError):
    """验证码校验不通过（`20101`；业务失败，HTTP 统一 200）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化验证码校验异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.CAPTCHA_VERIFY_FAILED, message, data=data)


class CaptchaExpiredError(CaptchaError):
    """验证码不存在或已过期（`20102` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化验证码失效异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.CAPTCHA_EXPIRED, message, http_status=404, data=data)


class CaptchaTooFrequentError(CaptchaError):
    """验证码发送过于频繁（`20103` / 429）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化验证码频次异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.CAPTCHA_TOO_FREQUENT, message, http_status=429, data=data)


class RateLimitError(GeneralError):
    """限流拒绝（超出配额；防重放失败归 `AuthError`）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.RATE_LIMIT, message, http_status=429, data=data)


class DatabaseUnavailableError(GeneralError):
    """数据库不可用（主库故障只读降级时写被拒 / 无可用副本；`10006` / 503）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.DATABASE_UNAVAILABLE, message, http_status=503, data=data)


class UserOrgError(BizError):
    """用户与组织段（`3xxxx`）异常基类。"""


class PermissionError(UserOrgError):
    """权限不足。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.PERMISSION, message, http_status=403, data=data)


class ConfigError(BizError):
    """系统配置段（`4xxxx`）异常基类：配置加载 / 校验失败（启动期致命，走启动失败路径）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CONFIG, message, http_status=500, data=data)


class PluginError(ConfigError):
    """插件注册 / 构建校验失败（启动期致命；错误码 `40002`）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化插件异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.PLUGIN, message, http_status=500, data=data)


class FileError(BizError):
    """文件段（`5xxxx`）异常基类：上传 / 下载 / 分片 / 导入导出与打印导出。"""


class PrintError(FileError):
    """打印与导出 PDF 子段（文件段内 `502xx`）异常基类；子类在构造时预置码位与 HTTP 状态。"""


class PrintTemplateNotFoundError(PrintError):
    """打印模板不存在（`50201` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化打印模板不存在异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.PRINT_TEMPLATE_NOT_FOUND, message, http_status=404, data=data)


class PrintArtifactNotFoundError(PrintError):
    """导出产物不存在或已过期（`50202` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化导出产物不存在异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.PRINT_ARTIFACT_NOT_FOUND, message, http_status=404, data=data)


class PrintBatchLimitError(PrintError):
    """批量打印超限（`50203`；业务失败，HTTP 统一 200）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化批量打印超限异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.PRINT_BATCH_LIMIT_EXCEEDED, message, data=data)


class OpenTenantError(BizError):
    """开放 / 租户 / SSO 段（`8xxxx`）异常基类。"""


class TenantNotFoundError(OpenTenantError):
    """租户不存在（未知租户；`80001` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.TENANT_NOT_FOUND, message, http_status=404, data=data)


class TenantSuspendedError(OpenTenantError):
    """租户已停用（`80002` / 403；引擎强制回收后拒绝访问）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.TENANT_SUSPENDED, message, http_status=403, data=data)
