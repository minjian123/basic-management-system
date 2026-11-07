"""租户配额只读视图（07D `02_03`）：`/api/v1/tenant-quotas/projections`。

- **只读**：平台按产品声明的 `kind = quota` 数据源实时取数，**不落库、不缓存、不双写**；
  产品端点是配额的单一事实源，平台侧不维护第二份值（架构 41 §5.3）。
- **权限**：`tenant-quota:query`（平台运营角色）；业务段不在 `sys_module` 中，不触发租户模块门禁。
- **审计**：端点声明 `audit_read`，读取进操作日志（读方法按端点显式另记）。
- **失败不整页失败**：单产品不可达时该产品条目 `unavailable`，HTTP 仍 200（运营视图部分可用）。
"""

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.datasource.registry import DataSourceKind, DataSourceRecord, data_source_records_view
from bms_core.permission.base import require_permission
from bms_core.quota.reader import QuotaProjectionReader
from bms_core.schemas.common import ApiResponse
from bms_core.servicecall.base import get_service_client

router = BaseRouter(
    key="tenant-quotas",
    prefix="/tenant-quotas",
    tags=["tenant-quota"],
)

_REQUIRE_QUERY = Depends(require_permission("tenant-quota:query"))


@router.get("/projections", dependencies=[_REQUIRE_QUERY])
async def list_quota_projections(
    request: Request,
    tenant_id: int,
    module_key: str | None = None,
    resource_key: str | None = None,
) -> ApiResponse:
    """租户配额投影视图（按租户取产品只读投影）。

    需要 `tenant-quota:query` 权限。

    Args:
        request: 请求对象（取服务间调用客户端；并声明读取审计）。
        tenant_id: 租户主键（雪花 id）。
        module_key: 模块键过滤（可选）。
        resource_key: 资源标识过滤（可选）。

    Returns:
        ApiResponse: 统一响应，data 为投影条目数组（与 `/scope-resource-types` 同风格）。
    """
    request.scope.setdefault("state", {})["audit_read"] = True  # type: ignore[index]
    records: ConcurrentStableList[DataSourceRecord] = ConcurrentStableList(
        record
        for record in data_source_records_view()
        if record.kind == DataSourceKind.QUOTA.value and record.status == "enabled"
    )
    if module_key is not None:
        records = ConcurrentStableList(
            record for record in records if str(record.data_source).split(".", 1)[0] == module_key
        )
    reader = QuotaProjectionReader(lambda: get_service_client(request))
    items = await reader.read(records, tenant_id=tenant_id)
    filtered = ConcurrentStableList(item for item in items if resource_key is None or item.resource_key == resource_key)
    return ApiResponse.ok(ConcurrentStableList(item.model_dump(mode="json") for item in filtered).to_list())
