"""异常构造路径补齐用例（`bms_core/core/exceptions.py`）。

口径：**不做抽样**。`_EXCEPTIONS` 覆盖「可用缺省参数直接构造」的**全部** `BizError` 子类
（95 个），并由 `test_table_covers_every_default_constructible_exception` 反向枚举模块内
所有子类做完整性自校验——将来新增可缺省构造的异常类而未登记本表，用例直接失败，
不会像抽样清单那样静默留下覆盖率缺口。

无法无参构造的 10 个段位基类（`UserOrgError` / `RoleError` / `MenuError` / `OidcError` /
`FileError` / `PrintError` / `ClientError` / `OpenTenantError` / `AccountLockError` /
`GeneralError`）不在此表：它们的 `__init__` 只做透传，覆盖由各自子类完成。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

import pytest

from bms_core.core import exceptions
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import BizError, PasswordPolicyViolationError

# 异常类 → （错误码, HTTP 状态）。逐项断言「无参构造后的码值与状态」，
# 即覆盖各子类 `__init__` 的 `super().__init__(...)` 构造行。
_EXCEPTIONS: ConcurrentStableList[tuple[type[BizError], int, int]] = ConcurrentStableList(
    (
        (exceptions.AccountDisabledError, 20004, 401),
        (exceptions.AccountLockNotFoundError, 30007, 200),
        (exceptions.AccountLockedError, 20003, 401),
        (exceptions.AuthError, 20001, 401),
        (exceptions.CaptchaError, 20001, 401),
        (exceptions.CaptchaExpiredError, 20102, 404),
        (exceptions.CaptchaTooFrequentError, 20103, 429),
        (exceptions.CaptchaVerifyError, 20101, 200),
        (exceptions.CatalogError, 40003, 500),
        (exceptions.ClientConflictError, 80113, 409),
        (exceptions.ClientInvalidError, 80112, 400),
        (exceptions.ClientNotFoundError, 80111, 404),
        (exceptions.ConcurrentConflictError, 10004, 409),
        (exceptions.ConfigError, 40001, 500),
        (exceptions.ConflictError, 10003, 200),
        (exceptions.ConsistencyBarrierTimeout, 10011, 409),
        (exceptions.DataOwnershipError, 10008, 500),
        (exceptions.DatabaseUnavailableError, 10006, 503),
        (exceptions.DingtalkAuthError, 20061, 400),
        (exceptions.DingtalkConfigError, 20060, 503),
        (exceptions.DingtalkUnavailableError, 20062, 503),
        (exceptions.EnterpriseIdpError, 20001, 401),
        (exceptions.EventContractError, 10010, 500),
        (exceptions.IdpConfigInvalidError, 20064, 400),
        (exceptions.IdpKeyConflictError, 20065, 409),
        (exceptions.IdpManageError, 20001, 401),
        (exceptions.IdpNotFoundError, 20063, 404),
        (exceptions.IdpTestFailedError, 20066, 502),
        (exceptions.InternalError, 10000, 500),
        (exceptions.LocalLoginGuardError, 20056, 429),
        (exceptions.LoginFailedError, 20002, 401),
        (exceptions.MenuFieldKeyConflictError, 40205, 200),
        (exceptions.MenuFieldPermissionMismatchError, 40207, 200),
        (exceptions.MenuCodeConflictError, 40209, 200),
        (exceptions.MenuI18nRequiredError, 40208, 200),
        (exceptions.MenuLinkBrokenError, 40202, 200),
        (exceptions.MenuNotFoundError, 40201, 404),
        (exceptions.MenuPathConflictError, 40203, 200),
        (exceptions.MenuPermissionExistsError, 40210, 200),
        (exceptions.MenuPlatformReadonlyError, 40204, 403),
        (exceptions.MenuReferencedError, 40206, 200),
        (exceptions.MultipleActiveTenantsError, 80004, 409),
        (exceptions.TenantAdminNotFoundError, 82002, 404),
        (exceptions.TenantCodeExistsError, 82001, 409),
        (exceptions.TenantDomainConflictError, 82004, 409),
        (exceptions.TenantModuleDisabledError, 82008, 403),
        (exceptions.TenantModuleUnavailableError, 82007, 400),
        (exceptions.TenantProvisionFailedError, 82006, 500),
        (exceptions.TenantQuotaExceededError, 82005, 409),
        (exceptions.TenantStateConflictError, 82003, 409),
        (exceptions.NeedTenantError, 20007, 200),
        (exceptions.NotFoundError, 10002, 404),
        (exceptions.OidcAccessDeniedError, 80106, 401),
        (exceptions.OidcInvalidClientError, 80102, 401),
        (exceptions.OidcInvalidGrantError, 80103, 400),
        (exceptions.OidcInvalidRequestError, 80101, 400),
        (exceptions.OidcInvalidScopeError, 80104, 400),
        (exceptions.OidcUnsupportedGrantError, 80105, 400),
        (exceptions.OutboxDeliveryError, 10009, 500),
        (exceptions.ParamError, 10001, 200),
        (exceptions.PasswordPolicyViolationError, 30005, 400),
        (exceptions.PasswordResetError, 20001, 401),
        (exceptions.PasswordResetTokenError, 20005, 400),
        (exceptions.PasswordResetTooFrequentError, 20006, 429),
        (exceptions.PasswordReusedError, 30006, 400),
        (exceptions.PermissionError, 30001, 403),
        (exceptions.PluginError, 40002, 500),
        (exceptions.PrintArtifactNotFoundError, 50202, 404),
        (exceptions.PrintBatchLimitError, 50203, 200),
        (exceptions.PrintTemplateNotFoundError, 50201, 404),
        (exceptions.RateLimitError, 10005, 429),
        (exceptions.RedisUnavailableError, 10012, 503),
        (exceptions.RoleAssignedError, 30044, 200),
        (exceptions.RoleCodeExistsError, 30042, 200),
        (exceptions.RoleFieldMismatchError, 30049, 400),
        (exceptions.RoleNotFoundError, 30041, 404),
        (exceptions.RoleProtectedError, 30043, 200),
        (exceptions.RoleScopeValueInvalidError, 30047, 400),
        (exceptions.RoleSeparationConflictError, 30048, 403),
        (exceptions.RoleSubjectInvalidError, 30045, 200),
        (exceptions.RoleTargetInvalidError, 30046, 200),
        (exceptions.ServiceUnavailableError, 10007, 503),
        (exceptions.SessionAuthError, 20012, 401),
        (exceptions.SessionError, 20001, 401),
        (exceptions.SessionExpiredError, 20012, 200),
        (exceptions.SessionNotFoundError, 20011, 404),
        (exceptions.SessionRevokedError, 20013, 200),
        (exceptions.SsoCallbackError, 20052, 400),
        (exceptions.SsoError, 20001, 401),
        (exceptions.SsoIdentityConflictError, 20055, 409),
        (exceptions.SsoIdentityUnmatchedError, 20054, 403),
        (exceptions.SsoProviderNotFoundError, 20051, 404),
        (exceptions.SsoProviderUnavailableError, 20053, 503),
        (exceptions.TenantAccessDeniedError, 80003, 403),
        (exceptions.TenantNotFoundError, 80001, 404),
        (exceptions.TenantSuspendedError, 80002, 403),
        (exceptions.TransactionUnavailableError, 10013, 503),
        (exceptions.UserNotFoundError, 30002, 404),
        (exceptions.UserProtectedError, 30009, 403),
        (exceptions.UserReferencedError, 30011, 409),
        (exceptions.UserSeparationConflictError, 30010, 403),
        (exceptions.UsernameExistsError, 30003, 409),
        (exceptions.WecomAuthError, 20058, 400),
        (exceptions.WecomConfigError, 20057, 503),
        (exceptions.WecomUnavailableError, 20059, 503),
    )
)


def _construct(error_class: type[BizError], message: str | None = None) -> BizError:
    """按「消息位」构造异常实例（各子类签名差异对调用方透明）。

    Args:
        error_class: 异常类。
        message: 提示信息（缺省为 None）。

    Returns:
        BizError: 构造出的异常实例。
    """
    factory = cast("Callable[..., BizError]", error_class)
    return factory(message)


def _default_constructible() -> ConcurrentStableSet[type[BizError]]:
    """枚举模块内所有「可无参构造」的 `BizError` 子类。

    Returns:
        ConcurrentStableSet[type[BizError]]: 可无参构造的异常类集合。
    """
    found: ConcurrentStableSet[type[BizError]] = ConcurrentStableSet()
    for obj in vars(exceptions).values():
        if not inspect.isclass(obj) or not issubclass(obj, BizError) or obj is BizError:
            continue
        if obj.__module__ != exceptions.__name__:
            continue
        try:
            _construct(obj)
        except TypeError:
            continue
        found.add(obj)
    return found


def test_table_covers_every_default_constructible_exception() -> None:
    """完整性自校验：登记表必须覆盖全部可无参构造的异常子类。"""
    listed = ConcurrentStableSet(error_class for error_class, _, _ in _EXCEPTIONS)
    missing = _default_constructible() - listed
    assert len(missing) == 0, f"有可无参构造的异常类未登记：{sorted(cls.__name__ for cls in missing)}"


def test_table_has_no_duplicate_entries() -> None:
    """登记表不得重复登记同一异常类。"""
    listed = ConcurrentStableSet(error_class for error_class, _, _ in _EXCEPTIONS)
    assert len(listed) == len(_EXCEPTIONS)


@pytest.mark.parametrize(("error_class", "code", "http_status"), _EXCEPTIONS)
def test_exception_constructor_sets_code_and_status(error_class: type[BizError], code: int, http_status: int) -> None:
    """每个异常类的缺省构造都落正确错误码与 HTTP 状态。

    Args:
        error_class: 异常类。
        code: 期望错误码。
        http_status: 期望 HTTP 状态。
    """
    error = _construct(error_class)
    assert (error.code, error.http_status) == (code, http_status)
    assert error.message is None
    assert _construct(error_class, "boom").message == "boom"


def test_biz_error_str_falls_back_to_i18n_key() -> None:
    """`BizError.__str__`：有消息用消息，无消息回落 `error.<code>`。"""
    silent = exceptions.InternalError()
    assert str(silent) == "error.10000"
    assert str(exceptions.InternalError("炸了")) == "炸了"


def test_password_policy_violation_error_assembles_payload() -> None:
    """密码策略违规异常的 `violations` 装配与 `data` 透传。"""
    error = PasswordPolicyViolationError("弱口令", violations=ConcurrentStableList(("too_short", "no_digit")))
    assert error.data == {"violations": ["too_short", "no_digit"]}
    explicit = PasswordPolicyViolationError("弱口令", data={"x": 1})
    assert explicit.data == {"x": 1}


def test_user_separation_conflict_error_carries_code_and_status() -> None:
    """三权互斥（用户维度）异常：`30010` / 403，`data` 透传。"""
    error = exceptions.UserSeparationConflictError("同一用户不得兼任两类内置管理员")
    assert error.code == ErrorCode.USER_SEPARATION_CONFLICT == 30010
    assert error.http_status == 403
    assert exceptions.UserSeparationConflictError("x", data={"user_id": 7}).data == {"user_id": 7}
