"""用户偏好占位路由：`/api/v1/preferences/{key}`（登录即可读写；真实持久化随通用能力阶段）。

- 读取 / 写入 / 重置单个偏好；键格式经 `is_valid_pref_key` 校验，非法抛 `ParamError`（10001）。
- 统一经 `BasePreferenceStore` 读写（占位实现固定回退默认值）；跨端同步与本地回退由消费方决定。
- 全量 `GET /preferences` 与批量 `PUT /preferences/batch`、白名单与大小校验随通用能力阶段。
"""

from typing import Annotated

from fastapi import Depends, Path

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_preference_store
from bms_core.core.exceptions import ParamError
from bms_core.preference.base import BasePreferenceStore, is_valid_pref_key
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.preference import PreferenceResponse, PreferenceValueRequest

router = BaseRouter(
    key="preference",
    prefix="/preferences",
    tags=["preference"],
    dependencies=[Depends(require_auth)],
)

StoreDep = Annotated[BasePreferenceStore, Depends(get_preference_store)]
KeyPath = Annotated[str, Path(description="偏好键（域.键，如 list.user_form / ui.theme）")]


def _ensure_key(key: str) -> str:
    """校验偏好键格式。

    Args:
        key: 偏好键。

    Returns:
        str: 原键。

    Raises:
        ParamError: 键不符合 `{域}.{键}` 规范（10001）。
    """
    if not is_valid_pref_key(key):
        raise ParamError(f"偏好键格式非法：{key}（应为 {{域}}.{{键}}）")
    return key


@router.get("/{key}")
async def get_preference(store: StoreDep, key: KeyPath) -> ApiResponse:
    """读取单个偏好（未设置回退默认值）。

    Args:
        store: 用户偏好存储。
        key: 偏好键。

    Returns:
        ApiResponse: 统一响应，data 为 `{key, value}`。
    """
    value = await store.get(_ensure_key(key))
    return ApiResponse.ok(PreferenceResponse(key=key, value=value))


@router.put("/{key}")
async def set_preference(store: StoreDep, key: KeyPath, req: PreferenceValueRequest) -> ApiResponse:
    """写入 / 覆盖单个偏好（upsert）。

    Args:
        store: 用户偏好存储。
        key: 偏好键。
        req: 偏好值请求。

    Returns:
        ApiResponse: 统一响应，data 为 `{key, value}`。
    """
    await store.set(_ensure_key(key), req.value)
    return ApiResponse.ok(PreferenceResponse(key=key, value=req.value))


@router.delete("/{key}")
async def reset_preference(store: StoreDep, key: KeyPath) -> ApiResponse:
    """重置单个偏好（清除该键，恢复默认）。

    Args:
        store: 用户偏好存储。
        key: 偏好键。

    Returns:
        ApiResponse: 统一响应，data 为 null。
    """
    await store.reset(_ensure_key(key))
    return ApiResponse.ok()
