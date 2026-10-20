"""通用数据接口三层（02_10）：基础通用 → 表单 / 字典（后两者继承基础、只声明差异）。

口径（2026-10-11 用户拍板，需求 02-57）：把数据接口抽为**三层**，**所有表**的通用取数能力收敛在
**基础通用数据接口**，表单 / 字典只声明各自差异：

- `BaseGenericDataSource`（**基础通用数据接口**，针对**所有表**）：取数 / 版本比对 / 缓存 / 批量等通用部分。
- `BaseFormDataSource`（**表单通用数据接口**）：业务表单数据（**不含字典**），按 `form_key` 取数。
- `BaseDictDataSource`（**字典通用数据接口**）：标准字典系统字段 `code` / `name` / `parent_id` /
  `sort` / `status`，可直用 / 可继承实现类见 `bms_core/dict/table.py::DictTableDataSource`。

通用条目 `DataSourceItem` 定义于本层（泛化层**不依赖字典层**，避免 `datasource ⇄ dict` 循环）；
字典对外契约 `DictItem`（`bms_core/dict/base.py`）由统一出口在取数时映射。

**落点口径**：提供者层为**框架对象**（`BaseFrameworkObject`）——由数据所有者域实现、经统一出口的
**提供者注册表**（`bms_core/dict/outlet.py::register_data_source`）注入，**不占用插件端口键**；
插件端口仍是出口取数契约 `BaseDataSource`（`bms_core/dict/base.py`，`plugin_key = "data_source"`）。
"""

from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    BaseSchema,
)

__all__ = [
    "DATA_SOURCE_CACHE_DOMAIN",
    "BaseDictDataSource",
    "BaseFormDataSource",
    "BaseGenericDataSource",
    "DataSourceItem",
]

DATA_SOURCE_CACHE_DOMAIN = "data_source"
"""通用数据源缓存域简称（子类可覆写；字典提供者沿用字典域 `dict`）。"""


class DataSourceItem(BaseSchema):
    """通用数据条目（提供者层出入形状；表单等动态列经 `extra` 承载）。

    字典条目的对外契约形状为 `bms_core/dict/base.py::DictItem`（字段同形）；出口负责映射。
    """

    id: int = Field(default=0, description="条目主键（雪花 ID，JSON 以字符串输出）")
    value: str = Field(description="条目值（标识）")
    label: str = Field(description="条目标签（按 locale）")
    code: str = Field(default="", description="条目编码")
    parent_id: int | None = Field(default=None, description="上级条目 ID（自引用 id；None＝顶层）")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态（enabled / disabled）")
    color: str | None = Field(default=None, description="语义色（可空）")
    extra: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="动态扩展列（表单等非标准字段载体）"
    )


class BaseGenericDataSource(BaseFrameworkObject, ABC):
    """基础通用数据接口：所有表通用（取数 / 版本比对 / 缓存 / 批量）。

    提供者只负责**加载某数据源的全部启用行**；版本比对 / 缓存 / 关键字 / 级联 / 按值子集 / 截断
    由统一出口（`bms_core/dict/outlet.py`）统一承载。提供者由数据所有者域实现。
    """

    @property
    @abstractmethod
    def data_source(self) -> str:
        """数据出口标识（与登记项 `DataSourceRecord.data_source` 对齐）。"""

    @property
    def cache_domain(self) -> str:
        """缓存域简称（缺省 `data_source`；字典提供者沿用字典域）。

        Returns:
            str: 缓存域简称。
        """
        return DATA_SOURCE_CACHE_DOMAIN

    @abstractmethod
    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """加载某数据源的全部启用行（供出口做过滤 / 截断 / 缓存）。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            tuple[DataSourceItem, ...]: 启用行（未登记 / 未支持标识返回空元组）。
        """

    async def version(self, data_source_key: str) -> int:
        """版本比对（缺省 `0`＝不参与版本比对；子类可覆写为真实版本号）。

        Args:
            data_source_key: 数据源标识。

        Returns:
            int: 版本号。
        """
        return 0

    async def batch(
        self, data_source_keys: ConcurrentStableList[str], locale: str
    ) -> ConcurrentStableDict[str, ConcurrentStableList[DataSourceItem]]:
        """批量取数（缺省逐键 `load` 合并；子类可覆写为一次批量加载）。

        Args:
            data_source_keys: 数据源标识序列。
            locale: 语言。

        Returns:
            ConcurrentStableDict[str, tuple[DataSourceItem, ...]]: 按标识的启用行。
        """
        result: ConcurrentStableDict[str, ConcurrentStableList[DataSourceItem]] = ConcurrentStableDict()
        for data_source_key in data_source_keys:
            result.set(data_source_key, await self.load(data_source_key, locale))
        return result


class BaseFormDataSource(BaseGenericDataSource, ABC):
    """表单通用数据接口：业务表单数据（**不含字典**）；取数 / 版本比对 / 缓存 / 批量继承基础。"""

    @property
    @abstractmethod
    def form_key(self) -> str:
        """表单标识（与 `FormRecord.form_key` 对齐；业务表单数据按表单标识取数）。"""


class BaseDictDataSource(BaseGenericDataSource, ABC):
    """字典通用数据接口：标准字典系统字段（`code` / `name` / `parent_id` / `sort` / `status`）。

    字典条目语义：`value`＝标识、`label`＝名称（按 locale 本地化）；可直用 / 可继承实现类见
    `bms_core/dict/table.py::DictTableDataSource`。
    """

    DICT_FIELDS: ClassVar[ConcurrentStableList[str]] = ConcurrentStableList(
        ("code", "name", "parent_id", "sort", "status")
    )
    """标准字典系统字段（可直用实现类按此映射）。"""
