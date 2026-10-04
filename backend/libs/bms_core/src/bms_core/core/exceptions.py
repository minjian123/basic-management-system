"""core 层异常体系：统一业务异常基类、段位基类与常用子类。

- `BizError` 继承 `BaseFrameworkObject`（框架对象体系根：非数据对象 + `object_kind` 标识），同时是 `Exception`。
- **段位基类**（按错误码段位分基）：`GeneralError`（1xxxx 通用）、`AuthError`（2xxxx 认证）、
  `UserOrgError`（3xxxx 用户与组织）、`ConfigError`（4xxxx 系统配置）、`FileError`（5xxxx 文件）、
  `OpenTenantError`（8xxxx 开放 / 租户 / SSO）；新增同段位错误码继承对应段位基。
- **段内子段基类**（同段位内的能力域细分）：`CaptchaError`（认证段验证码 `201xx` 子段）、
  `PrintError`（文件段打印与导出 PDF `502xx` 子段）；新增子段错误码继承对应子段基，
  子类构造时预置码位与 HTTP 状态。
- 错误码统一登记于 `app/core/error_codes.py`（段位见《架构设计 · 接口与集成》「错误码分段」节）。
- `http_status` 承载传输层语义（404 / 401 / 403 / 409 / 500），其余业务失败统一 200。
"""

from typing import ClassVar

from bms_core.core.error_codes import ErrorCode
from bms_core.core.objects import BaseFrameworkObject


class BizError(BaseFrameworkObject, Exception):
    """业务异常基类：携带业务错误码、可选消息、HTTP 状态与数据。

    归位（09_05 批次 ②b）：错误体系根由 `BaseObject` 改挂**框架对象体系根**（非数据对象）；
    错误码段位（`GeneralError` / `AuthError` / … → `BizError`）与既有捕获语义不变。
    """

    object_kind: ClassVar[str] = "biz_error"

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


class NeedTenantError(AuthError):
    """需要选择租户（`20007` / HTTP 200；免登录链路无法唯一解析租户，需用户补充租户标识）。

    业务失败统一 HTTP 200（与 `20012` 同口径）——前端请求层仅在 2xx 解包业务码；响应 `data` 为
    空（不携带租户清单，避免暴露租户目录）。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化「需要选择租户」异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选；本异常不使用）。
        """
        BizError.__init__(self, ErrorCode.TENANT_REQUIRED, message, data=data)


class PasswordResetError(AuthError):
    """找回密码段（认证段内自助找回子段）异常基类；子类在构造时预置码位与 HTTP 状态。"""


class PasswordResetTokenError(PasswordResetError):
    """重置令牌无效 / 过期 / 已使用（`20005` / 400；三态合一防枚举）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化重置令牌异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.PASSWORD_RESET_TOKEN_INVALID, message, http_status=400, data=data)


class PasswordResetTooFrequentError(PasswordResetError):
    """找回密码请求过于频繁（`20006` / 429；账号 / IP / 用户维度限流命中）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化找回限流异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.PASSWORD_RESET_TOO_FREQUENT, message, http_status=429, data=data)


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


class SessionAuthError(SessionError):
    """登录态会话失效（请求鉴权链；`20012` / 401）。

    与 `SessionExpiredError`（同码、业务失败 HTTP 200）分场景：本异常用于**每请求登录态校验**
    （会话标记缺失 = 已踢出 / 登出 / 超限作废，或设备 / IP 不一致），一律 401 促前端重新登录。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化登录态会话失效异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SESSION_EXPIRED, message, http_status=401, data=data)


class SsoError(AuthError):
    """SSO 段（认证段内 `2005x` 子段）异常基类；子类在构造时预置码位与 HTTP 状态。"""


class SsoProviderNotFoundError(SsoError):
    """IdP 配置不存在或已停用（`20051` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化 IdP 配置不存在异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SSO_PROVIDER_NOT_FOUND, message, http_status=404, data=data)


class SsoCallbackError(SsoError):
    """回调校验失败（`state` / `nonce` / PKCE / ID Token / IdP 回传错误；`20052` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化回调校验失败异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SSO_CALLBACK_FAILED, message, http_status=400, data=data)


class SsoProviderUnavailableError(SsoError):
    """外部 IdP 不可达或超时（发现 / 换码 / 用户信息 / JWKS；`20053` / 503）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化外部 IdP 不可达异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SSO_PROVIDER_UNAVAILABLE, message, http_status=503, data=data)


