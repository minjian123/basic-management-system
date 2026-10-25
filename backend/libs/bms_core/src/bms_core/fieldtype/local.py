"""字段类型注册表真实实现（`app/fieldtype/local.py`）：内建字段类型 + 校验 / 渲染元数据 / 列类型映射。

- `LocalFieldTypeRegistry`（插件名 `local`）：公共注册实现 + 内建字段类型注册（含 `dict` / `dict_multi`）。
- `SimpleFieldType`：数据驱动的字段类型提供者；`dict` / `dict_multi` 的 `render_metadata` 与前端
  `FIELD_WIDGET_MAP`（`dict` → `dict_select` / `dict_multi` → `dict_multi`）对齐，输出 `widget` 与 `multiple`。
- **枚举字段与字典字段分家（2026-10-21 任务 02-14）**：`option` / `option_multi` 只接注册表选项集
  （值 = 常量字符串），默认形态 `radio` / `checkbox`；`dict` / `dict_multi` 只接字典，值 = 条目 `id`
  （`dict` 列 `bigint`，`dict_multi` 列 `text` 承载 id 的 JSON 数组，应用层解析）。旧名
  `select` / `multi_select` **已废弃且不保留别名**。
- 下拉形态的语义键登记为 `OPTION_DROPDOWN_WIDGET` / `OPTION_MULTI_DROPDOWN_WIDGET`（供字段属性层与前端
  `06_09` 使用）；内建类型默认不产出下拉形态。
- 自建字段白名单（`EXT_FIELD_TYPES`）仍归表单定制；本实现只负责类型级校验与列类型映射。
"""

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.fieldtype.base import BaseFieldType, BaseFieldTypeRegistry

__all__ = [
    "OPTION_DROPDOWN_WIDGET",
    "OPTION_MULTI_DROPDOWN_WIDGET",
    "LocalFieldTypeRegistry",
    "SimpleFieldType",
]

_KIND_TEXT = "text"
_KIND_NUMBER = "number"
_KIND_BOOL = "bool"
_KIND_STRING = "string"
_KIND_STRING_LIST = "string_list"
_KIND_ID = "id"
_KIND_ID_LIST = "id_list"

OPTION_DROPDOWN_WIDGET = "dropdown"
"""枚举单选的下拉形态语义键（字段属性层 `widget` 取值；内建默认 `radio`，不产出）。"""

OPTION_MULTI_DROPDOWN_WIDGET = "dropdown-multi"
"""枚举多选的下拉形态语义键（字段属性层 `widget` 取值；内建默认 `checkbox`，不产出）。"""


