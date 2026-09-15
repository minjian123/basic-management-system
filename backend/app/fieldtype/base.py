"""表单字段类型能力域：字段类型提供者与注册表契约（真实字段类型与四库映射随表单定制阶段回补）。

- `COLUMN_TYPE_DIALECTS` / `NULL_COLUMN_TYPE`：方言清单（四库）与占位列类型。
- `BaseFieldType`：字段类型提供者契约（抽象 `key` + 同步 `validate` / `render_metadata` / `column_type`）。
- `BaseFieldTypeRegistry`：能力域中间层契约（`key = "field_type_registry"`）——抽象 `register` / `get` / `keys`
  + **具体聚合模板** `validate` / `column_type`（解析字段类型 → 委托；未命中抛 `NotFoundError`）。
- `get_field_type_registry`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：本域负责**自建字段类型**级校验与列类型映射；`BaseModel` 四库映射负责公共字段、动态 DDL（`ext_*` 物理列）
执行归上层（表单定制阶段 + 数据访问与分片）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, resolve_plugin
from app.core.provider import BaseProvider, BaseProviderRegistry

__all__ = [
    "COLUMN_TYPE_DIALECTS",
    "NULL_COLUMN_TYPE",
    "BaseFieldType",
    "BaseFieldTypeRegistry",
    "get_field_type_registry",
]

COLUMN_TYPE_DIALECTS: tuple[str, ...] = ("mysql", "postgresql", "dm", "sqlite")
"""方言清单（四库）；占位期仅登记不校验。"""

NULL_COLUMN_TYPE = "varchar(255)"
"""占位列类型（NullFieldTypeRegistry.column_type 固定返回）。"""


class BaseFieldType(BaseProvider, ABC):
    """字段类型提供者契约：校验 / 渲染元数据 / 类型映射。"""

    @abstractmethod
    def validate(self, value: object, *, options: Mapping[str, object] | None = None) -> tuple[str, ...]:
        """校验字段值。

        Args:
            value: 字段值。
            options: 字段选项（可选，如范围 / 正则 / 选项集）。

        Returns:
            tuple[str, ...]: 违规原因元组（空元组通过）。
        """

    @abstractmethod
    def render_metadata(self) -> Mapping[str, object]:
        """渲染元数据（组件名 / 属性）。

        Returns:
            Mapping[str, object]: 渲染元数据。
        """

    @abstractmethod
    def column_type(self, dialect: str) -> str:
        """按方言返回物理列类型。

        Args:
            dialect: 方言（取值见 `COLUMN_TYPE_DIALECTS`）。

        Returns:
            str: 物理列类型。
        """


class BaseFieldTypeRegistry(BaseProviderRegistry[BaseFieldType], ABC):
    """字段类型注册表契约：注册 / 解析 / 清单（公共实现继承）+ 校验与类型映射聚合（模板留域）。"""

    key: str = "field_type_registry"
    plugin_key: str = "field_type_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def validate(
        self, field_type: str, value: object, *, options: Mapping[str, object] | None = None
    ) -> tuple[str, ...]:
        """聚合校验（模板方法：解析字段类型 → 委托）。

        Args:
            field_type: 字段类型标识。
            value: 字段值。
            options: 字段选项（可选）。

        Returns:
            tuple[str, ...]: 违规原因元组。

        Raises:
            NotFoundError: 字段类型不存在（10002 / 404，全局处理器统一转响应）。
        """
        provider = self.get(field_type)
        if provider is None:
            raise NotFoundError(f"字段类型不存在：{field_type}")
        return provider.validate(value, options=options)

    def column_type(self, field_type: str, dialect: str) -> str:
        """聚合类型映射（模板方法：解析字段类型 → 委托）。

        Args:
            field_type: 字段类型标识。
            dialect: 方言（取值见 `COLUMN_TYPE_DIALECTS`）。

        Returns:
            str: 物理列类型。

        Raises:
            NotFoundError: 字段类型不存在（10002 / 404）。
        """
        provider = self.get(field_type)
        if provider is None:
            raise NotFoundError(f"字段类型不存在：{field_type}")
        return provider.column_type(dialect)


def get_field_type_registry(request: Request) -> BaseFieldTypeRegistry:
    """取应用级字段类型注册表（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseFieldTypeRegistry: 应用装配的注册表实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseFieldTypeRegistry",
        resolve_plugin(
            "field_type_registry",
            settings.field_type_registry.provider,
            expected_version=BaseFieldTypeRegistry.contract_version,
        ),
    )
