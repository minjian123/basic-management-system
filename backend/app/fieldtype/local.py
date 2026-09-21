"""字段类型注册表真实实现（`app/fieldtype/local.py`）：内建字段类型 + 校验 / 渲染元数据 / 列类型映射。

- `LocalFieldTypeRegistry`（插件名 `local`）：公共注册实现 + 内建字段类型注册（含 `dict` / `dict_multi`）。
- `SimpleFieldType`：数据驱动的字段类型提供者；`dict` / `dict_multi` 的 `render_metadata` 与前端
  `FIELD_WIDGET_MAP`（`dict` → `dict-select` / `dict_multi` → `dict-multi`）对齐，输出 `widget` 与 `multiple`。
- 自建字段白名单（`EXT_FIELD_TYPES`）仍归表单定制；本实现只负责类型级校验与列类型映射。
"""

from collections.abc import Mapping
from typing import cast

from app.fieldtype.base import BaseFieldType, BaseFieldTypeRegistry

__all__ = ["LocalFieldTypeRegistry", "SimpleFieldType"]

_KIND_TEXT = "text"
_KIND_NUMBER = "number"
_KIND_BOOL = "bool"
_KIND_STRING = "string"
_KIND_STRING_LIST = "string_list"


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

    def validate(self, value: object, *, options: Mapping[str, object] | None = None) -> tuple[str, ...]:
        """校验字段值（类型级；空值放行，必填由字段规则承载）。

        Args:
            value: 字段值。
            options: 字段选项（本实现忽略）。

        Returns:
            tuple[str, ...]: 违规原因元组（空元组通过）。
        """
        if value is None or value == "":
            return ()
        if self._kind == _KIND_STRING:
            return () if isinstance(value, str) else (f"{self._key} 需要字符串值",)
        if self._kind == _KIND_TEXT:
            return () if isinstance(value, str) else (f"{self._key} 需要文本值",)
        if self._kind == _KIND_NUMBER:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return (f"{self._key} 需要数值",)
            return ()
        if self._kind == _KIND_BOOL:
            return () if isinstance(value, bool) else (f"{self._key} 需要布尔值",)
        if self._kind == _KIND_STRING_LIST:
            if not isinstance(value, list):
                return (f"{self._key} 需要字符串数组",)
            items = cast("list[object]", value)
            if any(not isinstance(item, str) for item in items):
                return (f"{self._key} 数组元素需为字符串",)
            return ()
        return ()

    def render_metadata(self) -> Mapping[str, object]:
        """渲染元数据（控件语义键 / 是否多值）。

        Returns:
            Mapping[str, object]: 渲染元数据。
        """
        metadata: dict[str, object] = {"widget": self._widget, "multiple": self._multiple}
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


def builtin_field_types() -> tuple[SimpleFieldType, ...]:
    """内建字段类型清单（与前端字段类型 / 语义键口径对齐）。

    Returns:
        tuple[SimpleFieldType, ...]: 字段类型提供者元组。
    """
    return (
        SimpleFieldType(key="text", widget="text", kind=_KIND_TEXT, column_type="varchar(255)"),
        SimpleFieldType(key="longtext", widget="textarea", kind=_KIND_TEXT, column_type="text"),
        SimpleFieldType(key="number", widget="number", kind=_KIND_NUMBER, column_type="int"),
        SimpleFieldType(key="datetime", widget="datetime", kind=_KIND_STRING, column_type="datetime"),
        SimpleFieldType(key="select", widget="select", kind=_KIND_STRING, column_type="varchar(64)"),
        SimpleFieldType(
            key="multi_select", widget="multi-select", kind=_KIND_STRING_LIST, multiple=True, column_type="text"
        ),
        SimpleFieldType(key="switch", widget="switch", kind=_KIND_BOOL, column_type="smallint"),
        SimpleFieldType(key="file", widget="file", kind=_KIND_STRING, column_type="text"),
        SimpleFieldType(key="dict", widget="dict-select", kind=_KIND_STRING, column_type="varchar(64)"),
        SimpleFieldType(
            key="dict_multi", widget="dict-multi", kind=_KIND_STRING_LIST, multiple=True, column_type="text"
        ),
    )