class SimpleFieldType(BaseFieldType):
    """数据驱动的字段类型提供者（校验 / 渲染元数据 / 列类型）。"""

    def __init__(
        self,
        *,
        key: str,
        widget: str,
        kind: str = _KIND_TEXT,
        multiple: bool = False,
        column_type: str = "varchar(255)",
    ) -> None:
        """初始化。

        Args:
            key: 字段类型标识（如 `dict`）。
            widget: 控件语义键（与前端 `FIELD_WIDGET_MAP` 对齐）。
            kind: 校验类别（text / string / number / bool / string_list）。
            multiple: 是否多值。
            column_type: 物理列类型（四库同构口径）。
        """
        self._key = key
        self._widget = widget
        self._kind = kind
        self._multiple = multiple
        self._column_type = column_type

    @property
    def key(self) -> str:
        """字段类型标识。

        Returns:
            str: 类型键。
        """
        return self._key

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 类型说明。
        """
        return f"字段类型 {self._key}（{self._widget}）"

    def validate(
        self, value: object, *, options: ConcurrentStableDict[str, object] | None = None
    ) -> ConcurrentStableList[str]:
        """校验字段值（类型级；空值放行，必填由字段规则承载）。

        Args:
            value: 字段值。
            options: 字段选项（本实现忽略）。

        Returns:
            tuple[str, ...]: 违规原因元组（空元组通过）。
        """
        if value is None or value == "":
            return ConcurrentStableList(())
        if self._kind == _KIND_STRING:
            return (
                ConcurrentStableList(())
                if isinstance(value, str)
                else ConcurrentStableList((f"{self._key} 需要字符串值",))
            )
        if self._kind == _KIND_TEXT:
            return (
                ConcurrentStableList(())
                if isinstance(value, str)
                else ConcurrentStableList((f"{self._key} 需要文本值",))
            )
        if self._kind == _KIND_NUMBER:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return ConcurrentStableList((f"{self._key} 需要数值",))
            return ConcurrentStableList(())
        if self._kind == _KIND_BOOL:
            return (
                ConcurrentStableList(())
                if isinstance(value, bool)
                else ConcurrentStableList((f"{self._key} 需要布尔值",))
            )
        if self._kind == _KIND_STRING_LIST:
            if not isinstance(value, list):
                return ConcurrentStableList((f"{self._key} 需要字符串数组",))
            items = cast("list[object]", value)
            if any(not isinstance(item, str) for item in items):
                return ConcurrentStableList((f"{self._key} 数组元素需为字符串",))
            return ConcurrentStableList(())
        if self._kind == _KIND_ID:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                return ConcurrentStableList((f"{self._key} 需要正整数 id",))
            return ConcurrentStableList(())
        if self._kind == _KIND_ID_LIST:
            if not isinstance(value, list):
                return ConcurrentStableList((f"{self._key} 需要 id 数组",))
            ids = cast("list[object]", value)
            if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in ids):
                return ConcurrentStableList((f"{self._key} 数组元素需为正整数 id",))
            return ConcurrentStableList(())
        return ConcurrentStableList(())

    def render_metadata(self) -> ConcurrentStableDict[str, object]:
        """渲染元数据（控件语义键 / 是否多值）。

        Returns:
            ConcurrentStableDict[str, object]: 渲染元数据。
        """
        metadata: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"widget": self._widget, "multiple": self._multiple}
        )
        return metadata

    def column_type(self, dialect: str) -> str:
        """按方言返回物理列类型（四库同构口径；达梦差异随阶段二实测）。

        Args:
            dialect: 方言（取值见 `COLUMN_TYPE_DIALECTS`）。

        Returns:
            str: 物理列类型。
        """
        return self._column_type


class LocalFieldTypeRegistry(BaseFieldTypeRegistry):
    """真实字段类型注册表（插件名 `local`）：内建类型随构造注册。"""

    def __init__(self) -> None:
        """初始化并注册内建字段类型。"""
        super().__init__()
        for provider in builtin_field_types():
            self.register(provider)

    @classmethod
    def _provider_key(cls, provider: BaseFieldType) -> str:
        """注册项键：字段类型 `key`。

        Args:
            provider: 字段类型提供者。

        Returns:
            str: 字段类型标识。
        """
        return provider.key


def builtin_field_types() -> ConcurrentStableList[SimpleFieldType]:
    """内建字段类型清单（与前端字段类型 / 语义键口径对齐）。

    枚举字段（`option` / `option_multi`）默认形态为 `radio` / `checkbox`；字典字段（`dict` / `dict_multi`）
    绑定条目整数 `id`。旧名 `select` / `multi_select` 已废弃、不再注册。

    Returns:
        tuple[SimpleFieldType, ...]: 字段类型提供者元组。
    """
    return ConcurrentStableList(
        (
            SimpleFieldType(key="text", widget="text", kind=_KIND_TEXT, column_type="varchar(255)"),
            SimpleFieldType(key="longtext", widget="textarea", kind=_KIND_TEXT, column_type="text"),
            SimpleFieldType(key="number", widget="number", kind=_KIND_NUMBER, column_type="int"),
            SimpleFieldType(key="datetime", widget="datetime", kind=_KIND_STRING, column_type="datetime"),
            SimpleFieldType(key="option", widget="radio", kind=_KIND_STRING, column_type="varchar(64)"),
            SimpleFieldType(
                key="option_multi", widget="checkbox", kind=_KIND_STRING_LIST, multiple=True, column_type="text"
            ),
            SimpleFieldType(key="switch", widget="switch", kind=_KIND_BOOL, column_type="smallint"),
            SimpleFieldType(key="file", widget="file", kind=_KIND_STRING, column_type="text"),
            SimpleFieldType(key="dict", widget="dict_select", kind=_KIND_ID, column_type="bigint"),
            SimpleFieldType(
                key="dict_multi", widget="dict_multi", kind=_KIND_ID_LIST, multiple=True, column_type="text"
            ),
        )
    )
