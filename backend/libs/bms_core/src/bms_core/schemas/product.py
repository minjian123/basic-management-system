"""schemas 层产品档案契约：产品档案登记记录响应（与 `bms_core/schemas/module.py` 同构）。

产品档案（`sys_product`）的对外只读面（R4.2 产品服务接入）；字段集与表结构一一对应，
**不含密钥 / 敏感项**，新增字段须同步表文件与本节口径。
"""

from bms_core.schemas.base import BaseSchema


class ProductResponse(BaseSchema):
    """产品档案记录响应（与 `sys_product` 对齐）。"""

    product_key: str
    name: str
    frontend_package_source: str | None
    status: str
