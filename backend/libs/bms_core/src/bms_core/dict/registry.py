"""字典数据源登记：统一注册表 + 构建期清单（02_09 口径返工）。

口径（2026-10-11 用户拍板，任务 02_09）：「**字典**」＝**基础数据 / 参考数据**——含主数据，但**不止
主数据**（bms 的用户 / 角色 / 租户、biz 的仓库储位等也都是字典）；AI 自行编造的「字典类型 / 字典
条目 / 字典属性」一套剔除，被剔处的取数改由**字典数据源登记 + 统一出口**承载。本模块登记「各数据
源对外暴露的字典清单」，作为**数据权限左列**与**字典字段取数**的统一来源。

- **登记项**：`DictRecord` = （`dict_key` 字典标识 / `name` 名称 / `origin` 来源 / `data_source` 数据出口 /
  `product_key` 产品标识（`origin=product` 时）/ `allowlist` 可用于数据权限的字段白名单 / `cascade`
  是否级联 / `strategies` 可用策略集合 / `status` 状态）。字典标识为**业务码字符串**（如 `sys_user` /
  `sys_role` / `sys_tenant` / `org_dept` / `region` / `wms_bin`）。
- **单一来源与注入**（口径同服务目录 `ModuleRegistry`、产品服务接入）：`DICT_CATALOG` 是 bms 侧**构建期
  清单**；各项目在**构建期注入**自身登记项；应用工厂经 `merge_dict_records()` 拼接清单与注入记录，
  构造入参进入 `DictRegistry`（**无进程级注册表、不改常量**，运行期只读）。
- **离线校验**：`DictRegistry.validate()`（标识格式与唯一、名称 / 数据出口非空、白名单字段名格式、
  策略取值合法、`origin=product` 须带 `product_key`）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject

__all__ = [
    "DICT_CATALOG",
    "DICT_KEY_PATTERN",
    "DictOrigin",
    "DictRecord",
    "DictRegistry",
    "DictStatus",
    "DictStrategy",
    "merge_dict_records",
]

_DICT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")

DICT_KEY_PATTERN = "^[a-z][a-z0-9_]*$"
"""字典标识 / 白名单字段名格式（业务码字符串）。"""


class DictStatus(StrEnum):
    """字典登记项状态。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


class DictOrigin(StrEnum):
    """字典来源（数据所有者类别）。"""

    PLATFORM = "platform"
    PRODUCT = "product"


class DictStrategy(StrEnum):
    """数据权限可用策略（供数据权限左列渲染，只选不编）。"""

    SELECT = "select"
    REGION = "region"
    MATCH = "match"
    EXTENSION = "extension"


@dataclass(frozen=True)
class DictRecord(BaseValueObject):
    """字典数据源登记记录（构建期清单 / 注入清单的不可变条目）。

    Attributes:
        dict_key: 字典标识（业务码字符串，如 `sys_user` / `org_dept` / `wms_bin`），全局唯一。
        name: 名称（数据权限左列 / 字典页显示；多语言随所有者域下发）。
        origin: 来源（`platform` 平台内建 / `product` 产品提供）。
        data_source: 数据出口标识（统一出口按此路由到具体实现）。
        product_key: 产品标识（`origin=product` 时必填，如 `mdm` / `biz`）。
        allowlist: 可用于数据权限的字段白名单（`match` 策略可匹配字段）。
        cascade: 是否级联（有无上级字段，供级联取数）。
        strategies: 可用策略集合（`select` / `region` / `match` / `extension`）。
        status: 状态（`enabled` / `disabled`）。
    """

    dict_key: str
    name: str
    data_source: str
    origin: str = DictOrigin.PLATFORM.value
    product_key: str | None = None
    allowlist: tuple[str, ...] = ()
    cascade: bool = False
    strategies: tuple[str, ...] = (DictStrategy.SELECT.value,)
    status: str = DictStatus.ENABLED.value


