"""数据源路由：`/api/v1/data-sources`（登录即可；02_10 由字典清单端点泛化而来）。

- `GET /api/v1/data-sources`：统一数据源登记清单（`data_source_key` / 名称 / 类型 `kind` / 数据出口 /
  来源 / 字段白名单 / 级联 / 可用策略 / 状态），供**数据权限左列**与**通用页面**取可用数据源。
- 清单为**代码内构建期清单**（`bms_core/datasource/registry.py`，各项目装载注入、运行期只读），**不落表**。
- 运行时取数不经本端点：字典经 `/api/v1/dicts/*`；产品来源（`origin=product`）由前端经网关直取产品命名空间。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.datasource.registry import DataSourceKind
from bms_core.dict.outlet import build_data_source_outlet
from bms_core.schemas.common import ApiResponse

router = BaseRouter(
    key="data_source",
    prefix="/data-sources",
    tags=["data-source"],
    dependencies=[Depends(require_auth)],
)


@router.get("")
async def list_data_sources(
    kind: Annotated[str | None, Query(description="按类型过滤（dict / form；空 = 全部）")] = None,
) -> ApiResponse:
    """列统一数据源登记清单（供数据权限左列 / 通用页面）。

    Args:
        kind: 类型过滤（`dict` / `form`；空 = 全部）。

    Returns:
        ApiResponse: 统一响应，data 为登记清单数组。

    Raises:
        ParamError: 类型取值非法。
    """
    if kind is not None and kind not in {item.value for item in DataSourceKind}:
        raise ParamError(f"数据源类型非法：{kind}")
    records: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for record in build_data_source_outlet().registry.catalog_records():
        if kind is not None and record.kind != kind:
            continue
        records.add(
            ConcurrentStableDict(
                {
                    "data_source_key": record.data_source_key,
                    "name": record.name,
                    "kind": record.kind,
                    "data_source": record.data_source,
                    "origin": record.origin,
                    "product_key": record.product_key,
                    "path": record.path,
                    "allowlist": list(record.allowlist),
                    "cascade": record.cascade,
                    "strategies": list(record.strategies),
                    "status": record.status,
                }
            )
        )
    return ApiResponse.ok([dict(record) for record in records])
