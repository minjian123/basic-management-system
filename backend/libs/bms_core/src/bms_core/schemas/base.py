"""schemas 层基类：Pydantic 公共配置、契约集合元数据、ID 序列化与敏感字段掩码口径。

- `CONTRACT_COLLECTION`：把基座并发集合类（`ConcurrentStable*`）接入 Pydantic 校验 / 序列化 / JSON Schema，
  契约字段一律以内联 `Annotated[集合类[X], CONTRACT_COLLECTION]` 声明（禁命名泛型别名，防契约 `$defs` 漂移）；
- 契约集合 JSON Schema 与 `list[X]` / `frozenset[X]` / `dict[K, V]` **逐字节一致**（契约零漂移为门禁）；
- `core/` 不引入 Pydantic（元数据只落本层）。
"""

import types
from collections.abc import Callable, Mapping, Set
from typing import Any, ClassVar, Union, cast, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    SerializationInfo,
    model_serializer,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

from bms_core.core.collections import BaseCollection
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.context import get_current_masker
from bms_core.core.objects import BaseDataContract, BaseFrameworkObject
from bms_core.core.serialization import stringify_ids

CollectionType = type[BaseCollection[Any]]
"""基座集合类（`BaseCollection` 子类）类型。"""


def _collection_type(source_type: Any) -> CollectionType | None:
    """取注解中的基座集合类（非基座集合类返回 None）。

    Args:
        source_type: 注解类型（如 `ConcurrentStableList[X]`）。

    Returns:
        CollectionType | None: 基座集合类，或 None。
    """
    origin = get_origin(source_type)
    if isinstance(origin, type) and issubclass(origin, BaseCollection):
        return cast("CollectionType", origin)
    return None


