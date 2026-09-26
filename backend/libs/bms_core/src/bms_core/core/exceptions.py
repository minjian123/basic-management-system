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

from bms_core.core.base import BaseObject
from bms_core.core.error_codes import ErrorCode


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


class LoginFailedError(AuthError):
    """登录失败：账号不存在或密码错误（`20002`；同码不区分，防账号枚举）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化登录失败异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.LOGIN_FAILED, message, http_status=401, data=data)


class AccountLockedError(AuthError):
    """账号已锁定（`20003` / 401）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化账号锁定异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.ACCOUNT_LOCKED, message, http_status=401, data=data)


class AccountDisabledError(AuthError):
    """账号已停用（`20004` / 401）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化账号停用异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.ACCOUNT_DISABLED, message, http_status=401, data=data)


class SessionError(AuthError):
    """会话段（认证段内会话治理子段）异常基类；子类在构造时预置码位与 HTTP 状态。"""


class SessionNotFoundError(SessionError):
    """会话不存在（`20011` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化会话不存在异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SESSION_NOT_FOUND, message, http_status=404, data=data)


class SessionExpiredError(SessionError):
    """会话已失效（已过期 / 已登出；`20012`，业务失败 HTTP 200）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化会话失效异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SESSION_EXPIRED, message, data=data)


class SessionRevokedError(SessionError):
    """会话已撤销（重复踢出已撤销会话；`20013`，业务失败 HTTP 200）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化会话已撤销异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SESSION_REVOKED, message, data=data)


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


class ServiceUnavailableError(GeneralError):
    """下游服务不可用（超时 / 不可达 / 重试耗尽 / 熔断断开；`10007` / 503）。

    服务间调用失败时 `data` 携降级动作与依赖名（`BaseFallbackPolicy` 产物），
    供调用方按动作实现降级路径（基座只给动作、不接管调用链）。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.SERVICE_UNAVAILABLE, message, http_status=503, data=data)


class DataOwnershipError(GeneralError):
    """数据所有权违规（`enforce` 模式下跨服务库访问被拒；`10008` / 500）。

    运行时守卫（`boundary/table.py`）命中跨服务表访问且模式为 `enforce` 时抛出，
    调用方事务回滚；`warn` 模式只记录与计数、不抛错。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.DATA_OWNERSHIP, message, http_status=500, data=data)


class OutboxDeliveryError(GeneralError):
    """发件箱投递异常（`10009` / 500）。

    投递器取待投递 / 编排发生非预期异常时抛出；**单条事件发布失败不抛错**，
    走指数退避重试 / 转死信（看板人工处理）。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.OUTBOX_DELIVERY, message, http_status=500, data=data)


class EventContractError(GeneralError):
    """事件契约违规（`10010` / 500）。

    事件名 / 版本非法、未登记契约签发（`enforce` 模式）、契约不兼容、
    消费方不支持事件主版本时抛出；调用方事务回滚，消费侧转重试 / 死信。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.EVENT_CONTRACT, message, http_status=500, data=data)


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


class CatalogError(ConfigError):
    """服务目录与契约登记校验失败（启动期致命；错误码 `40003`）。

    用于启动接库校验与离线清单校验的冲突 / 非法拒绝（见需求 03-2）。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化服务目录异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.CATALOG, message, http_status=500, data=data)


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
