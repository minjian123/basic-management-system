"""core 层根基类：所有可继承类的公共方法落点。"""

import dataclasses
from abc import ABC
from collections.abc import Iterable, Mapping
from typing import Any, cast

from app.core.serialization import stable_json_dumps


class BaseObject(ABC):  # noqa: B024  抽象基座：只承载公共方法，不直接实例化
    """后端根基类：字符串输出、序列化、相等与哈希的统一实现。

    - 只放方法、不放字段（字段归模型基类 BaseModel，见 03-2）
    - 子类自带实现优先（dataclass/Pydantic 生成的 __eq__/__repr__ 覆盖本类同名方法）
    - __eq__/__hash__：有主键（id）按 (类名, 主键)，无主键按身份
    """

    def to_dict(self) -> dict[str, object]:
        """公开字段字典（递归转换嵌套对象）。

        Returns:
            dict[str, object]: 字段名到转换后值的映射。
        """
        return {key: self._convert(value) for key, value in self._public_fields().items()}

    def to_json(self, sort_keys: bool = True) -> str:
        """JSON 字符串（稳定序；不可序列化值降级 str）。

        Args:
            sort_keys: 是否按键排序（默认 True，保证输出稳定）。

        Returns:
            str: JSON 字符串。
        """
        return stable_json_dumps(self.to_dict(), sort_keys=sort_keys)

    def __str__(self) -> str:
        """字符串输出：类名 + 公开字段字典。"""
        return f"{type(self).__name__}({self.to_dict()})"

    def __repr__(self) -> str:
        """字符串输出（与 __str__ 一致，容器内展示统一）。"""
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        """相等判定：同类且主键相同；无主键退化为身份比较。

        Args:
            other: 比较对象。

        Returns:
            bool: 相等 True。
        """
        if other is self:
            return True
        if type(other) is not type(self):
            return False
        item_id = getattr(self, "id", None)
        other_id = getattr(other, "id", None)
        if item_id is None or other_id is None:
            return False
        return bool(item_id == other_id)

    def __hash__(self) -> int:
        """哈希：有主键按 (类名, 主键)，无主键按身份。

        Returns:
            int: 哈希值。
        """
        item_id = getattr(self, "id", None)
        if item_id is None:
            return object.__hash__(self)
        return hash((type(self).__name__, item_id))

    def _public_fields(self) -> dict[str, object]:
        """取公开字段：Pydantic 序列化器 → dataclass 声明字段 → 实例字典兜底。

        Returns:
            dict[str, object]: 字段映射。
        """
        model_dump = getattr(self, "model_dump", None)
        if callable(model_dump) and getattr(type(self), "model_fields", None) is not None:
            return cast("dict[str, object]", model_dump())
        if dataclasses.is_dataclass(self) and not isinstance(self, type):
            try:
                return {
                    field.name: getattr(self, field.name)
                    for field in dataclasses.fields(cast("Any", self))
                    if not field.name.startswith("_")
                }
            except TypeError:
                pass
        return {key: value for key, value in getattr(self, "__dict__", {}).items() if not key.startswith("_")}

    @classmethod
    def _convert(cls, value: object) -> object:
        """递归转换字段值（嵌套 BaseObject/映射/序列逐层转换）。

        Args:
            value: 原始值。

        Returns:
            object: 转换后的值。
        """
        if isinstance(value, BaseObject):
            return value.to_dict()
        if isinstance(value, Mapping):
            mapping = cast("Mapping[object, object]", value)
            return {key: cls._convert(item) for key, item in mapping.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            sequence = cast("Iterable[object]", value)
            return [cls._convert(item) for item in sequence]
        return value


class ValueHolder[ValueT](BaseObject):
    """`get_locked` 类上下文内可替换的值容器（进程内与 Redis 复用）。"""

    def __init__(self, value: ValueT) -> None:
        self.value = value
