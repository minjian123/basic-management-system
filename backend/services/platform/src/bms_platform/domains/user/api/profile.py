"""个人中心偏好端点：`GET/PUT /api/v1/profile/preferences`（语言 / 时区偏好）。

- **权限**：登录即可、仅本人（偏好只影响本人展示，不涉业务数据）；
- **部分更新**：请求中未出现的字段不修改，显式 `null` 清空回退缺省；
- **响应**：存值 + 生效值（`effective_locale` / `effective_timezone`），前端不必重算缺省规则。
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_locale_registry, get_uow
from bms_core.core.config import Settings
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.schemas.common import ApiResponse

from ..repositories.user import UserRepository
from ..schemas.profile import ProfilePreferenceRequest, ProfilePreferenceResponse
from ..services.profile import ProfilePreference, ProfilePreferenceService

__all__ = ["router"]

router = BaseRouter(
    key="user_profile",
    prefix="/profile",
    tags=["profile"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
RegistryDep = Annotated[BaseLocaleRegistry, Depends(get_locale_registry)]


def _current_user_id() -> int:
    """取当前登录用户主键。

    Returns:
        int: 用户主键。

    Raises:
        ParamError: 无登录上下文（鉴权路由下不可达）。
    """
    user_id = current_user_id.get()
    if user_id is None:  # pragma: no cover - 鉴权路由下不可达（防御性分支）
        raise ParamError("未登录")
    return user_id


def _service(request: Request, uow: UowDep, registry: RegistryDep) -> ProfilePreferenceService:
    """构造偏好服务（请求级会话与配置）。

    Args:
        request: 请求对象（取应用级配置）。
        uow: 请求级工作单元。
        registry: 语言清单能力域。

    Returns:
        ProfilePreferenceService: 偏好服务实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return ProfilePreferenceService(
        UserRepository(cast("DbSession", uow.session)),
        uow,
        registry=registry,
        i18n=settings.i18n_options,
    )


def _to_response(preference: ProfilePreference) -> ProfilePreferenceResponse:
    """偏好快照 → 响应契约。

    Args:
        preference: 偏好快照。

    Returns:
        ProfilePreferenceResponse: 响应体。
    """
    return ProfilePreferenceResponse(
        locale=preference.locale,
        timezone=preference.timezone,
        effective_locale=preference.effective_locale,
        effective_timezone=preference.effective_timezone,
    )


@router.get("/preferences")
async def get_profile_preferences(
    request: Request,
    uow: UowDep,
    registry: RegistryDep,
) -> ApiResponse[ProfilePreferenceResponse]:
    """读取本人语言 / 时区偏好（存值 + 生效值）。

    Args:
        request: 请求对象。
        uow: 请求级工作单元。
        registry: 语言清单能力域。

    Returns:
        ApiResponse[ProfilePreferenceResponse]: 统一响应。
    """
    preference = await _service(request, uow, registry).load(_current_user_id())
    return ApiResponse.ok(_to_response(preference))


@router.put("/preferences")
async def update_profile_preferences(
    request: Request,
    req: ProfilePreferenceRequest,
    uow: UowDep,
    registry: RegistryDep,
) -> ApiResponse[ProfilePreferenceResponse]:
    """设置本人语言 / 时区偏好（部分更新；非法值即拒）。

    Args:
        request: 请求对象。
        req: 偏好设置请求。
        uow: 请求级工作单元。
        registry: 语言清单能力域。

    Returns:
        ApiResponse[ProfilePreferenceResponse]: 更新后的偏好（存值 + 生效值）。
    """
    provided = req.model_fields_set
    preference = await _service(request, uow, registry).save(
        _current_user_id(),
        locale=req.locale,
        timezone=req.timezone,
        locale_provided="locale" in provided,
        timezone_provided="timezone" in provided,
    )
    return ApiResponse.ok(_to_response(preference))
