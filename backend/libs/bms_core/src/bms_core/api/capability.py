"""入站能力授权依赖（07B `02_04`）：`require_capability("<能力名>")`。

提供方在**自己的端点**上显式声明该端点对应哪项能力（能力名来自本产品自持声明），依赖按
「本能力的有效分配」判定调用方是否被授权，越界即拒（`PermissionError` 30001 / 403）。

口径：

- 授权主体统一用**服务键**（服务 JWT `sub`）；前端应用不持有服务令牌、不参与分配；
- 判定一律以**提供方侧授权视图**为准（不把入站令牌的 scope 当授权凭证，scope 是出站背书）；
- 打点按「调用方 × 能力」：`bms_capability_call_total{capability, consumer, result}` 与
  `bms_capability_denied_total{capability, consumer}`（见 `collaboration/grant.py`）；
- **迁移期不接线**：本任务只交付依赖，`platform.*` 三处端点仍走 `require_service` 白名单，
  端点切换归 `03_01`（避免同一端点并存两套判定口径）。

落点说明：本模块单列而不并入 `api/base.py`——`api/base.py` 被 `servicecall.base` 依赖，
若它反向导入 `collaboration`（其 `request` 模块又依赖 `servicecall`）会形成导入环。
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header

from bms_core.api.base import DEFAULT_GATEWAY_SERVICE_IDENTITY
from bms_core.collaboration.grant import check_capability_access
from bms_core.core.exceptions import AuthError, PermissionError
from bms_core.metrics.base import BaseMetrics, get_metrics
from bms_core.oauth.token import TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken, get_token_verifier

__all__ = ["require_capability", "require_capability_or_service"]


def require_capability(capability: str) -> Callable[..., Awaitable[VerifiedToken]]:
    """能力授权依赖工厂：校验调用方对 `capability` 是否有有效分配。

    Args:
        capability: 端点对应的能力名（须与产品清单 `[[collaborations]]` 一致）。

    Returns:
        Callable[..., Awaitable[VerifiedToken]]: FastAPI 依赖（返回校验通过的服务身份声明）。
    """

    async def dependency(
        verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
        metrics: Annotated[BaseMetrics, Depends(get_metrics)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> VerifiedToken:
        """校验入站服务 JWT 与能力授权（缺失 / 无效 / 未授权一律拒）。

        Args:
            verifier: 统一令牌校验器。
            metrics: 指标器（按「调用方 × 能力」打点）。
            authorization: `Authorization` 头。

        Returns:
            VerifiedToken: 校验通过的服务身份声明。

        Raises:
            AuthError: 缺少 / 无效服务身份凭证（20001 / 401）。
            PermissionError: 无有效分配或授权已过期（30001 / 403，消息含能力名与消费方）。
            CatalogError: 能力未登记 / 授权视图来源未装配（配置漂移，拒启级）。
        """
        token = _bearer_token(authorization)
        if token is None:
            raise AuthError("缺少服务身份凭证")
        verified = await verifier.verify(token, audience=TOKEN_AUDIENCE_SERVICE)
        consumer = (verified.service or "").strip()
        if not consumer:
            raise AuthError("服务身份缺少签发方标识")
        if consumer == DEFAULT_GATEWAY_SERVICE_IDENTITY:
            # 网关代发的服务票据只代表「请求来自网关」，不是产品服务；前端应用不参与分配
            raise PermissionError(f"网关代发的服务票据不得作为能力消费方：{capability}")
        await check_capability_access(capability, consumer, metrics=metrics)
        return verified

    return dependency


def require_capability_or_service(
    capability: str,
    *services: str,
) -> Callable[..., Awaitable[VerifiedToken]]:
    """能力授权为主、指定**平台内部服务**按白名单放行的复合依赖。

    用于「产品按能力授权、平台内部按白名单」并存的入站面（如系统参数内部读）：平台内部调用不参与
    能力分配，纳入授权会扩大范围且无收益；产品调用则一律按分配判定。

    判定顺序：网关代发票据一律拒 → 调用方在 `services` 内即放行 → 否则按能力分配判定。

    Args:
        capability: 端点对应的能力名（须与提供方清单 `[[collaborations]]` 一致）。
        *services: 按白名单放行的平台内部服务标识。

    Returns:
        Callable[..., Awaitable[VerifiedToken]]: FastAPI 依赖（返回校验通过的服务身份声明）。
    """

    async def dependency(
        verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
        metrics: Annotated[BaseMetrics, Depends(get_metrics)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> VerifiedToken:
        """校验入站服务 JWT，并按「白名单 → 能力分配」两档判定。

        Args:
            verifier: 统一令牌校验器。
            metrics: 指标器（能力判定按「调用方 × 能力」打点）。
            authorization: `Authorization` 头。

        Returns:
            VerifiedToken: 校验通过的服务身份声明。

        Raises:
            AuthError: 缺少 / 无效服务身份凭证（20001 / 401）。
            PermissionError: 既不在白名单、也无有效分配（30001 / 403）。
            CatalogError: 能力未登记 / 授权视图来源未装配（配置漂移，拒启级）。
        """
        token = _bearer_token(authorization)
        if token is None:
            raise AuthError("缺少服务身份凭证")
        verified = await verifier.verify(token, audience=TOKEN_AUDIENCE_SERVICE)
        consumer = (verified.service or "").strip()
        if not consumer:
            raise AuthError("服务身份缺少签发方标识")
        if consumer == DEFAULT_GATEWAY_SERVICE_IDENTITY:
            raise PermissionError(f"网关代发的服务票据不得作为能力消费方：{capability}")
        if consumer in services:
            return verified
        await check_capability_access(capability, consumer, metrics=metrics)
        return verified

    return dependency


def _bearer_token(authorization: str | None) -> str | None:
    """取 Bearer 令牌（大小写不敏感）。

    Args:
        authorization: `Authorization` 头原始值。

    Returns:
        str | None: 令牌紧凑串；缺失 / 非 Bearer 为 None。
    """
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
