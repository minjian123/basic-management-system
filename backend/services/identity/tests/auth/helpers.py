"""认证链路测试替身：用户令牌签发者与 org 凭据客户端（Kiwi 2194）。"""

from __future__ import annotations

import json
from typing import cast

from fastapi import FastAPI

from bms_core.api.deps import (
    get_captcha,
    get_rate_limiter,
    get_service_client,
    get_session_store,
    get_user_token_issuer,
)
from bms_core.captcha.base import BaseCaptcha, CaptchaChallenge, CaptchaCredential, CaptchaKind, CaptchaScenePolicy
from bms_core.core.exceptions import AuthError
from bms_core.db.tenant import DEMO_TENANT, TenantContext, TenantNotFoundError
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.user_token import BaseUserTokenIssuer, UserTokenPair, UserTokenSpec
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.session.memory import MemorySessionStore

_ACCESS = "access"
_REFRESH = "refresh"


class FakeUserTokenIssuer(BaseUserTokenIssuer):
    """测试替身：内存票据映射（签发 / 类型强校验验签）。"""

    plugin_name = "fake"

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

    def mint(
        self,
        token: str,
        *,
        sub: str = "1",
        jti: object = None,
        tenant_id: object = "demo",
        token_type: str = _REFRESH,
    ) -> None:
        """手工登记任意外形票据（覆盖异常分支用例）。

        Args:
            token: 令牌串。
            sub: 主体。
            jti: 会话 id（可为 None 覆盖缺失分支）。
            tenant_id: 租户编码（可为 None / 任意串）。
            token_type: 令牌类型。
        """
        self._by_token[token] = {"sub": sub, "jti": jti, "tenant_id": tenant_id, "type": token_type}


class FakeOrgClient(BaseServiceClient):
    """测试替身：内存 org 凭据服务（verify / update-password / login-state）。"""

    plugin_name = "fake"

    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {}
        self.last_state: dict[str, object] = {}
        self.fail_count = 0
        self.calls: list[str] = []

    def set_user(
        self,
        account: str,
        *,
        password: str,
        user_id: int = 1,
        name: str = "用户",
        status: str = "enabled",
        locked: bool = False,
        locale: str | None = None,
        timezone: str | None = None,
    ) -> None:
        """登记测试用户。

        Args:
            account: 账号。
            password: 口令明文。
            user_id: 用户 ID。
            name: 昵称。
            status: 状态。
            locked: 是否锁定。
            locale: 语言偏好。
            timezone: 时区偏好。
        """
        self.users[account] = {
            "password": password,
            "id": user_id,
            "name": name,
            "status": status,
            "locked": locked,
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
        data = self._dispatch(action, body)
        return ServiceResponse(status_code=200, content=json.dumps({"code": 0, "message": "ok", "data": data}).encode())

    def _dispatch(self, action: str, body: dict[str, object]) -> dict[str, object]:
        """分派动作。

        Args:
            action: 动作名。
            body: 请求体。

        Returns:
            dict[str, object]: 响应 data。
        """
        account = str(body.get("account", ""))
        user = self.users.get(account)
        if action == "verify":
            if user is None:
                return {"found": False, "valid": False, "locked": False, "status": ""}
            return {
                "found": True,
                "valid": user["password"] == body.get("password"),
                "locked": bool(user["locked"]),
                "status": user["status"],
                "rehashed": False,
                "user": {
                    "id": user["id"],
                    "username": account,
                    "name": user["name"],
                    "locale": user["locale"],
                    "timezone": user["timezone"],
                    "pwd_changed_at": None,
                },
            }
        if action == "update-password":
            if user is None:
                return {"updated": False}
            user["password"] = body.get("new_password")
            return {"updated": True}
        if action == "login-state":
            if user is None:
                return {"failed_count": 0, "locked_until": None, "last_login_at": None}
            if body.get("success"):
                self.last_state = {"failed_count": 0, "locked_until": None, "last_login_at": "now"}
            else:
                self.fail_count = int(cast("int", body.get("failed_count", 0)))
                self.last_state = {
                    "failed_count": self.fail_count,
                    "locked_until": "locked" if body.get("lock_seconds") else None,
                    "last_login_at": None,
                }
            return self.last_state
        return {}


class FakeCaptcha(BaseCaptcha):
    """测试替身：可配置是否强制 + 是否通过。"""

    plugin_name = "fake"

    def __init__(self, *, required: bool = False, verified: bool = True) -> None:
        self._required = required
        self._verified = verified
        self.seen: list[CaptchaCredential] = []

    async def generate(self, scene: str = "login", *, kind: CaptchaKind = CaptchaKind.IMAGE) -> CaptchaChallenge:
        """出题（占位）。

        Args:
            scene: 场景。
            kind: 形态。

        Returns:
            CaptchaChallenge: 挑战。
        """
        return CaptchaChallenge(captcha_id="cid", image=b"", scene=scene, kind=kind)

    async def send_sms(self, phone: str, scene: str = "login") -> CaptchaChallenge:
        """短信出题（占位）。

        Args:
            phone: 手机号。
            scene: 场景。

        Returns:
            CaptchaChallenge: 挑战。
        """
        return CaptchaChallenge(captcha_id="cid", image=b"", scene=scene, kind=CaptchaKind.SMS)

    async def verify_credential(self, credential: CaptchaCredential) -> bool:
        """凭证判定（可配置）。

        Args:
            credential: 凭证。

        Returns:
            bool: 是否通过。
        """
        self.seen.append(credential)
        return self._verified

    async def policy(self, scene: str = "login") -> CaptchaScenePolicy:
        """场景策略（可配置强制）。

        Args:
            scene: 场景。

        Returns:
            CaptchaScenePolicy: 策略。
        """
        return CaptchaScenePolicy(scene=scene, required=self._required)


class FakeTenantSource:
    """测试替身：固定演示租户的租户源（仅演示租户可用）。"""

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户（仅 demo）。

        Args:
            code: 租户编码。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 非演示租户（404）。
        """
        if code == DEMO_TENANT.tenant_code:
            return DEMO_TENANT
        raise TenantNotFoundError(f"未知租户：{code}")

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户（仅回退演示租户）。

        Args:
            domain: 子域名。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 非演示租户（404）。
        """
        if domain == DEMO_TENANT.domain:
            return DEMO_TENANT
        raise TenantNotFoundError(f"未知域名：{domain}")


def wire_auth(
    app: FastAPI,
    *,
    issuer: BaseUserTokenIssuer,
    org: BaseServiceClient,
    store: MemorySessionStore,
    limiter: MemoryRateLimiter,
    captcha: BaseCaptcha | None = None,
) -> None:
    """把认证链路依赖覆盖为测试替身。

    Args:
        app: 应用实例。
        issuer: 用户令牌签发者替身。
        org: org 客户端替身。
        store: 会话存储替身。
        limiter: 限流器替身。
        captcha: 验证码替身（None 用默认 Null）。
    """
    app.dependency_overrides[get_user_token_issuer] = lambda: issuer
    app.dependency_overrides[get_service_client] = lambda: org
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    if captcha is not None:
        app.dependency_overrides[get_captcha] = lambda: captcha
    else:
        app.dependency_overrides.pop(get_captcha, None)
