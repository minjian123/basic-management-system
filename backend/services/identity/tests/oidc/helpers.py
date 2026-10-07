"""OIDC Provider 测试替身与流程助手（Kiwi 2202）。"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import cast
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.serialization import normalize_collections
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

CLIENT_ID = "bms-demo-client"
CLIENT_SECRET = "demo-secret"
REDIRECT_URI = "http://rp.test/callback"
ISSUER = "http://localhost:8000/api/v1/oidc"
TENANT = "demo"
TENANT_ID = "1001"
TENANT_HEADERS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"X-Tenant-ID": TENANT})
USER_ID = 1001


def pkce() -> tuple[str, str]:
    """生成 PKCE (verifier, challenge)（S256）。

    Returns:
        tuple[str, str]: (code_verifier, code_challenge)。
    """
    verifier = "verifier-0123456789abcdefghijklmnopqrstuvwxyzABCDEFG"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def authorize_code(
    client: AsyncClient,
    *,
    client_id: str = CLIENT_ID,
    redirect_uri: str = REDIRECT_URI,
    scope: str = "openid",
    state: str = "st-1",
    nonce: str = "nonce-1",
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    headers: ConcurrentStableDict[str, str] | None = None,
) -> tuple[str, str]:
    """发起授权并返回 (code, location)。

    Args:
        client: 测试客户端。
        client_id: 客户端标识。
        redirect_uri: 回调地址。
        scope: 申请 scope。
        state: 透传状态。
        nonce: 透传 nonce。
        code_challenge: PKCE 挑战（可选）。
        code_challenge_method: PKCE 方法（可选）。
        headers: 请求头（缺省带租户头）。

    Returns:
        tuple[str, str]: (授权码, 回跳地址)。
    """
    params: ConcurrentStableDict[str, str] = ConcurrentStableDict(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "nonce": nonce,
        }
    )
    if code_challenge:
        params.set("code_challenge", code_challenge)
        params.set("code_challenge_method", code_challenge_method or "S256")
    response = await client.get("/api/v1/oidc/authorize", params=params, headers=headers or TENANT_HEADERS)
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    return query.get("code", [""])[0], location


class FakeOidcPlatformClient(BaseServiceClient):
    """测试替身：内存 platform 用户概要接口（`/platform_client/internal/users/profile`）。"""

    plugin_name = "oidc_fake"

    def __init__(self) -> None:
        """初始化（默认登记一个启用用户）。"""
        self.users: ConcurrentStableDict[int, ConcurrentStableDict[str, object]] = ConcurrentStableDict(
            {USER_ID: ConcurrentStableDict({"username": "alice", "name": "Alice", "status": "enabled"})}
        )
        self.fail = False
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    def set_user(
        self,
        user_id: int,
        *,
        username: str = "alice",
        name: str = "Alice",
        status: str = "enabled",
    ) -> None:
        """登记 / 覆盖测试用户。

        Args:
            user_id: 用户主键。
            username: 账号。
            name: 显示名。
            status: 状态。
        """
        self.users.set(user_id, ConcurrentStableDict({"username": username, "name": name, "status": status}))

    def remove_user(self, user_id: int) -> None:
        """移除测试用户（覆盖不存在分支）。

        Args:
            user_id: 用户主键。
        """
        self.users.get_and_remove(user_id)

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """按路径动作返回统一响应体（仅实现 profile）。

        Args:
            request: 服务间调用请求。

        Returns:
            ServiceResponse: 统一响应。

        Raises:
            ServiceUnavailableError: 标记不可用时（10007/503）。
        """
        action = request.path.rsplit("/", 1)[-1]
        self.calls.add(action)
        if action == "profile":
            if self.fail:
                raise ServiceUnavailableError("platform 用户接口不可用")
            body = request.json_body or ConcurrentStableDict()
            user_id = int(cast("int", body.get("user_id", 0)))
            user = self.users.get(user_id)
            if user is None:
                return _ok(ConcurrentStableDict({"found": False, "user": None}))
            return _ok(
                ConcurrentStableDict(
                    {
                        "found": True,
                        "user": ConcurrentStableDict(
                            {
                                "id": user_id,
                                "username": user["username"],
                                "name": user["name"],
                                "status": user["status"],
                                "locale": None,
                                "timezone": None,
                            }
                        ),
                    }
                )
            )
        return _ok(ConcurrentStableDict())


def _ok(data: ConcurrentStableDict[str, object]) -> ServiceResponse:
    """构造统一响应（HTTP 200 + code=0）。

    Args:
        data: 响应 data。

    Returns:
        ServiceResponse: 统一响应。
    """
    payload = {"code": 0, "message": "ok", "data": normalize_collections(data)}
    return ServiceResponse(status_code=200, content=json.dumps(payload).encode())
