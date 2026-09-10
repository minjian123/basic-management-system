"""schemas 层基类：Pydantic 公共配置。"""

from pydantic import BaseModel, ConfigDict

from app.core.base import BaseObject


class BaseSchema(BaseModel, BaseObject):
    """Pydantic 模型基类：请求/响应模型统一继承。

    - from_attributes：允许 ORM/实体对象直接校验（03-2 落库后响应模型使用）
    - str_strip_whitespace：字符串字段自动去除首尾空白
    - 继承 BaseObject：to_dict/to_json 可用；Pydantic 自身语义优先（见 MRO 约定）
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
