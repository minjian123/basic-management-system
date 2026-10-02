"""org 凭据接口客户端测试（Kiwi 2194）：成功解析与失败分支（服务不可用）。"""

import json

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    PasswordPolicyViolationError,
    PasswordReusedError,
    ServiceUnavailableError,
)
from bms_core.core.serialization import normalize_collections
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_identity.services.org_client import OrgCredentialClient


def _resp(status: int, payload: object) -> ServiceResponse:
    """构造服务响应。

    Args:
        status: HTTP 状态码。
        payload: 响应体。

    Returns:
        ServiceResponse: 响应。
    """
    return ServiceResponse(status_code=status, content=json.dumps(normalize_collections(payload)).encode())


class _Scripted(BaseServiceClient):
    """测试替身：固定返回一条响应。"""

    plugin_name = "scripted"

    def __init__(self, response: ServiceResponse) -> None:
        self._response = response

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """返回固定响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 响应。
        """
        return self._response


@pytest.mark.kiwi_id(2194)
async def test_org_client_success_paths() -> None:
    """verify / update-password / login-state 成功解析。"""
    verify = OrgCredentialClient(
        _Scripted(
            _resp(
                200,
                {
                    "code": 0,
                    "data": {
                        "found": True,
                        "valid": True,
                        "locked": False,
                        "status": "enabled",
                        "rehashed": False,
                        "user": {"id": 1, "username": "admin", "name": "管理员", "locale": None, "timezone": None},
                    },
                },
            )
        )
    )
    result = await verify.verify("demo", "admin", "p")
    assert result.found and result.valid and result.user is not None and result.user.username == "admin"

    updated = await OrgCredentialClient(_Scripted(_resp(200, {"code": 0, "data": {"updated": True}}))).update_password(
        "demo", "admin", "new"
    )
    assert updated is True

    state = await OrgCredentialClient(
        _Scripted(_resp(200, {"code": 0, "data": {"failed_count": 2, "locked_until": None, "last_login_at": None}}))
    ).login_state("demo", "admin", success=False, failed_count=2, lock_seconds=None)
    assert state.failed_count == 2


@pytest.mark.kiwi_id(2194)
async def test_org_client_failure_branches() -> None:
    """非 2xx / 业务码非 0 / data 非法一律抛服务不可用（fail-closed）。"""
    with pytest.raises(ServiceUnavailableError):
        await OrgCredentialClient(_Scripted(_resp(503, {"code": 0, "data": {}}))).verify("demo", "a", "b")

    with pytest.raises(ServiceUnavailableError):
        await OrgCredentialClient(_Scripted(_resp(200, {"code": 500, "data": {}}))).verify("demo", "a", "b")

    with pytest.raises(ServiceUnavailableError):
        await OrgCredentialClient(_Scripted(_resp(200, "not-a-dict"))).verify("demo", "a", "b")

    with pytest.raises(ServiceUnavailableError):
        await OrgCredentialClient(_Scripted(_resp(200, {"code": 0, "data": "nope"}))).verify("demo", "a", "b")


@pytest.mark.kiwi_id(2209)
async def test_org_client_update_password_policy_mapping() -> None:
    """改密策略闸门映射：复杂度违规 30005（带 violations）/ 历史重复 30006 / 账号不存在 False。"""

    def _client(data: ConcurrentStableDict[str, object]) -> OrgCredentialClient:
        return OrgCredentialClient(_Scripted(_resp(200, {"code": 0, "data": data})))

    with pytest.raises(PasswordPolicyViolationError) as weak:
        await _client(
            ConcurrentStableDict(
                {"updated": False, "reason": "policy_violation", "violations": ConcurrentStableList(["too_short"])}
            )
        ).update_password("demo", "admin", "weak")
    assert weak.value.data == {"violations": ["too_short"]}

    with pytest.raises(PasswordReusedError):
        await _client(ConcurrentStableDict({"updated": False, "reason": "history_reused"})).update_password(
            "demo", "admin", "OldPass1!"
        )

    assert (
        await _client(ConcurrentStableDict({"updated": False, "reason": "not_found"})).update_password(
            "demo", "nobody", "x"
        )
        is False
    )
    assert (
        await _client(ConcurrentStableDict({"updated": True, "reason": ""})).update_password(
            "demo", "admin", "NewSecret1!"
        )
        is True
    )
