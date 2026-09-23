"""JWKS 公开端点：`GET /.well-known/jwks.json`（服务 JWT 自签公钥分发）。

- 免鉴权、**无统一响应包体**（标准 JWKS 文档，供网关与内部服务取公钥验签）；豁免租户解析与边缘旁路拒绝。
- 取应用装配的 `service_token` 签发者公钥（`app.state.service_token`）；未接真实实现 / 无密钥时返回 `{"keys": []}`。
"""

from fastapi import Request

from bms_core.api.base import BaseRouter

router = BaseRouter(key="wellknown", prefix="/.well-known", tags=["wellknown"], default_responses=False)


@router.get("/jwks.json")
async def get_jwks(request: Request) -> dict[str, object]:
    """取服务 JWT 公开 JWKS 文档。

    Args:
        request: 请求对象（取应用装配的服务 JWT 签发者）。

    Returns:
        dict[str, object]: 标准 JWKS 文档（只含公钥）。
    """
    issuer = getattr(request.app.state, "service_token", None)
    if issuer is None:
        return {"keys": []}
    return dict(issuer.jwks())
