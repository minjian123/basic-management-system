"""schemas 层服务目录契约：服务 / 模块登记记录响应，以及带参快照的产品段与能力段。"""

from typing import Annotated

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    BaseSchema,
)


class ModuleResponse(BaseSchema):
    """服务目录登记记录响应（与 `sys_module` 对齐）。"""

    module_key: str
    service_key: str | None
    name: str
    table_prefix: str
    business_code: str | None
    errcode_segment: str | None
    event_domain: str
    service_group: str
    build_batch: int
    service_version: str
    contract_version: str
    product_key: str | None
    status: str


class ProductSnapshotItem(BaseSchema):
    """带参快照的产品段（前端产品键来源；**不含** `frontend_package_source` 等构建期信息）。"""

    product_key: str
    name: str
    status: str


class CollaborationSnapshotItem(BaseSchema):
    """带参快照的能力段（前端取址 / 服务启动对账共用）。

    **不含** `path`（不向浏览器暴露服务内部路径）与 `default_consumers` 等授权信息（分配出口归 `02_04`）。
    """

    name: str
    domain: str
    product_key: str | None
    frontend_prefix: str | None
    contract_version: str
    status: str
    replacement: str | None


class CatalogSnapshotResponse(BaseSchema):
    """带参快照响应（`GET /api/v1/modules/snapshot?with=`；**缺省形态仍为 `ModuleResponse` 数组**）。

    口径：

    - `modules` 恒下发（服务目录本体，来源不变）；
    - `products` / `collaborations` 仅在 `with` 中声明的段下发，未声明为空数组（不额外查询、不多暴露）；
    - `snapshot_version` 为带参形态的契约版本（形态变更时递增，便于消费方识别，避免与数组形态混用）；
    - `warnings` 承载降级提示（如产品声明未装载），不静默。
    """

    modules: Annotated[ConcurrentStableList[ModuleResponse], CONTRACT_COLLECTION]
    products: Annotated[ConcurrentStableList[ProductSnapshotItem], CONTRACT_COLLECTION]
    collaborations: Annotated[ConcurrentStableList[CollaborationSnapshotItem], CONTRACT_COLLECTION]
    snapshot_version: str
    warnings: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION]
