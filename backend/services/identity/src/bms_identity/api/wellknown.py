"""JWKS 公开端点：`GET /.well-known/jwks.json`（服务令牌与用户令牌自签公钥分发）。

- 免鉴权、**无统一响应包体**（标准 JWKS 文档，供网关与内部服务取公钥验签）；豁免租户解析与边缘旁路拒绝。
- 同端点发布两类公钥：服务令牌（`svc-*`）与用户令牌（`usr-*`，BMS 自签）；只含公钥、按 kid 排序。
- `kid` 冲突 / 文档结构非法 → 503（fail-closed，不发有歧义的键集）；两域均无密钥时返回 `{"keys": []}`。
"""

from fastapi import HTTPException, Request

from bms_core.api.base import BaseRouter
from bms_core.core.exceptions import ConfigError
from bms_core.oauth.keys import merge_jwks

router = BaseRouter(key="wellknown", prefix="/.well-known", tags=["wellknown"], default_responses=False)


@router.get("/jwks.json")
async def get_jwks(request: Request) -> dict[str, object]:
    """取公开 JWKS 文档（服务令牌 + 用户令牌公钥合并）。

    Args:
        request: 请求对象（取应用装配的服务 / 用户令牌签发者）。

    Returns:
        dict[str, object]: 标准 JWKS 文档（只含公钥）。

    Raises:
        HTTPException: 两域 kid 冲突 / 文档非法（503，fail-closed）。
    """
    documents = [
        dict(issuer.jwks())
        for issuer in (
            getattr(request.app.state, "service_token", None),
            getattr(request.app.state, "user_token", None),
        )
        if issuer is not None
    ]
    try:
        return merge_jwks(*documents)
    except ConfigError as exc:
        raise HTTPException(status_code=503) from exc
