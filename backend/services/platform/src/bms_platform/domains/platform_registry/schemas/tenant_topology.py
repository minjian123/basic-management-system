"""schemas 层租户拓扑契约（07C `02_01`）：记录响应 / 整批写入请求 / 按租户导出。

字段与 `sys_tenant_topology` 对齐（表结构以表文件为准）；**写入请求不接收库名**——库由部署单元派生。
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema


class TenantTopologyRowResponse(BaseSchema):
    """拓扑记录响应（与 `sys_tenant_topology` 对齐）。"""

    id: int
    tenant_id: int
    domain_key: str
    unit_key: str
    topology_version: int
    status: str
    note: str | None
    updated_at: datetime


class TenantTopologyRowRequest(BaseSchema):
    """整批写入的单行（部署单元由调用方指定，库名不落库）。"""

    domain_key: Annotated[str, Field(min_length=1, max_length=64, description="业务域标识（须已登记）")]
    unit_key: Annotated[str, Field(min_length=1, max_length=64, description="部署单元标识（小写字母开头）")]
    status: Annotated[str, Field(description="状态（enabled / disabled，缺省 enabled）")] = "enabled"
    note: Annotated[str, Field(max_length=255, description="说明（可选）")] = ""


class TenantTopologyWriteRequest(BaseSchema):
    """整批写入请求：`rows` 与 `template` **二选一**（模板先展开，再按需人工调整）。

    `version` 留空表示「当前版本 + 1」；显式给值时必须大于当前版本（拒绝回退）。
    """

    rows: Annotated[
        ConcurrentStableList[TenantTopologyRowRequest] | None,
        CONTRACT_COLLECTION,
        Field(description="整批行（与 template 二选一）"),
    ] = None
    template: Annotated[
        str | None,
        Field(description="参照模板名（single / grouped / isolated；与 rows 二选一）"),
    ] = None
    version: Annotated[int | None, Field(ge=1, description="拓扑版本（空=当前版本+1；须递增）")] = None
    note: Annotated[str, Field(max_length=255, description="本批次说明（可选）")] = ""


class TenantTopologyExportResponse(BaseSchema):
    """按租户导出当前版本（部署编排输入）。"""

    tenant_id: int
    version: int
    rows: Annotated[ConcurrentStableList[TenantTopologyRowResponse], CONTRACT_COLLECTION]


class TopologySnapshotRow(BaseSchema):
    """内部快照的一行（解析所需三列，不含 `note` / 审计等运营字段）。"""

    domain_key: Annotated[str, Field(description="业务域标识")]
    unit_key: Annotated[str, Field(description="部署单元标识")]
    status: Annotated[str, Field(description="状态（enabled / disabled）")]


class TopologySnapshotItem(BaseSchema):
    """一个租户的当前版本快照（`tenant_id = 0` 为默认拓扑）。"""

    tenant_id: Annotated[int, Field(description="租户主键（0 = 平台级默认拓扑）")]
    version: Annotated[int, Field(description="拓扑版本")]
    rows: Annotated[ConcurrentStableList[TopologySnapshotRow], CONTRACT_COLLECTION]


class TopologySnapshotResponse(BaseSchema):
    """拓扑全量快照（跨进程分发：其它服务装配期拉取后登记进程内快照）。"""

    default_version: Annotated[int, Field(description="默认拓扑（tenant_id=0）的当前版本；0 表示尚未自举")]
    snapshots: Annotated[ConcurrentStableList[TopologySnapshotItem], CONTRACT_COLLECTION]
