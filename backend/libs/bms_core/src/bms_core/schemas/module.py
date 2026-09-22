"""schemas 层服务目录契约：服务 / 模块登记记录响应。"""

from bms_core.schemas.base import BaseSchema


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
