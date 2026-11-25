"""服务令牌签发助手：用装配夹具注入的测试密钥签服务 JWT（跨服务用例共用）。

为什么需要：装配态应用走**真实鉴权**，服务间端点的白名单校验（`sub` ∈ identity / platform）
必须用**合法签名的服务令牌**才能验证；用替身替换 `get_token_verifier` 属「改装配状态」，
已按 13_10 口径禁止。

密钥来源：装配夹具在装配前把测试密钥写到 `BMS_TEST_SERVICE_TOKEN__KEYS` /
`BMS_TEST_SERVICE_TOKEN__ACTIVE_KID`（`ops.contract_smoke.smoke_service_token_keys` 生成）。
用 `BMS_TEST_` 前缀是为了避开**每例的配置隔离夹具**——它清空 `BMS_*`，不清 `BMS_TEST_*`。
"""

from __future__ import annotations

import json
import os
import time
import uuid

from joserfc import jwt
from joserfc.jwk import RSAKey

from bms_core.oauth.token import (
    DEFAULT_SERVICE_TOKEN_ISSUER,
    SERVICE_DOMAIN_CLAIM,
    SERVICE_DOMAIN_SEPARATOR,
    SERVICE_TOKEN_TYPE,
    TOKEN_AUDIENCE_SERVICE,
)

_KEYS_ENV = "BMS_TEST_SERVICE_TOKEN__KEYS"
"""测试密钥环境变量（`BMS_TEST_` 前缀：配置隔离夹具只清 `BMS_*`，不清它）。"""

_KID_ENV = "BMS_TEST_SERVICE_TOKEN__ACTIVE_KID"
"""当前签名 kid 的环境变量。"""

_TTL = 300
"""签发有效期（秒）：仅覆盖单条用例的执行窗口。"""


def issue_service_token(service: str, *, domains: tuple[str, ...] = ()) -> str:
    """签一枚服务 JWT（`typ=service`、`aud=service`，`sub` / `service` 同为服务标识）。

    能力判定有两道：**域归属**（令牌 `domains` claim 须含被调能力所属域）与**能力分配**。
    要访问 `platform.user.query` 这类按能力分配的端点，`domains` 必须带上 `user`。

    Args:
        service: 服务标识（`identity` / `platform` / `gateway` 等）。
        domains: 令牌声明的承载业务域（空格分隔写入 `domains` claim）。

    Returns:
        str: 紧凑 JWT。

    Raises:
        RuntimeError: 装配夹具没跑（测试密钥未注入）。
    """
    raw = os.environ.get(_KEYS_ENV, "")
    kid = os.environ.get(_KID_ENV, "")
    if not raw or not kid:
        raise RuntimeError("服务令牌测试密钥未注入：需要装配态夹具（已装配系统在装配前注入）")
    private = str(json.loads(raw)[kid].get("private_key") or "")
    if not private:
        raise RuntimeError(f"服务令牌密钥 {kid} 缺私钥，无法签发")
    key = RSAKey.import_key(private)
    now = int(time.time())
    claims = {
        "iss": DEFAULT_SERVICE_TOKEN_ISSUER,
        "sub": service,
        "aud": TOKEN_AUDIENCE_SERVICE,
        "exp": now + _TTL,
        "iat": now,
        "jti": uuid.uuid4().hex,
        "scope": "",
        "typ": SERVICE_TOKEN_TYPE,
        "service": service,
    }
    if domains:
        claims[SERVICE_DOMAIN_CLAIM] = SERVICE_DOMAIN_SEPARATOR.join(domains)
    return jwt.encode({"alg": "RS256", "kid": kid}, claims, key)
