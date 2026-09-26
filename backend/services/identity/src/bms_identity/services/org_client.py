"""认证与身份服务 services 层：org 内部凭据接口客户端（服务间契约调用）。

- 经 `service_client` 基座走公开契约面（`/api/v1/org/internal/credentials/*`），出站附自签服务 JWT
  （`sub=identity`）+ `tenant` claim，供 org 解析租户库；不经网关。
- 失败语义：下游不可达 / 非 2xx / 响应契约非法 → `ServiceUnavailableError`（10007/503，fail-closed，
  不降级为「密码错误」）。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest, ServiceResponse
from bms_identity.schemas.auth import OrgLoginState, OrgVerifyResult

ORG_SERVICE = "org"
"""凭据主数据归属服务标识。"""

_SCOPES: tuple[str, ...] = ("credential",)
"""内部凭据调用所需服务 JWT scope。"""


class OrgCredentialClient(BaseObject):
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
        """调 org 更新账号密码。

        Args:
            tenant: 租户编码。
            account: 登录账号。
            new_password: 新口令明文。

        Returns:
            bool: 是否更新成功。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法（10007/503）。
        """
        data = await self._post("update-password", tenant, {"account": account, "new_password": new_password})
        return bool(data.get("updated"))

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
        response = await self._client.call(
            ServiceRequest(
                service=ORG_SERVICE,
                method="POST",
                path=f"/api/v1/org/internal/credentials/{action}",
                tenant=tenant,
                json_body=body,
                policy=ServiceCallPolicy(scopes=_SCOPES),
            )
        )
        payload = _payload(response)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ServiceUnavailableError(f"org 凭据接口返回契约非法：{action}")
        return cast("dict[str, object]", data)


def _payload(response: ServiceResponse) -> dict[str, object]:
    """解析服务响应为统一响应体（非 2xx / 非对象 / code≠0 即服务不可用）。

    Args:
        response: 服务间调用响应。

    Returns:
        dict[str, object]: 统一响应体。

    Raises:
        ServiceUnavailableError: 非 2xx / 非对象 / 业务码非 0（10007/503）。
    """
    if response.status_code != 200:
        raise ServiceUnavailableError(f"org 凭据接口不可用（HTTP {response.status_code}）")
    payload = response.payload()
    if not isinstance(payload, dict):
        raise ServiceUnavailableError("org 凭据接口返回非法响应")
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        raise ServiceUnavailableError("org 凭据接口返回非法响应")
    return body
