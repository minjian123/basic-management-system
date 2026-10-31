"""统一数据源注册：统一注册表 + 构建期清单（02_10 泛化，源自 02_09 字典数据源登记）。

口径（2026-10-11 用户拍板，需求 02-57）：「**字典**」只是**数据源的一类**——注册的真正对象是
「**数据从哪来**」（一个数据源可被**多个界面 / 表单**复用），故把「字典数据源登记」泛化为
**统一数据源注册**（按 `kind` 区分：`dict` 字典 / `form` 表单，预留其它）。本模块登记「各数据源
对外暴露的清单」，作为**数据权限左列**与**通用页面路由 / 字段取数**的统一来源。

- **登记项**：`DataSourceRecord` = （`data_source_key` 数据源标识 / `name` 名称 / `kind` 类型 /
  `data_source` 数据出口 / `origin` 来源 / `product_key` 产品标识 / `path` 产品取数路径 /
  `allowlist` 字段白名单 / `cascade` 是否级联 / `strategies` 可用策略集合 / `status` 状态）。
  数据源标识为**业务码字符串**（如 `role` / `sys_user` / `org_dept` / `region`）。
- **单一来源与注入**（口径同服务目录 `ModuleRegistry`、`form_key` 清单 `FormRegistry`）：
  `DATA_SOURCE_CATALOG` 是 bms 侧**构建期清单**；各项目在**构建期注入**自身登记项；应用工厂经
  `merge_data_source_records()` 拼接清单与注入记录，构造入参进入 `DataSourceRegistry`
  （**无进程级注册表、不改常量**，运行期只读）。
- **离线校验**：`DataSourceRegistry.validate()`（标识格式与唯一、名称 / 数据出口非空、`kind` 合法、
  白名单字段名格式、策略取值合法、`origin=product` 须带 `product_key`）。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.datasource.keys import DataSourceKey

__all__ = [
    "DATA_SOURCE_CATALOG",
    "DATA_SOURCE_KEY_PATTERN",
    "DataSourceKind",
    "DataSourceOrigin",
    "DataSourceRecord",
    "DataSourceRegistry",
    "DataSourceStatus",
    "DataSourceStrategy",
    "merge_data_source_records",
]

_DATA_SOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")

DATA_SOURCE_KEY_PATTERN = "^[a-z][a-z0-9_]*$"
"""数据源标识 / 白名单字段名格式（业务码字符串）。"""


class DataSourceStatus(StrEnum):
    """数据源登记项状态。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


class DataSourceKind(StrEnum):
    """数据源类型（数据形态；预留其它）。"""

    DICT = "dict"
    FORM = "form"


class DataSourceOrigin(StrEnum):
    """数据源来源（数据所有者类别）。"""

    PLATFORM = "platform"
    PRODUCT = "product"


class DataSourceStrategy(StrEnum):
    """数据权限可用策略（供数据权限左列渲染，只选不编）。"""

    SELECT = "select"
    REGION = "region"
    MATCH = "match"
    EXTENSION = "extension"


@dataclass(frozen=True)
class DataSourceRecord(BaseValueObject):
    """数据源登记记录（构建期清单 / 注入清单的不可变条目）。

    Attributes:
        data_source_key: 数据源标识（业务码字符串，如 `role` / `user` / `org_dept`），全局唯一。
        name: 名称（数据权限左列 / 通用页面显示；多语言随所有者域下发）。
        data_source: 数据出口标识（统一出口按此路由到具体实现，如 `platform` / `{产品}.{域}.{表}`）。
        kind: 类型（`dict` 字典 / `form` 表单，预留其它）。
        origin: 来源（`platform` 平台内建 / `product` 产品提供）。
        product_key: 产品标识（`origin=product` 时必填，取产品键）。
        path: 产品取数路径（`origin=product` 时前端经网关直取用，如 `/data-source/dept-tree`）。
        allowlist: 可用于数据权限的字段白名单（`match` 策略可匹配字段）。
        cascade: 是否级联（有无上级字段，供级联取数）。
        strategies: 可用策略集合（`select` / `region` / `match` / `extension`）。
        status: 状态（`enabled` / `disabled`）。
    """

    data_source_key: str
    name: str
    data_source: str
    kind: str = DataSourceKind.DICT.value
    origin: str = DataSourceOrigin.PLATFORM.value
    product_key: str | None = None
    path: str | None = None
    allowlist: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList[str]())
    cascade: bool = False
    strategies: ConcurrentStableFrozenList[str] = field(
        default_factory=lambda: ConcurrentStableFrozenList[str]((DataSourceStrategy.SELECT.value,))
    )
    status: str = DataSourceStatus.ENABLED.value


