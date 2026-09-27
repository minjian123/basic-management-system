"""SSO 测试替身与 OIDC IdP Mock（Kiwi 2197）。

自包含实现（不复用 `tests.auth.helpers` 的跨包导入）：内存用户令牌签发者、
org 内部接口客户端（含 profile）与可控 OIDC IdP（Discovery / JWKS / token / userinfo）。
"""

from __future__ import annotations

import json
import time
from typing import cast

import httpx
from joserfc import jwt
from joserfc.jwk import RSAKey

from bms_core.core.exceptions import AuthError, ServiceUnavailableError
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.user_token import BaseUserTokenIssuer, UserTokenPair, UserTokenSpec
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

ISSUER = "http://idp.test/realms/bms"
CLIENT_ID = "bms-backend"
CLIENT_SECRET = "client-secret"
TENANT = "demo"
IDP_KEY = "keycloak"
TENANT_HEADERS = {"X-Tenant-ID": TENANT}

_ACCESS = "access"
_REFRESH = "refresh"


class FakeUserTokenIssuer(BaseUserTokenIssuer):
    """测试替身：内存票据映射（签发 / 类型强校验验签）。"""

    plugin_name = "sso_fake"

    def __init__(self) -> None:
        self._by_token: dict[str, dict[str, object]] = {}
        self._n = 0
        self.specs: list[UserTokenSpec] = []

    async def issue_pair(self, spec: UserTokenSpec) -> UserTokenPair:
        """签发双 token（同会话 id；记录类型与租户）。

        Args:
            spec: 签发请求。

        Returns:
            UserTokenPair: 双 token。
        """
        self._n += 1
        access, refresh = f"acc-{self._n}", f"ref-{self._n}"
        base = {"sub": spec.subject, "jti": spec.session_id, "tenant_id": spec.tenant_id}
        self._by_token[access] = {**base, "type": _ACCESS}
        self._by_token[refresh] = {**base, "type": _REFRESH}
        self.specs.append(spec)
        return UserTokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=1800,
            refresh_expires_in=1209600,
            session_id=spec.session_id,
        )

    def verify(self, token: str, *, expected_type: str) -> IdentityClaims:
        """验签（内存查表 + 类型强校验）。

        Args:
            token: 令牌串。
            expected_type: 期望类型。

        Returns:
            IdentityClaims: 身份声明。

        Raises:
            AuthError: 未知令牌 / 类型不符（20001/401）。
        """
        info = self._by_token.get(token)
        if info is None or info["type"] != expected_type:
            raise AuthError("invalid token")
        return IdentityClaims(subject=cast("str", info["sub"]), payload=info)

    def jwks(self) -> dict[str, object]:
        """占位 JWKS。

        Returns:
            dict[str, object]: 空公钥集。
        """
        return {"keys": []}


class FakeSsoOrgClient(BaseServiceClient):
    """测试替身：内存 org 内部接口（profile / login-state / credential 兜底）。"""

    plugin_name = "sso_fake"

    def __init__(self) -> None:
        self.users: dict[int, dict[str, object]] = {}
        self.fail_profile = False
        self.calls: list[str] = []
        self.login_states: list[dict[str, object]] = []

    def set_user(
        self,
        user_id: int,
        *,
        username: str = "admin",
        name: str = "管理员",
        status: str = "enabled",
        locale: str | None = "zh-cn",
        timezone: str | None = "Asia/Shanghai",
    ) -> None:
        """登记测试用户（按主键索引）。

        Args:
            user_id: 用户主键。
            username: 账号。
            name: 昵称。
            status: 账号状态。
            locale: 语言偏好。
            timezone: 时区偏好。
        """
        self.users[user_id] = {
            "username": username,
            "name": name,
            "status": status,
            "locale": locale,
            "timezone": timezone,
        }

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """按路径动作返回统一响应体。

        Args:
            request: 服务间调用请求。

        Returns:
            ServiceResponse: 统一响应。
        """
        action = request.path.rsplit("/", 1)[-1]
        body = request.json_body or {}
        self.calls.append(action)
        if action == "profile":
            if self.fail_profile:
                raise ServiceUnavailableError("org 用户接口不可用")
            return _ok(self._profile(body))
        if action == "login-state":
            self.login_states.append(body)
            return _ok({"failed_count": 0, "locked_until": None, "last_login_at": "now"})
        return _ok({})

    def _profile(self, body: dict[str, object]) -> dict[str, object]:
        """按 user_id 返回概要（未登记 → found=False）。

        Args:
            body: 请求体。

        Returns:
            dict[str, object]: 概要 data。
        """
        user_id = int(cast("int", body.get("user_id", 0)))
        user = self.users.get(user_id)
        if user is None:
            return {"found": False, "user": None}
        return {
            "found": True,
            "user": {
                "id": user_id,
                "username": user["username"],
                "name": user["name"],
                "status": user["status"],
                "locale": user["locale"],
                "timezone": user["timezone"],
            },
        }