DICT_CATALOG: tuple[DictRecord, ...] = (
    # 平台内建示例（数据本体在平台实体表；provider 随本任务落地）
    DictRecord(
        dict_key="role",
        name="角色",
        origin=DictOrigin.PLATFORM.value,
        data_source="platform.role",
        allowlist=("code", "name"),
        strategies=(DictStrategy.SELECT.value, DictStrategy.MATCH.value),
    ),
    DictRecord(
        dict_key="tenant",
        name="租户",
        origin=DictOrigin.PLATFORM.value,
        data_source="platform.tenant",
        allowlist=("code", "name"),
        strategies=(DictStrategy.SELECT.value, DictStrategy.MATCH.value),
    ),
    # 跨项目示例（数据本体在 mdm 产品；provider 经产品命名空间寻址）
    DictRecord(
        dict_key="org_dept",
        name="部门",
        origin=DictOrigin.PRODUCT.value,
        product_key="mdm",
        data_source="mdm.org_dept",
        allowlist=("code", "name"),
        cascade=True,
        strategies=(DictStrategy.SELECT.value, DictStrategy.REGION.value, DictStrategy.MATCH.value),
    ),
    DictRecord(
        dict_key="org_post",
        name="岗位",
        origin=DictOrigin.PRODUCT.value,
        product_key="mdm",
        data_source="mdm.org_post",
        allowlist=("code", "name"),
        strategies=(DictStrategy.SELECT.value, DictStrategy.MATCH.value),
    ),
)
"""bms 侧构建期清单（平台内建 + 跨项目示例；其余字典随各自域以注入方式回补）。"""


def merge_dict_records(
    builtin: tuple[DictRecord, ...] = DICT_CATALOG,
    injected: tuple[DictRecord, ...] = (),
) -> ConcurrentStableList[DictRecord]:
    """拼接构建期清单与项目注入记录（应用装配期视图的构造入口）。

    Args:
        builtin: 构建期清单（默认 `DICT_CATALOG`）。
        injected: 本部署注入的记录（各项目构建期声明；默认空）。

    Returns:
        ConcurrentStableList[DictRecord]: 合并后的登记记录（插入序：清单在前、注入在后）。
    """
    merged: ConcurrentStableList[DictRecord] = ConcurrentStableList(builtin)
    merged.update(injected)
    return merged


class DictRegistry(BaseFrameworkObject):
    """字典数据源登记：离线校验与清单查询（**应用装配视图**）。"""

    def __init__(self, records: ConcurrentStableList[DictRecord] | None = None) -> None:
        """初始化。

        Args:
            records: 登记记录（插入序）；默认全量构建期清单 `DICT_CATALOG`
                （应用装配期应传入 `merge_dict_records()` 结果）。
        """
        self._records: ConcurrentStableList[DictRecord] = (
            ConcurrentStableList(DICT_CATALOG) if records is None else ConcurrentStableList(records)
        )

    def catalog_records(self) -> ConcurrentStableList[DictRecord]:
        """返回全量登记记录副本（插入序）。

        Returns:
            ConcurrentStableList[DictRecord]: 登记记录。
        """
        return ConcurrentStableList(self._records)

    def keys(self) -> ConcurrentStableSet[str]:
        """返回全部字典标识集合（去重，插入序）。

        Returns:
            ConcurrentStableSet[str]: 字典标识集合。
        """
        return ConcurrentStableSet(record.dict_key for record in self._records)

    def get(self, dict_key: str) -> DictRecord | None:
        """按字典标识取登记记录。

        Args:
            dict_key: 字典标识。

        Returns:
            DictRecord | None: 命中记录；未登记返回 `None`。
        """
        for record in self._records:
            if record.dict_key == dict_key:
                return record
        return None

    def validate(self) -> ConcurrentStableList[str]:
        """离线校验：标识格式与唯一、名称 / 数据出口非空、白名单字段名格式、策略合法、产品标识。

        Returns:
            ConcurrentStableList[str]: 问题描述列表（空列表 = 通过）。
        """
        issues: ConcurrentStableList[str] = ConcurrentStableList()
        seen: ConcurrentStableSet[str] = ConcurrentStableSet()
        valid_origins = {item.value for item in DictOrigin}
        valid_strategies = {item.value for item in DictStrategy}
        for record in self._records:
            if not _DICT_KEY_RE.match(record.dict_key):
                issues.add(f"字典标识格式非法：{record.dict_key!r}（须 {DICT_KEY_PATTERN}）")
            if record.dict_key in seen:
                issues.add(f"字典标识重复：{record.dict_key!r}")
            seen.add(record.dict_key)
            if not record.name:
                issues.add(f"字典名称缺失：{record.dict_key!r}")
            if not record.data_source:
                issues.add(f"数据出口标识缺失：{record.dict_key!r}")
            if record.origin not in valid_origins:
                issues.add(f"来源取值非法：{record.dict_key!r} → {record.origin!r}")
            if record.origin == DictOrigin.PRODUCT.value and not record.product_key:
                issues.add(f"产品来源缺产品标识：{record.dict_key!r}")
            for field_name in record.allowlist:
                if not _FIELD_RE.match(field_name):
                    issues.add(f"白名单字段名格式非法：{record.dict_key!r} → {field_name!r}")
            for strategy in record.strategies:
                if strategy not in valid_strategies:
                    issues.add(f"策略取值非法：{record.dict_key!r} → {strategy!r}")
        return issues
