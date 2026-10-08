"""schemas 层基类：Pydantic 公共配置、契约集合元数据、ID 序列化与敏感字段掩码口径。

- `CONTRACT_COLLECTION`：把基座并发集合类（`ConcurrentStable*`）接入 Pydantic 校验 / 序列化 / JSON Schema，
  契约字段一律以内联 `Annotated[集合类[X], CONTRACT_COLLECTION]` 声明（禁命名泛型别名，防契约 `$defs` 漂移）；
- 契约集合 JSON Schema 与 `list[X]` / `frozenset[X]` / `dict[K, V]` **逐字节一致**（契约零漂移为门禁）；
- `masked_fields`：敏感字段声明（字段 → 策略 映射，或字段名集合兼容写法），序列化时经当前掩码器递归
  掩码（含嵌套模型与列表；未注入掩码器时直通）；
- `core/` 不引入 Pydantic（元数据只落本层）。
"""

import types
from collections.abc import Callable, Iterable, Mapping, Set
from typing import Any, ClassVar, Protocol, Union, cast, get_args, get_origin

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
from bms_core.core.serialization import is_id_key, stringify_ids


class _MaskerProtocol(Protocol):
    """序列化掩码所需的最小掩码器面（结构化类型，避免 schemas 层反向依赖 masking 域）。"""

    def mask(self, field: str, value: object, strategy: str | None = None) -> object:
        """掩码字段值（语义见 `BaseMasker.mask`）。

        Args:
            field: 字段名。
            value: 原始值。
            strategy: 字段策略（缺省 None，由实现按注册 / 字段名解析）。

        Returns:
            object: 明文（有权限 / 未声明）或掩码值。
        """
        ...


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


def _stringified_value_schema(value: Any) -> Any:
    """把 ID 字段的值 schema 改写为字符串口径（`anyOf` / `oneOf` 成员递归）。

    Args:
        value: 字段值 schema（映射或标量）。

    Returns:
        Any: 改写后的 schema；非映射原样返回。
    """
    if not isinstance(value, Mapping):
        return value
    mapping = cast("Mapping[str, object]", value)
    if mapping.get("type") == "integer":
        return {**mapping, "type": "string"}
    rewritten = dict(mapping)
    for key in ("anyOf", "oneOf"):
        members = mapping.get(key)
        if isinstance(members, list):
            rewritten[key] = [_stringified_value_schema(member) for member in cast("list[object]", members)]
    return rewritten


def _stringify_id_properties(json_schema: JsonSchemaValue) -> JsonSchemaValue:
    """把模型 `properties` 中 ID 字段的 schema 改写为字符串口径（未命中时原样）。

    判定与运行时 `stringify_ids` 同源（`is_id_key`）：`id` / `*_id` 的整型值在序列化输出中
    一律字符串化，故其契约 schema 也应为字符串。

    Args:
        json_schema: 模型 JSON Schema（`properties` 就地改写）。

    Returns:
        JsonSchemaValue: 改写后的 JSON Schema。
    """
    properties = json_schema.get("properties")
    if not isinstance(properties, Mapping):
        return json_schema
    typed = cast("dict[str, Any]", properties)
    for name, value in typed.items():
        if is_id_key(name):
            typed[name] = _stringified_value_schema(value)
    return json_schema


MaskedFields = ConcurrentStableDict[str, str] | ConcurrentStableSet[str]
"""敏感字段声明形态：字段 → 策略 映射，或字段名集合（兼容写法，字段名同时作为策略名）。"""

_MAX_MASK_DEPTH = 5
"""掩码递归深度上限（防深层 / 循环结构；与日志脱敏同口径）。"""


def _normalize_masked_fields(masked_fields: MaskedFields) -> ConcurrentStableDict[str, str]:
    """把敏感字段声明归一化为「字段 → 策略」映射。

    映射写法原样使用；集合写法把字段名同时作为策略名——「字段名同名内置策略、否则兜底 `custom` 全掩码」
    由掩码器解析链单点实现（见 `DefaultMasker._resolve_strategy`）。

    Args:
        masked_fields: 敏感字段声明（映射或集合）。

    Returns:
        ConcurrentStableDict[str, str]: 归一化后的字段 → 策略映射。
    """
    if isinstance(masked_fields, ConcurrentStableDict):
        return ConcurrentStableDict[str, str]({str(field): str(strategy) for field, strategy in masked_fields.items()})
    return ConcurrentStableDict[str, str]({str(field): str(field) for field in masked_fields})


def _mask_mapping(
    masked: ConcurrentStableDict[str, str],
    data: object,
    masker: _MaskerProtocol,
    depth: int,
) -> object:
    """递归掩码映射：命中声明字段的标量掩码，容器继续下钻（容器类型保持）。

    Args:
        masked: 归一化后的字段 → 策略映射。
        data: 待掩码映射（序列化结果的字典；调用方已按映射判定传入）。
        masker: 当前掩码器。
        depth: 当前嵌套深度。

    Returns:
        object: 掩码后的映射（契约集合类保持原类型，内置字典仍为内置字典）。
    """
    if depth >= _MAX_MASK_DEPTH or not isinstance(data, Mapping):
        return data
    result = ConcurrentStableDict[str, object]()
    mapping = cast("ConcurrentStableDict[object, object]", data)
    for key, value in mapping.items():
        name = key if isinstance(key, str) else str(key)
        result.set(name, _mask_value(masked, name, value, masker, depth))
    if isinstance(data, ConcurrentStableDict):
        return result
    return {key: item for key, item in result.items()}


