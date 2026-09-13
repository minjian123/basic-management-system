"""schemas 层基类：Pydantic 公共配置与 ID 序列化口径。"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, SerializationInfo, model_serializer

from app.core.base import BaseObject
from app.core.serialization import stringify_ids


class BaseSchema(BaseModel, BaseObject):
    """Pydantic 模型基类：请求/响应模型统一继承。

    - from_attributes：允许 ORM/实体对象直接校验（响应模型使用）
    - str_strip_whitespace：字符串字段自动去除首尾空白
    - 序列化：继承 `BaseObject`（声明字段优先）；统一把 `id` / `*_id` 按字符串输出（JS 安全整数）
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @model_serializer(mode="wrap")
    def _serialize_ids(self, serializer: Callable[..., Any], info: SerializationInfo) -> Any:
        """序列化包装：对字段 ID 值做字符串化。

        Args:
            serializer: Pydantic 序列化器。
            info: 序列化信息。

        Returns:
            Any: 序列化结果。
        """
        del info
        return stringify_ids(serializer(self))
