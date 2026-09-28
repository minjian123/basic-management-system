"""跨服务测试共用夹具：测试用户令牌密钥对 + 环境注入 + 签发 access + 默认鉴权头。

`require_auth` 真实化（01_05）后，受保护路由要求有效登录态。本模块提供**共享夹具**，让各服务
`conftest` 的 `client` 默认携带一枚真实签名的用户令牌（`aud=api`、`type=access`，`jti` 与会话 id 同值），
使既有受保护路由用例在真实鉴权下零改动通过；会话标记校验交由测试环境的 `NullSessionStore`（恒定
返回占位）通过。

- 密钥对进程内惰性生成（`session` 级复用），测试密钥仅存环境变量、不落仓库。
- 令牌 `iss=bms`、`aud=api`，与 `[user_token].issuer` / `UnifiedTokenVerifier` 口径一致。
"""

from __future__ import annotations

import json
import time
from functools import lru_cache

from joserfc import jwt
from joserfc.jwk import RSAKey
from pytest import MonkeyPatch

TEST_KID = "usr-test"
"""测试用户令牌密钥 kid（须带 `usr-` 前缀）。"""

TEST_ISSUER = "bms"
"""测试用户令牌签发方（与 `[user_token].issuer` 一致）。"""

TEST_SUBJECT = "1001"
"""默认测试用户主体（数字 id）。"""

TEST_SESSION_ID = "1001"
"""默认测试会话 id（= access `jti`）。"""

TEST_TENANT = "demo"
"""默认测试租户编码（与演示租户一致）。"""

TOKEN_AUDIENCE_API = "api"
"""用户令牌受众。"""

_ACCESS_TTL = 1800


@lru_cache(maxsize=1)
def _key_pems() -> tuple[str, str]:
    """生成 / 复用测试 RSA 密钥对（公钥 PEM, 私钥 PEM）。

    Returns:
        tuple[str, str]: (公钥 PEM, 私钥 PEM)。
    """
    key = RSAKey.generate_key(2048, private=True)
    return key.as_pem(private=False).decode(), key.as_pem(private=True).decode()


def configure_token_env(monkeypatch: MonkeyPatch) -> None:
    """把测试密钥写入 `[security].keys` 环境变量（供应用装配真实校验器）。

    Args:
        monkeypatch: pytest `monkeypatch` 夹具。
    """
    public_key, private_key = _key_pems()
    keys = {TEST_KID: {"algorithm": "RS256", "public_key": public_key, "private_key": private_key}}
    monkeypatch.setenv("BMS_SECURITY__KEYS", json.dumps(keys))
    monkeypatch.setenv("BMS_SECURITY__ACTIVE_KID", TEST_KID)


def issue_access_token(
    subject: str = TEST_SUBJECT,
    session_id: str = TEST_SESSION_ID,
    tenant: str | None = TEST_TENANT,
    scopes: tuple[str, ...] = (),
) -> str:
    """签发一枚测试用户 access 令牌（同步，可直接在夹具内调用）。

    Args:
        subject: 用户主体。
        session_id: 会话 id（`jti`）。
        tenant: 租户编码（None 不写租户声明）。
        scopes: 授权范围（非空时写 `scope`）。

    Returns:
        str: access 令牌紧凑串。
    """
    _, private_key = _key_pems()
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": TEST_ISSUER,
        "sub": subject,
        "aud": TOKEN_AUDIENCE_API,
        "jti": session_id,
        "type": "access",
        "exp": now + _ACCESS_TTL,
        "iat": now,
    }
    if tenant:
        claims["tenant_id"] = tenant
    if scopes:
        claims["scope"] = " ".join(scopes)
    return jwt.encode({"alg": "RS256", "kid": TEST_KID}, claims, RSAKey.import_key(private_key))


def auth_headers(
    subject: str = TEST_SUBJECT,
    session_id: str = TEST_SESSION_ID,
    tenant: str | None = TEST_TENANT,
    scopes: tuple[str, ...] = (),
) -> dict[str, str]:
    """默认鉴权头（`Authorization: Bearer <测试 access>`）。

    Args:
        subject: 用户主体。
        session_id: 会话 id。
        tenant: 租户编码。
        scopes: 授权范围。

    Returns:
        dict[str, str]: 请求头映射。
    """
    return {"Authorization": f"Bearer {issue_access_token(subject, session_id, tenant, scopes)}"}