def _mask_sequence(
    masked: ConcurrentStableDict[str, str],
    field: str,
    value: Iterable[object],
    masker: _MaskerProtocol,
    depth: int,
) -> object:
    """按同一字段上下文逐元素掩码序列（保持原容器类型）。

    Args:
        masked: 归一化后的字段 → 策略映射。
        field: 元素所属字段名（声明为敏感字段时逐元素掩码）。
        value: 待掩码序列（列表 / 元组 / 集合 / 基座集合类）。
        masker: 当前掩码器。
        depth: 当前嵌套深度。

    Returns:
        object: 掩码后的序列。
    """
    items = [_mask_value(masked, field, item, masker, depth + 1) for item in value]
    if isinstance(value, ConcurrentStableList):
        return ConcurrentStableList(items)
    if isinstance(value, ConcurrentStableSet):
        return ConcurrentStableSet(items)
    if isinstance(value, tuple):
        return tuple(items)
    if isinstance(value, frozenset):
        return frozenset(items)
    if isinstance(value, set):
        return set(items)
    return items


def _mask_value(
    masked: ConcurrentStableDict[str, str], field: str, value: object, masker: _MaskerProtocol, depth: int
) -> object:
    """掩码单个值：映射递归、序列逐元素、其余按声明字段掩码（未声明原样）。

    Args:
        masked: 归一化后的字段 → 策略映射。
        field: 字段名（序列元素沿用所属字段名）。
        value: 待掩码值。
        masker: 当前掩码器。
        depth: 当前嵌套深度。

    Returns:
        object: 掩码后的值。
    """
    if depth >= _MAX_MASK_DEPTH:
        return value
    if isinstance(value, Mapping):
        return _mask_mapping(masked, cast("ConcurrentStableDict[object, object]", value), masker, depth + 1)
    if isinstance(value, (list, tuple, set, frozenset, BaseCollection)):
        return _mask_sequence(masked, field, cast("Iterable[object]", value), masker, depth)
    strategy = masked.get(field)
    if strategy is None:
        return value
    return masker.mask(field, value, strategy=strategy)


def _apply_masking(masked_fields: MaskedFields, data: object) -> object:
    """按当前掩码器掩码敏感字段（含嵌套模型与列表）。

    未注入掩码器（`current_masker` 为 None）/ 无敏感字段声明时**原样返回**（未接入脱敏的行为与既有一致）。

    Args:
        masked_fields: 敏感字段声明（映射或集合）。
        data: 序列化结果。

    Returns:
        object: 掩码后的结果。
    """
    masker = get_current_masker()
    if masker is None or not masked_fields:
        return data
    masked = _normalize_masked_fields(masked_fields)
    if not masked:
        return data
    return _mask_value(masked, "", data, masker, 0)


class BaseSchema(BaseModel, BaseDataContract):
    """Pydantic 模型基类：请求/响应模型统一继承。

    - from_attributes：允许 ORM/实体对象直接校验（响应模型使用）
    - str_strip_whitespace：字符串字段自动去除首尾空白
    - 序列化：继承 `BaseObject`（声明字段优先）；统一把 `id` / `*_id` 按字符串输出（JS 安全整数）
    - 敏感字段：类属性 `masked_fields`（映射或集合）声明的字段在序列化时经当前掩码器**递归掩码**
      （含嵌套模型与列表；未注入掩码器时直通）
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, extra="forbid")

    masked_fields: ClassVar[MaskedFields] = ConcurrentStableSet[str]()
    """敏感字段声明（默认空集＝不掩码）。

    映射写法（`{"mobile": "phone"}`）显式指定字段策略；集合写法（`{"phone", "email"}`）以字段名同名
    内置策略掩码、非内置字段名兜底全掩码。序列化时经当前掩码器递归掩码（含嵌套模型与列表）；
    未注入掩码器时直通。
    """

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

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """JSON Schema 生成：序列化模式按字段口径输出，并把 ID 字段类型对齐实际输出。

        本基类的模型序列化器（`_serialize_ids`，`@model_serializer(mode="wrap")`）在**序列化模式**下
        会把模型 schema 塌陷为空对象（其 `return_schema` 为 `any`），使**响应契约丢失全部字段信息**
        （前端生成类型退化为 `unknown`）。此处仅在序列化模式剥离该序列化器、回落到字段口径，再按
        `stringify_ids` 的**同一判定**（`is_id_key`）把 `id` / `*_id` 标为字符串。

        **校验模式 schema 与运行时序列化行为均不变**——请求体契约、`model_dump()` /
        `model_dump_json()` 输出与敏感字段掩码照旧。

        Args:
            schema: 本模型 core schema。
            handler: JSON Schema 处理器（含生成模式）。

        Returns:
            JsonSchemaValue: JSON Schema。
        """
        if getattr(handler, "mode", None) != "serialization":
            return handler(schema)
        fields = cast("Mapping[str, object]", schema)
        trimmed = {key: value for key, value in fields.items() if key != "serialization"}
        return _stringify_id_properties(handler(cast("CoreSchema", trimmed)))
