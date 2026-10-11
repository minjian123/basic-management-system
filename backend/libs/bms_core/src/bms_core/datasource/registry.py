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
from dataclasses import dataclass
from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject

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
        data_source: 数据出口标识（统一出口按此路由到具体实现，如 `platform` / `mdm.org.dept`）。
        kind: 类型（`dict` 字典 / `form` 表单，预留其它）。
        origin: 来源（`platform` 平台内建 / `product` 产品提供）。
        product_key: 产品标识（`origin=product` 时必填，如 `mdm` / `biz`）。
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
    allowlist: tuple[str, ...] = ()
    cascade: bool = False
    strategies: tuple[str, ...] = (DataSourceStrategy.SELECT.value,)
    status: str = DataSourceStatus.ENABLED.value


DATA_SOURCE_CATALOG: tuple[DataSourceRecord, ...] = (
    # 平台内建：bms 侧全部字典表（与 `bms_core/registry/forms.py::FORM_CATALOG` 的 `form_key` 一一对应；
    # 数据本体在平台实体表，经平台统一出口取数）
    DataSourceRecord(data_source_key="module", name="业务模块注册", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="product", name="产品档案", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="business", name="业务码", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="action", name="动作码", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="role", name="角色", data_source="platform", allowlist=("code", "label")),
    DataSourceRecord(data_source_key="user", name="用户", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="config", name="系统参数", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="tenant", name="租户", data_source="platform", allowlist=("code",)),
    DataSourceRecord(
        data_source_key="identity_provider", name="外部 IdP 配置", data_source="platform", allowlist=("code",)
    ),
    DataSourceRecord(data_source_key="client", name="第三方应用", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="task", name="定时任务", data_source="platform", allowlist=("code",)),
    DataSourceRecord(data_source_key="icon", name="自定义图标", data_source="platform", allowlist=("code",)),
    # 跨项目示例（数据本体在 mdm 产品；前端经网关直取产品命名空间）
    DataSourceRecord(
        data_source_key="org_dept",
        name="部门",
        data_source="mdm.org.dept",
        origin=DataSourceOrigin.PRODUCT.value,
        product_key="mdm",
        path="/data-source/dept-tree",
        allowlist=("code", "label"),
        cascade=True,
        strategies=(DataSourceStrategy.SELECT.value, DataSourceStrategy.REGION.value, DataSourceStrategy.MATCH.value),
    ),
    DataSourceRecord(
        data_source_key="org_post",
        name="岗位",
        data_source="mdm.org.post",
        origin=DataSourceOrigin.PRODUCT.value,
        product_key="mdm",
        path="/data-source/posts",
        allowlist=("code", "label"),
        strategies=(DataSourceStrategy.SELECT.value, DataSourceStrategy.MATCH.value),
    ),
)
"""bms 侧构建期清单（平台内建字典表 + 跨项目示例；其余数据源随各自域以注入方式回补）。"""


def merge_data_source_records(
    builtin: tuple[DataSourceRecord, ...] = DATA_SOURCE_CATALOG,
    injected: tuple[DataSourceRecord, ...] = (),
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
            records: 登记记录（插入序）；默认全量构建期清单 `DATA_SOURCE_CATALOG`
                （应用装配期应传入 `merge_data_source_records()` 结果）。
        """
        self._records: ConcurrentStableList[DataSourceRecord] = (
            ConcurrentStableList(DATA_SOURCE_CATALOG) if records is None else ConcurrentStableList(records)
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
