"""认证与身份服务端点：SSO 身份绑定查看（`GET /api/v1/users/{user_id}/identities`）。

- 鉴权：`require_auth` + `require_permission("sso:bind")`（权限基座当前为 Null = RBAC 前超管口径）。
- 数据源：平台库 `sys_user_identity`（按本地用户反查绑定）；只读。
- 越权判定（仅本人 / 超管）随 RBAC 阶段收口；本期按超管口径。
"""

from typing import Annotated

from fastapi import Depends, Path, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import session_scope
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_identity.repositories.user_identity import UserIdentityRepository
from bms_identity.schemas.sso import SsoIdentityItem, SsoIdentityList

router = BaseRouter(
    key="identity_users",
    prefix="/users",
    tags=["identity-users"],
    dependencies=[Depends(require_auth), Depends(require_permission("sso:bind"))],
)

UserIdPath = Annotated[int, Path(description="本地用户 ID")]


@router.get("/{user_id}/identities")
async def list_identities(request: Request, user_id: UserIdPath) -> ApiResponse[SsoIdentityList]:
    """按本地用户反查 SSO 身份绑定（平台库只读；无绑定返回空列表）。

    Args:
        request: 请求对象（取引擎注册表与会话工厂）。
        user_id: 本地用户 ID（路由参数）。

    Returns:
        ApiResponse: 统一响应，data 为绑定清单（`SsoIdentityList`）。
    """
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=PLATFORM_DB_KEY, read_only=True, factory=factory) as session:
        rows = await UserIdentityRepository(session).list_by_user(user_id)
    items = [SsoIdentityItem(idp_key=row.idp_key, external_id=row.external_id, tenant_id=row.tenant_id) for row in rows]
    return ApiResponse.ok(SsoIdentityList(items=items))