class _ContractCollection(BaseFrameworkObject):
    """契约集合元数据：把基座集合类接入 Pydantic 校验、序列化与 JSON Schema。

    - **校验**：按同类内置容器 schema（`list` / `frozenset` / `dict`）校验后转为集合类实例；
    - **序列化**：Python 模式重组为同类集合实例（元素递归 dump），JSON 模式输出内置容器（array / object）；
    - **JSON Schema**：与 `list[X]` / `frozenset[X]` / `dict[K, V]` 逐字节一致；
    - **联合形态**：`Annotated[集合类[X] | None, CONTRACT_COLLECTION]` 同样适用。
    """

    def __get_pydantic_core_schema__(self, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        """按注解类型生成集合类 core schema。

        Args:
            source_type: 被标注类型（`Annotated` 去掉元数据后）。
            handler: Pydantic core schema 处理器。

        Returns:
            CoreSchema: 集合类校验 / 序列化 / JSON Schema schema。
        """
        origin = get_origin(source_type)
        if origin is Union or origin is types.UnionType:
            return core_schema.union_schema(
                [
                    self.__get_pydantic_core_schema__(member, handler)
                    if _collection_type(member) is not None
                    else handler.generate_schema(member)
                    for member in get_args(source_type)
                ]
            )
        collection = _collection_type(source_type)
        if collection is None:
            return handler.generate_schema(source_type)
        return self._container_schema(collection, get_args(source_type), handler)

    def _element_schema(self, arg: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        """生成元素 / 键 / 值 schema（**嵌套基座集合类**递归经本元数据）。

        Args:
            arg: 元素 / 键 / 值类型。
            handler: Pydantic core schema 处理器。

        Returns:
            CoreSchema: 元素 schema。
        """
        if _collection_type(arg) is not None:
            return self.__get_pydantic_core_schema__(arg, handler)
        return handler.generate_schema(arg)

    def _container_schema(
        self, collection: CollectionType, args: tuple[Any, ...], handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        """按集合类所属映射 / 集合 / 序列分派到同类内置容器 schema。

        校验统一按内置容器（映射 `dict` / 序列 `list`），**集合类以 `list` 校验以保插入序**（去重交集合类），
        其 JSON Schema 的 `uniqueItems` 由 `__get_pydantic_json_schema__` 补齐（与 `frozenset[X]` 逐字节一致）。

        Args:
            collection: 基座集合类。
            args: 注解泛型实参（元素 / 键值类型）。
            handler: Pydantic core schema 处理器。

        Returns:
            CoreSchema: 校验（内置容器 → 集合类）+ 序列化（Python 同类 / JSON 内置）schema。
        """
        if issubclass(collection, Mapping):
            kind = "dict"
            key_schema = self._element_schema(args[0], handler) if len(args) == 2 else core_schema.any_schema()
            value_schema = self._element_schema(args[1], handler) if len(args) == 2 else core_schema.any_schema()
            inner = core_schema.dict_schema(key_schema, value_schema)
            to_builtin = cast("Callable[[Any], Any]", dict)
        else:
            item_schema = self._element_schema(args[0], handler) if args else core_schema.any_schema()
            inner = core_schema.list_schema(item_schema)
            to_builtin = cast("Callable[[Any], Any]", list)
            kind = "set" if issubclass(collection, Set) else "list"
        factory = cast("Callable[[Any], Any]", collection)

        def before(value: Any) -> Any:
            """已传入集合类实例时先落内置容器，交内置 schema 校验。"""
            return to_builtin(value) if isinstance(value, BaseCollection) else value

        def after(value: Any) -> Any:
            """校验通过的内置容器转为集合类实例。"""
            return factory(value)

        def serialize(value: Any, wrap: Callable[[Any], Any], info: SerializationInfo) -> Any:
            """序列化：Python 模式同类重组、JSON 模式内置容器。"""
            converted = wrap(to_builtin(value))
            return converted if info.mode == "json" else type(value)(converted)

        serializer = core_schema.wrap_serializer_function_ser_schema(serialize, schema=inner, info_arg=True)
        normalized = core_schema.no_info_before_validator_function(before, inner)
        return core_schema.no_info_after_validator_function(
            after, normalized, serialization=serializer, metadata={"contract_collection_kind": kind}
        )

    def __get_pydantic_json_schema__(self, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """集合类 JSON Schema 与内置容器逐字节一致（集合补 `uniqueItems`）。

        Args:
            schema: 本元数据生成的 core schema。
            handler: Pydantic JSON Schema 处理器。

        Returns:
            JsonSchemaValue: 契约 JSON Schema（`array` / `object`）。
        """
        json_schema = handler(schema)
        if schema.get("metadata", {}).get("contract_collection_kind") == "set":
            json_schema["uniqueItems"] = True
        return json_schema


CONTRACT_COLLECTION = _ContractCollection()
"""Pydantic 契约集合元数据：`Annotated[集合类[X], CONTRACT_COLLECTION]` 声明契约字段。"""

CONTRACT_STABLE_LIST: Callable[[], ConcurrentStableList[Any]] = ConcurrentStableList
"""插入序列表空集合工厂（`Field(default_factory=...)`）。"""

CONTRACT_STABLE_DICT: Callable[[], ConcurrentStableDict[Any, Any]] = ConcurrentStableDict
"""插入序映射空集合工厂（`Field(default_factory=...)`）。"""

CONTRACT_STABLE_SET: Callable[[], ConcurrentStableSet[Any]] = ConcurrentStableSet
"""插入序集合空集合工厂（`Field(default_factory=...)`）。"""


def _apply_masking(masked_fields: ConcurrentStableSet[str], data: object) -> object:
    """按当前掩码器掩码敏感字段。

    未注入掩码器（`current_masker` 为 None）/ 无敏感字段声明 / 序列化结果非字典时**原样返回**
    （占位期行为与既有完全一致）。

    Args:
        masked_fields: 需掩码的字段集合。
        data: 序列化结果。

    Returns:
        object: 掩码后的结果。
    """
    masker = get_current_masker()
    if masker is None or not masked_fields or not isinstance(data, dict):
        return data
    fields = cast("dict[str, object]", data)
    for field in masked_fields:
        if field in fields:
            fields[field] = masker.mask(field, fields[field])
    return fields


class BaseSchema(BaseModel, BaseDataContract):
    """Pydantic 模型基类：请求/响应模型统一继承。

    - from_attributes：允许 ORM/实体对象直接校验（响应模型使用）
    - str_strip_whitespace：字符串字段自动去除首尾空白
    - 序列化：继承 `BaseObject`（声明字段优先）；统一把 `id` / `*_id` 按字符串输出（JS 安全整数）
    - 敏感字段：类属性 `masked_fields` 声明的字段在序列化时经当前掩码器掩码（未注入掩码器时直通）
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    masked_fields: ClassVar[ConcurrentStableSet[str]] = ConcurrentStableSet()
    """需掩码的敏感字段（默认空集＝不掩码）；真实规则随性能与安全阶段回补。"""

    @model_serializer(mode="wrap")
    def _serialize_ids(self, serializer: Callable[..., Any], info: SerializationInfo) -> Any:
        """序列化包装：字段 ID 值字符串化 + 敏感字段掩码。

        Args:
            serializer: Pydantic 序列化器。
            info: 序列化信息。

        Returns:
            Any: 序列化结果。
        """
        del info
        return _apply_masking(type(self).masked_fields, stringify_ids(serializer(self)))
