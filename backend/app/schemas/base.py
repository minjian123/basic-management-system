"""schemas 层基类：Pydantic 公共配置。"""

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Pydantic 模型基类：请求/响应模型统一继承。

    - from_attributes：允许 ORM/实体对象直接校验（03-2 落库后响应模型使用）
    - str_strip_whitespace：字符串字段自动去除首尾空白
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