class SsoIdentityUnmatchedError(SsoError):
    """未匹配本地用户且 JIT 未启用 / 被拒（`20054` / 403）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化身份未匹配异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SSO_IDENTITY_UNMATCHED, message, http_status=403, data=data)


class SsoIdentityConflictError(SsoError):
    """身份映射冲突（多行 / 唯一约束冲突；`20055` / 409）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化身份映射冲突异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.SSO_IDENTITY_CONFLICT, message, http_status=409, data=data)


class LocalLoginGuardError(SsoError):
    """本地登录保护（预留，本期不触发；`20056` / 429）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化本地登录保护异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.LOCAL_LOGIN_GUARD, message, http_status=429, data=data)


class EnterpriseIdpError(SsoError):
    """企微 / 钉钉免登适配错误基类（认证段内 `2005x` 子段）；子类预置码位与 HTTP 状态。

    与 `SsoProviderUnavailableError`（20053）等既有 SSO 码区分：本子段承载两平台
    「配置 / 授权 / 不可达」三类专用语义，供前端按平台给出更精确的提示；SSO 链路对其
    优先放行、不再折回 20052 / 20053。
    """


class WecomConfigError(EnterpriseIdpError):
    """企业微信配置缺失 / 非法（`20057` / 503）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化企业微信配置异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.WECOM_CONFIG, message, http_status=503, data=data)


class WecomAuthError(EnterpriseIdpError):
    """企业微信授权失败（`code` 无效 / 用户未授权 / 不在可见范围；`20058` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化企业微信授权异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.WECOM_AUTH, message, http_status=400, data=data)


class WecomUnavailableError(EnterpriseIdpError):
    """企业微信接口不可达 / 超时 / 响应非法（`20059` / 503）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化企业微信不可达异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.WECOM_UNAVAILABLE, message, http_status=503, data=data)


class DingtalkConfigError(EnterpriseIdpError):
    """钉钉配置缺失 / 非法（`20060` / 503）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化钉钉配置异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.DINGTALK_CONFIG, message, http_status=503, data=data)


class DingtalkAuthError(EnterpriseIdpError):
    """钉钉授权失败（`code` 无效 / 用户未授权；`20061` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化钉钉授权异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.DINGTALK_AUTH, message, http_status=400, data=data)


class DingtalkUnavailableError(EnterpriseIdpError):
    """钉钉接口不可达 / 超时 / 响应非法（`20062` / 503）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化钉钉不可达异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.DINGTALK_UNAVAILABLE, message, http_status=503, data=data)


class IdpManageError(SsoError):
    """外部 IdP 配置管理面错误基类（认证段内 `2006x` 子段）；子类预置码位与 HTTP 状态。

    覆盖租户级 IdP 配置 CRUD / 启停 / 连通性测试（02_06）；与登录链路 SSO 码（`20051`~`20062`）区分，
    走平台统一响应体（非 OIDC 端点标准错误 JSON）。
    """


class IdpNotFoundError(IdpManageError):
    """IdP 配置不存在（`20063` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化 IdP 配置不存在异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.IDP_NOT_FOUND, message, http_status=404, data=data)


class IdpConfigInvalidError(IdpManageError):
    """IdP 配置写入校验失败（必填 / 类型 / 枚举 / 未知键 / 密钥引用 / SSRF；`20064` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化 IdP 配置非法异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.IDP_CONFIG_INVALID, message, http_status=400, data=data)


class IdpKeyConflictError(IdpManageError):
    """IdP 标识冲突（同租户内未软删重复；`20065` / 409）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化 IdP 标识冲突异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.IDP_KEY_CONFLICT, message, http_status=409, data=data)


class IdpTestFailedError(IdpManageError):
    """IdP 连通性测试不可达 / 不可探测（`20066` / 502；`data` 携测试结果）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化连通性测试失败异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        BizError.__init__(self, ErrorCode.IDP_TEST_FAILED, message, http_status=502, data=data)


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


class PasswordPolicyViolationError(UserOrgError):
    """密码不符合复杂度策略（`30005` / 400；`data.violations` 为违规原因码清单）。"""

    def __init__(
        self,
        message: str | None = None,
        *,
        data: object | None = None,
        violations: tuple[str, ...] | None = None,
    ) -> None:
        """初始化密码策略违规异常。

        Args:
            message: 提示信息。
            data: 随附数据（未提供时由 `violations` 组装）。
            violations: 违规原因码清单（`PASSWORD_VIOLATIONS` 子集）。
        """
        payload = data if data is not None else {"violations": list(violations or ())}
        super().__init__(ErrorCode.PASSWORD_POLICY_VIOLATION, message, http_status=400, data=payload)


class PasswordReusedError(UserOrgError):
    """新密码与近 N 次历史密码重复（`30006` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化历史密码重复异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        super().__init__(ErrorCode.PASSWORD_REUSED, message, http_status=400, data=data)