def _ok(data: dict[str, object]) -> ServiceResponse:
    """构造统一响应（HTTP 200 + code=0）。

    Args:
        data: 响应 data。

    Returns:
        ServiceResponse: 统一响应。
    """
    return ServiceResponse(status_code=200, content=json.dumps({"code": 0, "message": "ok", "data": data}).encode())


class IdpMock:
    """可控 OIDC IdP：Discovery / JWKS / token / userinfo 四端点。"""

    def __init__(self) -> None:
        self.key, self.public = _key_pair()
        self.subject = "sub-1"
        self.id_token: str | None = None
        self.discovery_status = 200
        self.jwks_status = 200
        self.token_status = 200
        self.token_forms: list[str] = []
        self.userinfo_sub = "sub-1"
        self.discovery_drop: set[str] | None = None
        self.token_bad_json = False
        self.userinfo_status = 200

    def make_id_token(self, *, nonce: str | None = None, subject: str | None = None, exp_delta: int = 300) -> str:
        """签发测试 ID Token（RS256 / kid=k1）。

        Args:
            nonce: nonce 声明（可选）。
            subject: 主体（缺省用当前 subject）。
            exp_delta: 过期偏移（秒）。

        Returns:
            str: 紧凑 JWT。
        """
        self.id_token = _token(
            self.key,
            subject=subject or self.subject,
            nonce=nonce,
            exp_delta=exp_delta,
        )
        return self.id_token

    def handle(self, request: httpx.Request) -> httpx.Response:
        """MockTransport 处理函数（按路径后缀分派）。

        Args:
            request: 出站请求。

        Returns:
            httpx.Response: 模拟响应。
        """
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            if self.discovery_status != 200:
                return httpx.Response(self.discovery_status, json={})
            return httpx.Response(200, json=_metadata(drop=self.discovery_drop))
        if path.endswith("/certs"):
            if self.jwks_status != 200:
                return httpx.Response(self.jwks_status, json={})
            return httpx.Response(200, json={"keys": [self.public]})
        if path.endswith("/token"):
            self.token_forms.append(request.content.decode())
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            if self.token_bad_json:
                return httpx.Response(200, json=[])
            payload: dict[str, object] = {
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 300,
            }
            if self.id_token is not None:
                payload["id_token"] = self.id_token
            return httpx.Response(200, json=payload)
        if path.endswith("/userinfo"):
            if self.userinfo_status != 200:
                return httpx.Response(self.userinfo_status, json={})
            return httpx.Response(200, json={"sub": self.userinfo_sub, "preferred_username": "sso-user"})
        return httpx.Response(404, json={"error": "not_found"})


def _metadata(issuer: str = ISSUER, *, drop: set[str] | None = None) -> dict[str, str]:
    """构造 OIDC Discovery 文档（`drop` 可剔除字段以覆盖配置缺失分支）。

    Args:
        issuer: 签发方。
        drop: 需剔除的字段名集合（可选）。

    Returns:
        dict[str, str]: Discovery 文档。
    """
    document = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "userinfo_endpoint": f"{issuer}/protocol/openid-connect/userinfo",
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
    }
    if drop:
        for field in drop:
            document.pop(field, None)
    return document


def _key_pair() -> tuple[RSAKey, dict[str, object]]:
    """生成 RSA 密钥与对应公钥 JWK（kid=k1）。

    Returns:
        tuple[RSAKey, dict[str, object]]: 私钥与公钥 JWK。
    """
    key = RSAKey.generate_key(2048, private=True)
    public = cast("dict[str, object]", key.as_dict(private=False))
    public["kid"] = "k1"
    return key, public


def _token(
    key: RSAKey,
    *,
    kid: str = "k1",
    alg: str = "RS256",
    iss: str = ISSUER,
    aud: object = CLIENT_ID,
    exp_delta: int = 300,
    subject: str = "sub-1",
    nonce: str | None = None,
) -> str:
    """签发测试 JWT。

    Args:
        key: 签名私钥。
        kid: 密钥标识（写入 header）。
        alg: 签名算法。
        iss: 签发方。
        aud: 受众。
        exp_delta: 过期时间偏移（秒；负数为已过期）。
        subject: 主体标识。
        nonce: ID Token nonce 声明（可选）。

    Returns:
        str: JWT 紧凑串。
    """
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": iss,
        "sub": subject,
        "aud": aud,
        "exp": now + exp_delta,
        "iat": now,
        "preferred_username": "alice",
        "email": "alice@example.com",
    }
    if nonce is not None:
        claims["nonce"] = nonce
    return jwt.encode({"alg": alg, "kid": kid}, claims, key)
