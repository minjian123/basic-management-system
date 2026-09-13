"""schemas 层模块注册契约：模块注册清单响应。"""

from app.schemas.base import BaseSchema


class ModuleResponse(BaseSchema):
    """模块注册记录响应（与 `sys_module` 对齐）。"""

    module_key: str
    name: str
    table_prefix: str
    errcode_segment: str
    event_domain: str
    status: str
