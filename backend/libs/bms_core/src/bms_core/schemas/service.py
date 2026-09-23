"""跨服务契约数据契约：服务间调用响应 DTO 基类。

服务间同步读（`BaseServiceClient`）返回体落本基类派生模型；跨服务读**只经契约 DTO 或本地只读投影**
（`BaseQueryProvider`），禁止直接依赖他服务 ORM 模型（见《后端开发规范》「模块边界与数据所有权」节）。
"""

from bms_core.schemas.base import BaseSchema

__all__ = ["ServiceDto"]


class ServiceDto(BaseSchema):
    """跨服务公开契约响应 DTO 基类：复用统一序列化 / ID 字符串化 / 敏感字段掩码口径。

    只作公共基类，不引入跨服务字段耦合；具体字段由消费方按目标服务公开契约声明。
    """
