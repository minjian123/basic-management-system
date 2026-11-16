"""平台服务内部端点：`/api/v1/platform/internal/preferences/resolve`（服务间调用，不经网关）。

- **鉴权**：`require_service("notification")`（平台自持服务白名单；只接受服务 JWT）。
- **租户**：由服务 JWT 的 `tenant` claim 经全局租户中间件解析租户库。
- **契约**：计入 platform 公开契约；通知服务据此过滤渠道与免打扰。
"""

from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import get_uow
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.preference.repository import PreferenceRepository
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.schemas.preferences import (
    InternalPreferenceResolveRequest,
    InternalPreferenceResolveResponse,
)

__all__ = ["router"]

router = BaseRouter(
    key="preference_internal",
    prefix="/platform/internal/preferences",
    tags=["preference-internal"],
    dependencies=[Depends(require_service("notification"))],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]


@router.post("/resolve")
async def resolve_preferences(
    req: InternalPreferenceResolveRequest, uow: UowDep
) -> ApiResponse[InternalPreferenceResolveResponse]:
    """按用户批量取偏好值 + 时区（缺失键由调用方回落默认）。

    Args:
        req: 批量取偏好请求。
        uow: 请求级工作单元。

    Returns:
        ApiResponse[InternalPreferenceResolveResponse]: 统一响应，data 为 `{values, timezone}`。

    Raises:
        ParamError: 用户主键非十进制字符串（10001）。
    """
    if not req.user_id.isdigit():
        raise ParamError(f"用户主键非法：{req.user_id}")
    session = cast("DbSession", uow.session)
    user_id = int(req.user_id)
    values = await PreferenceRepository(session).get_many(user_id, req.keys)
    user = await UserRepository(session).get(user_id)
    return ApiResponse.ok(
        InternalPreferenceResolveResponse(
            values=ConcurrentStableDict(values),
            timezone=user.timezone if user is not None else None,
        )
    )
