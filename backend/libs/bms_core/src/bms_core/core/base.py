"""core 层根基类：所有可继承类的公共方法落点。"""

import dataclasses
from collections.abc import Iterable, Mapping, Sequence, Set
from typing import TYPE_CHECKING, Any, cast

from bms_core.core.serialization import rebuild_mapping, rebuild_sequence, stable_json_dumps, stringify_ids

if TYPE_CHECKING:
    # 运行期反向依赖：`core.concurrent -> core.base`（集合体系实现承 `BaseObject`），故此处仅类型期引用，
    # 构造点在使用处延迟导入，避免运行期导入成环。
    from bms_core.core.concurrent import ConcurrentStableDict


class BaseObject:
    """后端根基类：字符串输出、序列化、相等与哈希的统一实现。

    - 只放方法、不放字段（字段归模型基类 BaseModel）
    - 子类自带实现优先（dataclass/Pydantic 生成的 __eq__/__repr__ 覆盖本类同名方法）
    - __eq__/__hash__：有主键（id）按 (类名, 主键)，无主键按身份
    - 普通类（非 ABC）：可被 SQLAlchemy 声明式基类等混合继承（元类兼容）
    """

    # 运行期成环：`core.concurrent -> core.base`，须字符串前向引用（免运行期导入）
    def to_dict(self) -> "ConcurrentStableDict[str, object]":  # noqa: UP037
        """公开字段字典（递归转换嵌套对象；ID 值按字符串输出）。

        Returns:
            ConcurrentStableDict[str, object]: 字段名到转换后值的映射。
        """
        from bms_core.core.concurrent import ConcurrentStableDict

        fields = ConcurrentStableDict({key: self._convert(value) for key, value in self._public_fields().items()})
        return cast("ConcurrentStableDict[str, object]", stringify_ids(fields))

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
        return f"{type(self).__name__}({dict(self.to_dict())})"

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

    def _public_fields(self) -> "ConcurrentStableDict[str, object]":  # noqa: UP037
        """取公开字段：Pydantic 序列化器 → dataclass 声明字段 → 实例字典兜底。

        Returns:
            ConcurrentStableDict[str, object]: 字段映射。

        Note:
            dataclass 分支要求**本类自身**由 `@dataclass` 声明（`__dataclass_fields__` 在自己的
            `__dict__` 中）：ORM 模型（`BaseModel`）继承 `@dataclass` 体系根（`BaseDataContract`）后
            会被 `dataclasses.is_dataclass` 判真，但其字段在实例字典而非 dataclass 字段 → 须走兜底分支。
        """
        from bms_core.core.concurrent import ConcurrentStableDict

        model_dump = getattr(self, "model_dump", None)
        if callable(model_dump) and getattr(type(self), "model_fields", None) is not None:
            return ConcurrentStableDict(cast("Mapping[str, object]", model_dump()))
        if dataclasses.is_dataclass(self) and not isinstance(self, type) and "__dataclass_fields__" in vars(type(self)):
            try:
                return ConcurrentStableDict(
                    {
                        field.name: getattr(self, field.name)
                        for field in dataclasses.fields(cast("Any", self))
                        if not field.name.startswith("_")
                    }
                )
            except TypeError:
                pass
        return ConcurrentStableDict(
            {key: value for key, value in getattr(self, "__dict__", {}).items() if not key.startswith("_")}
        )

    @classmethod
    def _convert(cls, value: object) -> object:
        """递归转换字段值（嵌套 BaseObject/映射/序列逐层转换）。

        按 `collections.abc` 只读面识别映射 / 序列 / 集合（含基座集合类并**同型重组**）；
        `str` / `bytes` / `bytearray` 不参与识别；内置 `set` / `frozenset` 按列表输出。

        Args:
            value: 原始值。

        Returns:
            object: 转换后的值。
        """
        if isinstance(value, Mapping):
            mapping = cast("Mapping[object, object]", value)
            return rebuild_mapping(mapping, ((key, cls._convert(item)) for key, item in mapping.items()))
        if isinstance(value, (str, bytes, bytearray)):
            return value
        if isinstance(value, Sequence):
            sequence = cast("Sequence[object]", value)
            return rebuild_sequence(sequence, (cls._convert(item) for item in sequence))
        if isinstance(value, Set):
            members = cast("Set[object]", value)
            if isinstance(members, BaseObject):
                return rebuild_sequence(members, (cls._convert(item) for item in members))
            elements = cast("Iterable[object]", members)
            return [cls._convert(item) for item in elements]
        if isinstance(value, BaseObject):
            return value.to_dict()
        return value
