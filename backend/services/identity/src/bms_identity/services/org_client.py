"""认证与身份服务 services 层：org 内部接口客户端（服务间契约调用）。

- 经 `service_client` 基座走公开契约面（`/api/v1/org/internal/credentials/*` 与
  `/api/v1/org/internal/users/profile`），出站附自签服务 JWT（`sub=identity`）+ `tenant` claim，
  供 org 解析租户库；不经网关。
- 失败语义：下游不可达 / 非 2xx / 响应契约非法 → `ServiceUnavailableError`（10007/503，fail-closed，
  不降级为「密码错误」）。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.exceptions import (
    PasswordPolicyViolationError,
    PasswordReusedError,
    ServiceUnavailableError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest, ServiceResponse
from bms_identity.schemas.auth import OrgLoginState, OrgUpdatePasswordResult, OrgVerifyResult
from bms_identity.schemas.password_reset import OrgResetTargetResult
from bms_identity.schemas.sso import OrgProfileResult, OrgUserCreateResult

ORG_SERVICE = "org"
"""凭据主数据归属服务标识。"""

_SCOPES: tuple[str, ...] = ("credential",)
"""内部凭据调用所需服务 JWT scope。"""

_PROFILE_SCOPES: tuple[str, ...] = ("user_profile",)
"""用户概要接口所需服务 JWT scope。"""

_CREDENTIAL_INTERFACE = "org 凭据接口"
_PROFILE_INTERFACE = "org 用户接口"


class OrgCredentialClient(BaseFrameworkObject):
    """org 凭据接口客户端（verify / update-password / login-state）。"""

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（经 `get_service_client` 注入）。
        """
        self._client = client

    async def verify(self, tenant: str | None, account: str, password: str) -> OrgVerifyResult:
        """调 org 校验账号口令。

        Args:
            tenant: 租户编码（随服务 JWT claim 传递）。
            account: 登录账号。
            password: 口令明文。

        Returns:
            OrgVerifyResult: 校验结果。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        data = await self._post("verify", tenant, {"account": account, "password": password})
        return OrgVerifyResult.model_validate(data)

    async def update_password(self, tenant: str | None, account: str, new_password: str) -> bool:
        """调 org 更新账号密码（策略闸门：复杂度 / 历史重复）。

        Args:
            tenant: 租户编码。
            account: 登录账号。
            new_password: 新口令明文。

        Returns:
            bool: 是否更新成功；账号不存在返回 False。

        Raises:
            PasswordPolicyViolationError: 不符合复杂度策略（30005；data 带 violations）。
            PasswordReusedError: 命中近 N 次历史密码（30006）。
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        data = await self._post("update-password", tenant, {"account": account, "new_password": new_password})
        outcome = OrgUpdatePasswordResult.model_validate(data)
        if outcome.updated:
            return True
        if outcome.reason == "policy_violation":
            raise PasswordPolicyViolationError(violations=tuple(outcome.violations))
        if outcome.reason == "history_reused":
            raise PasswordReusedError()
        return False

    async def login_state(
        self,
        tenant: str | None,
        account: str,
        *,
        success: bool,
        failed_count: int | None = None,
        lock_seconds: int | None = None,
    ) -> OrgLoginState:
        """调 org 写回登录态（成功清零 / 失败计数与锁定）。

        Args:
            tenant: 租户编码。
            account: 登录账号。
            success: 本次登录是否成功。
            failed_count: 失败计数（失败时传）。
            lock_seconds: 锁定时长（秒；失败且达阈值时传）。

        Returns:
            OrgLoginState: 写回后的登录态。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        body: dict[str, object] = {"account": account, "success": success}
        if failed_count is not None:
            body["failed_count"] = failed_count
        if lock_seconds is not None:
            body["lock_seconds"] = lock_seconds
        data = await self._post("login-state", tenant, body)
        return OrgLoginState.model_validate(data)

    async def user_profile(self, tenant: str | None, user_id: int) -> OrgProfileResult:
        """调 org 取用户概要（SSO 回调定位用户后）。

        Args:
            tenant: 租户编码（随服务 JWT claim 传递）。
            user_id: 本地用户主键。

        Returns:
            OrgProfileResult: 概要结果（`found=False` 表示用户不存在）。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        data = await self._post_path(
            "/api/v1/org/internal/users/profile",
            _PROFILE_SCOPES,
            tenant,
            {"user_id": user_id},
            interface=_PROFILE_INTERFACE,
        )
        return OrgProfileResult.model_validate(data)

    async def reset_target(self, tenant: str | None, identifier: str) -> OrgResetTargetResult:
        """调 org 解析找回密码重置目标（账号 / 手机 / 邮箱 → 通道与投递目标）。

        Args:
            tenant: 租户编码（随服务 JWT claim 传递）。
            identifier: 账号 / 手机号 / 邮箱。

        Returns:
            OrgResetTargetResult: 解析结果。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        data = await self._post_path(
            "/api/v1/org/internal/users/reset-target",
            _PROFILE_SCOPES,
            tenant,
            {"identifier": identifier},
            interface=_PROFILE_INTERFACE,
        )
        return OrgResetTargetResult.model_validate(data)

    async def create_user(
        self,
        tenant: str | None,
        *,
        username: str,
        name: str,
        locale: str | None = None,
        timezone: str | None = None,
    ) -> OrgUserCreateResult:
        """调 org 建号（JIT 首登；单次「用户名空闲即建」，撞名由调用侧换后缀重试）。

        Args:
            tenant: 租户编码（随服务 JWT claim 传递）。
            username: 登录账号（调用侧已清洗）。
            name: 昵称 / 显示名。
            locale: 语言偏好（可空）。
            timezone: 时区偏好（可空）。

        Returns:
            OrgUserCreateResult: 建号结果（`created=False` + `reason` 表示撞名）。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        data = await self._post_path(
            "/api/v1/org/internal/users/create",
            _PROFILE_SCOPES,
            tenant,
            {"username": username, "name": name, "locale": locale, "timezone": timezone},
            interface=_PROFILE_INTERFACE,
        )
        return OrgUserCreateResult.model_validate(data)

    async def _post(self, action: str, tenant: str | None, body: dict[str, object]) -> dict[str, object]:
        """发起内部凭据 POST（公开契约面 + 服务 JWT），解析统一响应体 `data`。

        Args:
            action: 动作路径段（verify / update-password / login-state）。
            tenant: 租户编码（随服务 JWT claim）。
            body: JSON 请求体。

        Returns:
            dict[str, object]: 统一响应 `data`。

        Raises:
            ServiceUnavailableError: 下游不可达 / 非 2xx / 响应契约非法（10007/503）。
        """
        return await self._post_path(
            f"/api/v1/org/internal/credentials/{action}",
            _SCOPES,
            tenant,
            body,
            interface=_CREDENTIAL_INTERFACE,
        )

    async def _post_path(
        self,
        path: str,
        scopes: tuple[str, ...],
        tenant: str | None,
        body: dict[str, object],
        *,
        interface: str,
    ) -> dict[str, object]:
        """发起内部 POST（公开契约面 + 服务 JWT），解析统一响应体 `data`。

        Args:
            path: 公开契约路径。
            scopes: 服务 JWT scope。
            tenant: 租户编码（随服务 JWT claim）。
            body: JSON 请求体。
            interface: 错误提示用接口名称。

        Returns:
            dict[str, object]: 统一响应 `data`。

        Raises:
            ServiceUnavailableError: 下游不可达 / 非 2xx / 响应契约非法（10007/503）。
        """
        response = await self._client.call(
            ServiceRequest(
                service=ORG_SERVICE,
                method="POST",
                path=path,
                tenant_id=tenant,
                json_body=body,
                policy=ServiceCallPolicy(scopes=scopes),
            )
        )
        payload = _payload(response, interface)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ServiceUnavailableError(f"{interface}返回契约非法")
        return cast("dict[str, object]", data)


def _payload(response: ServiceResponse, interface: str) -> dict[str, object]:
    """解析服务响应为统一响应体（非 2xx / 非对象 / code≠0 即服务不可用）。

    Args:
        response: 服务间调用响应。
        interface: 错误提示用接口名称。

    Returns:
        dict[str, object]: 统一响应体。

    Raises:
        ServiceUnavailableError: 非 2xx / 非对象 / 业务码非 0（10007/503）。
    """
    if response.status_code != 200:
        raise ServiceUnavailableError(f"{interface}不可用（HTTP {response.status_code}）")
    payload = response.payload()
    if not isinstance(payload, dict):
        raise ServiceUnavailableError(f"{interface}返回非法响应")
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        raise ServiceUnavailableError(f"{interface}返回非法响应")
    return body
