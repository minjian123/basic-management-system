"""表单标识路由：`/api/v1/form-keys`（登录即可；2026-10-12 新增，任务 02-13-1）。

- `GET /api/v1/form-keys`：`form_key` 构建期清单（`form_key` / 名称 / 类型 `kind` / 物理表 /
  `data_source_key` / 状态），供**通用页面路由**按 `form_key` 解析页面并经 `form_key → data_source_key`
  （多对一）取数。
- 清单为**代码内构建期清单**（`bms_core/registry/forms.py`，各项目装载注入、运行期只读），**不落表**。
- 与 `GET /api/v1/forms`（权限表单维护，`menu.py`）区分：后者为菜单 / 权限表单元数据，无 `form_key`。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.registry.forms import FormKind, merge_form_records
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.form import FormKeyListResponse, FormKeyResponse

router = BaseRouter(
    key="form_key",
    prefix="/form-keys",
    tags=["form-key"],
    dependencies=[Depends(require_auth)],
)


@router.get("")
async def list_form_keys(
    kind: Annotated[str | None, Query(description="按类型过滤（dict / form；空 = 全部）")] = None,
) -> ApiResponse[FormKeyListResponse]:
    """列表单标识清单（供通用页面路由：`form_key → data_source_key`）。

    Args:
        kind: 类型过滤（`dict` / `form`；空 = 全部）。

    Returns:
        ApiResponse[FormKeyListResponse]: 统一响应，data 为表单标识清单（`items` 保序）。

    Raises:
        ParamError: 类型取值非法。
    """
    if kind is not None and kind not in {item.value for item in FormKind}:
        raise ParamError(f"表单类型非法：{kind}")
    records: ConcurrentStableList[FormKeyResponse] = ConcurrentStableList()
    for record in merge_form_records():
        if kind is not None and record.kind != kind:
            continue
        records.add(FormKeyResponse.model_validate(record))
    return ApiResponse.ok(FormKeyListResponse(items=records))