class AccountLockError(UserOrgError):
    """账号锁定记录段（用户与组织段内子段）异常基类；子类在构造时预置码位与 HTTP 状态。"""


class AccountLockNotFoundError(AccountLockError):
    """锁定记录不存在或已解锁（`30007`；业务失败 HTTP 200，解锁 / 详情幂等语义）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化锁定记录不存在异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        super().__init__(ErrorCode.ACCOUNT_LOCK_NOT_FOUND, message, data=data)


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


class TenantAccessDeniedError(OpenTenantError):
    """目标租户不可访问（不在当前用户可访问集合；`80003` / 403）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.TENANT_ACCESS_DENIED, message, http_status=403, data=data)


class MultipleActiveTenantsError(OpenTenantError):
    """启用租户不唯一（免登录链路无法默认定位租户；`80004` / 409）。

    内部租户注册契约信号：远端租户源据内部端点响应映射为本异常，identity 免登录链路捕获后转
    认证段 `20007`（需要选择租户）。`data` 为空（不携带租户清单）。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化「启用租户不唯一」异常。

        Args:
            message: 提示信息。
            data: 随附数据（可选）。
        """
        super().__init__(ErrorCode.TENANT_SCOPE_AMBIGUOUS, message, http_status=409, data=data)


class OidcError(OpenTenantError):
    """OIDC Provider 子段（开放 / 租户 / SSO 段内 `8010x`）异常基类。

    携标准 OAuth2 错误串（`error`）与描述；端点边界据此转标准错误 JSON（不进平台统一响应体）。
    """

    error: str
    """标准 OAuth2 错误串（如 `invalid_request`）。"""

    def __init__(
        self,
        code: int,
        error: str,
        message: str | None = None,
        *,
        http_status: int = 400,
        data: object | None = None,
    ) -> None:
        super().__init__(code, message, http_status=http_status, data=data)
        self.error = error


class OidcInvalidRequestError(OidcError):
    """OIDC 请求非法（缺参 / `response_type` 不支持 / 未知客户端；`80101` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.OIDC_INVALID_REQUEST, "invalid_request", message, http_status=400, data=data)


class OidcInvalidClientError(OidcError):
    """客户端认证失败（未知客户端或密钥错误；`80102` / 401）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.OIDC_INVALID_CLIENT, "invalid_client", message, http_status=401, data=data)


class OidcInvalidGrantError(OidcError):
    """授权码无效 / 已消费 / 过期 / PKCE 不符（`80103` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.OIDC_INVALID_GRANT, "invalid_grant", message, http_status=400, data=data)


class OidcInvalidScopeError(OidcError):
    """scope 未注册或缺少 `openid`（`80104` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.OIDC_INVALID_SCOPE, "invalid_scope", message, http_status=400, data=data)


class OidcUnsupportedGrantError(OidcError):
    """`grant_type` 不支持（`80105` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(
            ErrorCode.OIDC_UNSUPPORTED_GRANT, "unsupported_grant_type", message, http_status=400, data=data
        )


class OidcAccessDeniedError(OidcError):
    """未登录且未配登录页（`80106` / 401）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.OIDC_ACCESS_DENIED, "access_denied", message, http_status=401, data=data)


class ClientError(OpenTenantError):
    """客户端注册子段（开放 / 租户 / SSO 段内 `8011x`）异常基类；走平台统一响应体。"""


class ClientNotFoundError(ClientError):
    """客户端不存在（`80111` / 404）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CLIENT_NOT_FOUND, message, http_status=404, data=data)


class ClientInvalidError(ClientError):
    """客户端字段非法（`80112` / 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CLIENT_INVALID, message, http_status=400, data=data)


class ClientConflictError(ClientError):
    """客户端标识冲突（`80113` / 409）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(ErrorCode.CLIENT_CONFLICT, message, http_status=409, data=data)
