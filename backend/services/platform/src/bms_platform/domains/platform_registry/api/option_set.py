"""选项集只读路由：`GET /api/v1/option-sets`（登录即可；数据权限后续挂同一入口）。

- 返回装载时注册的静态值域快照（`optionSetKey` + `items`），供列表页 / 表单统一消费；
- 选项集运行期只读、不落库、无写接口；
- 数据权限（后续）在**本入口**统一判定，不另开后门。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.optionset.base import BaseOptionSetRegistry, get_option_set_registry
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.option_set import (
    OptionSetItemResponse,
    OptionSetListResponse,
    OptionSetResponse,
)

router = BaseRouter(
    key="option_set",
    prefix="/option-sets",
    tags=["option-set"],
    dependencies=[Depends(require_auth)],
)


@router.get("")
async def list_option_sets(
    registry: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
    keys: Annotated[str | None, Query(description="逗号分隔的选项集标识；空 = 全部")] = None,
) -> ApiResponse[OptionSetListResponse]:
    """列选项集快照（供列表页 / 表单元数据统一消费）。

    Args:
        registry: 选项集注册表（装载清单注册；运行期只读）。
        keys: 逗号分隔的选项集标识；空 = 全部。

    Returns:
        ApiResponse[OptionSetListResponse]: 统一响应，data 为选项集快照集合。

    Raises:
        NotFoundError: 请求的选项集未注册（10002）。
    """
    requested: ConcurrentStableList[str] = ConcurrentStableList()
    if keys:
        for raw in keys.split(","):
            key = raw.strip()
            if key and key not in requested:
                requested.add(key)
    else:
        requested.update(registry.keys())
    snapshots: ConcurrentStableList[OptionSetResponse] = ConcurrentStableList()
    for key in requested:
        info = registry.resolve(key)
        items: ConcurrentStableList[OptionSetItemResponse] = ConcurrentStableList(
            OptionSetItemResponse(
                value=item.value,
                label=item.label,
                label_key=item.label_key,
                color=item.color,
                disabled=item.disabled,
                sort=item.sort,
            )
            for item in info.items
        )
        snapshots.add(
            OptionSetResponse(
                option_set_key=info.option_set_key,
                name=info.name,
                namespace=info.namespace,
                version=info.version,
                items=items,
            )
        )
    return ApiResponse.ok(OptionSetListResponse(items=snapshots))