DATA_SOURCE_CATALOG: ConcurrentStableList[DataSourceRecord] = ConcurrentStableFrozenList(
    (
        # 平台内建：bms 侧全部字典表（与 `bms_core/registry/forms.py::FORM_CATALOG` 的 `form_key` 一一对应；
        # 数据本体在平台实体表，经平台统一出口取数）
        DataSourceRecord(
            data_source_key=DataSourceKey.MODULE.value,
            name="业务模块注册",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.PRODUCT.value,
            name="产品档案",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.BUSINESS.value,
            name="业务码",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.ACTION.value,
            name="动作码",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.ROLE.value,
            name="角色",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code", "label")),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.USER.value,
            name="用户",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.CONFIG.value,
            name="系统参数",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.TENANT.value,
            name="租户",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.IDENTITY_PROVIDER.value,
            name="外部 IdP 配置",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.CLIENT.value,
            name="第三方应用",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.TASK.value,
            name="定时任务",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
        DataSourceRecord(
            data_source_key=DataSourceKey.ICON.value,
            name="自定义图标",
            data_source="platform",
            kind=DataSourceKind.DICT.value,
            allowlist=ConcurrentStableFrozenList(("code",)),
        ),
    )
)
"""平台内建数据源清单（**只含平台自有字典表**；产品数据源由产品仓自持清单装载）。

`kind` 一律**逐条显式声明**（2026-10-13，任务 `08_01`）——不再依赖数据类默认值；
取值保持既有不变（本清单均为字典表）。

**产品条目不入本常量**：产品在 `deploy/registry/<产品>.toml` 的 `data_sources` 段声明，
经 `register_data_source_records()` 装载（装配期 / 离线网关生成），避免产品名与取数路径写进基座源码。
"""

_INJECTED_DATA_SOURCE_RECORDS: ConcurrentStableDict[str, DataSourceRecord] = ConcurrentStableDict()
"""产品清单装载的数据源条目（`data_source_key` → 记录）。"""


def register_data_source_records(records: Iterable[DataSourceRecord]) -> None:
    """装载产品数据源条目（幂等：同 `data_source_key` 同值覆盖、异值即拒）。

    Args:
        records: 数据源登记记录（来自产品自持清单）。

    Raises:
        CatalogError: 与已装载记录同键异值（fail-closed）。
    """
    from bms_core.core.exceptions import CatalogError

    for record in records:
        existing = _INJECTED_DATA_SOURCE_RECORDS.get(record.data_source_key)
        if existing is not None and existing != record:
            raise CatalogError(f"数据源条目同键异值：{record.data_source_key!r}（已装载 {existing!r}，新 {record!r}）")
        _INJECTED_DATA_SOURCE_RECORDS.set(record.data_source_key, record)


def reset_data_source_records() -> None:
    """清空已装载的产品数据源条目（测试隔离用；生产路径不调用）。"""
    _INJECTED_DATA_SOURCE_RECORDS.clear()


def data_source_records_view() -> ConcurrentStableList[DataSourceRecord]:
    """数据源登记**合并视图**（平台内建 + 已装载产品条目，插入序）。

    Returns:
        ConcurrentStableList[DataSourceRecord]: 数据源登记记录。
    """
    return merge_data_source_records(DATA_SOURCE_CATALOG, ConcurrentStableList(_INJECTED_DATA_SOURCE_RECORDS.values()))


def merge_data_source_records(
    builtin: ConcurrentStableList[DataSourceRecord] = DATA_SOURCE_CATALOG,
    injected: ConcurrentStableList[DataSourceRecord] = ConcurrentStableList(()),  # noqa: B008
) -> ConcurrentStableList[DataSourceRecord]:
    """拼接构建期清单与项目注入记录（应用装配期视图的构造入口）。

    Args:
        builtin: 构建期清单（默认 `DATA_SOURCE_CATALOG`）。
        injected: 本部署注入的记录（各项目构建期声明；默认空）。

    Returns:
        ConcurrentStableList[DataSourceRecord]: 合并后的登记记录（插入序：清单在前、注入在后）。
    """
    merged: ConcurrentStableList[DataSourceRecord] = ConcurrentStableList(builtin)
    merged.update(injected)
    return merged


class DataSourceRegistry(BaseFrameworkObject):
    """统一数据源登记：离线校验与清单查询（**应用装配视图**）。"""

    def __init__(self, records: ConcurrentStableList[DataSourceRecord] | None = None) -> None:
        """初始化。

        Args:
            records: 登记记录（插入序）；默认**合并视图** `data_source_records_view()`
                （平台内建 + 已装载产品条目）。
        """
        self._records: ConcurrentStableList[DataSourceRecord] = (
            data_source_records_view() if records is None else ConcurrentStableList(records)
        )

    def catalog_records(self) -> ConcurrentStableList[DataSourceRecord]:
        """返回全量登记记录副本（插入序）。

        Returns:
            ConcurrentStableList[DataSourceRecord]: 登记记录。
        """
        return ConcurrentStableList(self._records)

    def keys(self) -> ConcurrentStableSet[str]:
        """返回全部数据源标识集合（去重，插入序）。

        Returns:
            ConcurrentStableSet[str]: 数据源标识集合。
        """
        return ConcurrentStableSet(record.data_source_key for record in self._records)

    def get(self, data_source_key: str) -> DataSourceRecord | None:
        """按数据源标识取登记记录。

        Args:
            data_source_key: 数据源标识。

        Returns:
            DataSourceRecord | None: 命中记录；未登记返回 `None`。
        """
        for record in self._records:
            if record.data_source_key == data_source_key:
                return record
        return None

    def validate(self) -> ConcurrentStableList[str]:
        """离线校验：标识格式与唯一、名称 / 数据出口非空、类型 / 来源 / 策略合法、产品标识、白名单字段名。

        Returns:
            ConcurrentStableList[str]: 问题描述列表（空列表 = 通过）。
        """
        issues: ConcurrentStableList[str] = ConcurrentStableList()
        seen: ConcurrentStableSet[str] = ConcurrentStableSet()
        valid_kinds = {item.value for item in DataSourceKind}
        valid_origins = {item.value for item in DataSourceOrigin}
        valid_strategies = {item.value for item in DataSourceStrategy}
        for record in self._records:
            if not _DATA_SOURCE_KEY_RE.match(record.data_source_key):
                issues.add(f"数据源标识格式非法：{record.data_source_key!r}（须 {DATA_SOURCE_KEY_PATTERN}）")
            if record.data_source_key in seen:
                issues.add(f"数据源标识重复：{record.data_source_key!r}")
            seen.add(record.data_source_key)
            if not record.name:
                issues.add(f"数据源名称缺失：{record.data_source_key!r}")
            if not record.data_source:
                issues.add(f"数据出口标识缺失：{record.data_source_key!r}")
            if record.kind not in valid_kinds:
                issues.add(f"类型取值非法：{record.data_source_key!r} → {record.kind!r}")
            if record.origin not in valid_origins:
                issues.add(f"来源取值非法：{record.data_source_key!r} → {record.origin!r}")
            if record.origin == DataSourceOrigin.PRODUCT.value and not record.product_key:
                issues.add(f"产品来源缺产品标识：{record.data_source_key!r}")
            for field_name in record.allowlist:
                if not _FIELD_RE.match(field_name):
                    issues.add(f"白名单字段名格式非法：{record.data_source_key!r} → {field_name!r}")
            for strategy in record.strategies:
                if strategy not in valid_strategies:
                    issues.add(f"策略取值非法：{record.data_source_key!r} → {strategy!r}")
        return issues
