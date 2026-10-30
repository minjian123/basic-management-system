"""schemas 层发布清单契约（07C `04_01`）：清单响应 / 明细响应 / 预检与回滚结论。

字段与 `sys_release_manifest` / `sys_release_manifest_domain` 对齐（表结构以表文件为准）；
预检结论与回滚计划是**计算产物**（不落库），字段只为「运维与流水线能直接读数」而设。
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema


class ReleaseDomainEntryResponse(BaseSchema):
    """发布清单的域明细（某业务域本次发布到哪个版本）。"""

    domain_key: Annotated[str, Field(description="业务域标识")]
    service_key: Annotated[str, Field(description="承载该域的服务标识；历史读取时可能为空")]
    service_version: Annotated[str, Field(description="服务版本")]
    contract_version: Annotated[str, Field(description="契约版本")]
    schema_revision: Annotated[str | None, Field(description="表结构 revision（无表结构的域为空）")]
    note: Annotated[str, Field(description="说明")]


class ReleaseManifestResponse(BaseSchema):
    """一次发布的完整快照（主表字段 + 逐域明细）。"""

    id: Annotated[int, Field(description="清单主键")]
    unit_key: Annotated[str, Field(description="部署单元标识")]
    tenant_scope: Annotated[int, Field(description="作用范围（0 = 全局）")]
    manifest_version: Annotated[int, Field(description="发布批次号")]
    topology_version: Annotated[int, Field(description="本次发布对应的拓扑版本")]
    status: Annotated[str, Field(description="状态（released / rolled_back / failed）")]
    released_at: Annotated[datetime, Field(description="发布时间（UTC）")]
    rolled_back_from: Annotated[int | None, Field(description="回滚来源清单主键")]
    note: Annotated[str, Field(description="说明")]
    domains: Annotated[
        ConcurrentStableList[ReleaseDomainEntryResponse], CONTRACT_COLLECTION, Field(description="逐域明细")
    ]


class ReleaseManifestListResponse(BaseSchema):
    """发布快照数组（按单元查最近发布；不套分页结构，便于运维直接读首条）。"""

    items: Annotated[ConcurrentStableList[ReleaseManifestResponse], CONTRACT_COLLECTION, Field(description="发布快照")]


class ReleaseCheckItemResponse(BaseSchema):
    """一项前置校验的结论。"""

    key: Annotated[str, Field(description="校验标识")]
    title: Annotated[str, Field(description="校验名称")]
    passed: Annotated[bool, Field(description="是否通过")]
    detail: Annotated[str, Field(description="详情（失败时给出定位信息）")]


class ReleasePrecheckResponse(BaseSchema):
    """发布前置校验的整体结论（任一不过即整体失败）。"""

    unit_key: Annotated[str, Field(description="部署单元标识")]
    tenant_scope: Annotated[int, Field(description="作用范围（0 = 全局）")]
    manifest_version: Annotated[int, Field(description="本次批次号")]
    topology_version: Annotated[int, Field(description="绑定的拓扑版本")]
    passed: Annotated[bool, Field(description="整体是否通过")]
    entries: Annotated[
        ConcurrentStableList[ReleaseDomainEntryResponse], CONTRACT_COLLECTION, Field(description="将写入的明细")
    ]
    items: Annotated[ConcurrentStableList[ReleaseCheckItemResponse], CONTRACT_COLLECTION, Field(description="逐项结论")]


class RollbackStepResponse(BaseSchema):
    """回滚计划中的一步。"""

    domain_key: Annotated[str, Field(description="业务域标识")]
    from_revision: Annotated[str | None, Field(description="当前发布的结构 revision")]
    to_revision: Annotated[str | None, Field(description="目标发布的结构 revision")]


class RollbackPlanResponse(BaseSchema):
    """批次回滚计划（按清单整体回退，不支持部分回滚）。"""

    unit_key: Annotated[str, Field(description="部署单元标识")]
    tenant_scope: Annotated[int, Field(description="作用范围（0 = 全局）")]
    from_version: Annotated[int, Field(description="被回滚的批次号")]
    to_version: Annotated[int, Field(description="回退目标批次号")]
    requires_confirmation: Annotated[bool, Field(description="是否需要人工确认（涉及结构回退）")]
    executable: Annotated[bool, Field(description="是否可执行（无阻断原因）")]
    steps: Annotated[ConcurrentStableList[RollbackStepResponse], CONTRACT_COLLECTION, Field(description="逐域步骤")]
    blocked_reasons: Annotated[
        ConcurrentStableList[str], CONTRACT_COLLECTION, Field(description="阻断原因（非空即不可执行）")
    ]
