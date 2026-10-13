"""`form_key` 构建期清单：系统字段 `form_key` 的跨表登记与全局唯一校验（02_11）。

口径（2026-10-11 用户拍板，需求 02-57 /《数据库开发规范》「系统字段」节 §3.1.2 / §3.1.3）：

- `form_key`＝**表单标识**（业务码字符串），落于**业务实体表**（字典表 + 表单表两类）；明细表、多对多关联表、
  元数据表、账本 / 日志 / 会话 / 锁 / 发件箱 / 表归属 / 节点映射等基础设施表**不落**。
- **核心用途＝多表联合（union）取数的表判别列**——同一 `form_key` 聚集一张表（一个表单 / 字典）的行，
  联合结果按 `form_key` 区分数据来源；故「同表多行同值」是设计意图。
- 每表 `(form_key, deleted_at)` 复合唯一（DB 层）；**跨表全局唯一**由本清单校验承担。
- `form_key` **保存后不变**，供通用页面路由 / 查询方案（`field_key = form_key`）/ 用户偏好（`list.{form_key}`）引用。

本模块只登记**界面标识 → 表**；数据源登记（`data_source_key`）归 `DataSourceRegistry`
（`bms_core/datasource/registry.py`）；`form_key → data_source_key`（多对一）在构建期**回填**
（默认 1:1 同名，任务 `02_10`），由通用页面路由解析（任务 `02_13` 消费）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject

__all__ = [
    "FORM_CATALOG",
    "FORM_KEY_PATTERN",
    "FormKind",
    "FormRecord",
    "FormRegistry",
    "FormStatus",
    "merge_form_records",
]

_FORM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

FORM_KEY_PATTERN = "^[a-z][a-z0-9_]*$"
"""表单标识（`form_key`）格式（业务码字符串）。"""


class FormStatus(StrEnum):
    """表单登记项状态。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


class FormKind(StrEnum):
    """表单类型（数据形态）。"""

    DICT = "dict"
    FORM = "form"


@dataclass(frozen=True)
class FormRecord(BaseValueObject):
    """`form_key` 登记记录（构建期清单 / 注入清单的不可变条目）。

    Attributes:
        form_key: 表单标识（业务码字符串，如 `role` / `tenant` / `purchase_order`），全局唯一、保存后不变。
        table: 物理表名（该标识所在实体表，如 `sys_role`）。
        name: 名称（通用页面路由 / 清单展示）。
        kind: 类型（`dict` 字典 / `form` 表单）。
        status: 状态（`enabled` / `disabled`）。
        data_source_key: 数据源标识（`form_key → data_source_key` 多对一；任务 `02_10` 回填，默认 1:1 同名；
            与 `DataSourceRegistry` 的**闭合**（回填值已登记）由 `check-system-fields.py` 对 bms 侧清单断言）。
    """

    form_key: str
    table: str
    name: str
    kind: str = FormKind.DICT.value
    status: str = FormStatus.ENABLED.value
    data_source_key: str | None = None


FORM_CATALOG: tuple[FormRecord, ...] = (
    FormRecord(
        form_key="module",
        table="sys_module",
        name="业务模块注册",
        kind=FormKind.DICT.value,
        data_source_key="module",
    ),
    FormRecord(
        form_key="product",
        table="sys_product",
        name="产品档案",
        kind=FormKind.DICT.value,
        data_source_key="product",
    ),
    FormRecord(
        form_key="business",
        table="sys_business",
        name="业务码",
        kind=FormKind.DICT.value,
        data_source_key="business",
    ),
    FormRecord(
        form_key="action",
        table="sys_action",
        name="动作码",
        kind=FormKind.DICT.value,
        data_source_key="action",
    ),
    FormRecord(
        form_key="role",
        table="sys_role",
        name="角色",
        kind=FormKind.DICT.value,
        data_source_key="role",
    ),
    FormRecord(
        form_key="user",
        table="sys_user",
        name="用户",
        kind=FormKind.DICT.value,
        data_source_key="user",
    ),
    FormRecord(
        form_key="config",
        table="sys_config",
        name="系统参数",
        kind=FormKind.DICT.value,
        data_source_key="config",
    ),
    FormRecord(
        form_key="tenant",
        table="sys_tenant",
        name="租户",
        kind=FormKind.DICT.value,
        data_source_key="tenant",
    ),
    FormRecord(
        form_key="identity_provider",
        table="sys_identity_provider",
        name="外部 IdP 配置",
        kind=FormKind.DICT.value,
        data_source_key="identity_provider",
    ),
    FormRecord(
        form_key="client",
        table="sys_client",
        name="第三方应用",
        kind=FormKind.DICT.value,
        data_source_key="client",
    ),
    FormRecord(
        form_key="task",
        table="sys_task",
        name="定时任务",
        kind=FormKind.DICT.value,
        data_source_key="task",
    ),
    FormRecord(
        form_key="icon",
        table="sys_icon",
        name="自定义图标",
        kind=FormKind.DICT.value,
        data_source_key="icon",
    ),
)
"""bms 侧构建期清单（字典表；表单表 `form` 类随产品 / 业务表以注入方式回补）。

`kind` 一律**逐条显式声明**（2026-10-13，任务 `08_01`）——不再依赖数据类默认值，
使「一个界面是不是字典页」的判定在清单层即可读；取值保持既有不变（本清单均为字典表）。
"""


def merge_form_records(
    builtin: tuple[FormRecord, ...] = FORM_CATALOG,
    injected: tuple[FormRecord, ...] = (),
) -> ConcurrentStableList[FormRecord]:
    """拼接构建期清单与项目注入记录（应用装配期视图的构造入口）。

    Args:
        builtin: 构建期清单（默认 `FORM_CATALOG`）。
        injected: 本部署注入的记录（各项目构建期声明；默认空）。

    Returns:
        ConcurrentStableList[FormRecord]: 合并后的登记记录（插入序：清单在前、注入在后）。
    """
    merged: ConcurrentStableList[FormRecord] = ConcurrentStableList(builtin)
    merged.update(injected)
    return merged


class FormRegistry(BaseFrameworkObject):
    """`form_key` 登记：离线校验与清单查询（**应用装配视图**）。"""

    def __init__(self, records: ConcurrentStableList[FormRecord] | None = None) -> None:
        """初始化。

        Args:
            records: 登记记录（插入序）；默认全量构建期清单 `FORM_CATALOG`
                （应用装配期应传入 `merge_form_records()` 结果）。
        """
        self._records: ConcurrentStableList[FormRecord] = (
            ConcurrentStableList(FORM_CATALOG) if records is None else ConcurrentStableList(records)
        )

    def catalog_records(self) -> ConcurrentStableList[FormRecord]:
        """返回全量登记记录副本（插入序）。

        Returns:
            ConcurrentStableList[FormRecord]: 登记记录。
        """
        return ConcurrentStableList(self._records)

    def keys(self) -> ConcurrentStableSet[str]:
        """返回全部表单标识集合（去重，插入序）。

        Returns:
            ConcurrentStableSet[str]: 表单标识集合。
        """
        return ConcurrentStableSet(record.form_key for record in self._records)

    def get(self, form_key: str) -> FormRecord | None:
        """按表单标识取登记记录。

        Args:
            form_key: 表单标识。

        Returns:
            FormRecord | None: 命中记录；未登记返回 `None`。
        """
        for record in self._records:
            if record.form_key == form_key:
                return record
        return None

    def by_table(self, table: str) -> FormRecord | None:
        """按物理表名取登记记录。

        Args:
            table: 物理表名（如 `sys_role`）。

        Returns:
            FormRecord | None: 命中记录；未登记返回 `None`。
        """
        for record in self._records:
            if record.table == table:
                return record
        return None

    def validate(self) -> ConcurrentStableList[str]:
        """离线校验：标识 / 表名格式与唯一、名称非空、类型合法。

        Returns:
            ConcurrentStableList[str]: 问题描述列表（空列表 = 通过）。
        """
        issues: ConcurrentStableList[str] = ConcurrentStableList()
        seen_keys: ConcurrentStableSet[str] = ConcurrentStableSet()
        seen_tables: ConcurrentStableSet[str] = ConcurrentStableSet()
        valid_kinds = {item.value for item in FormKind}
        valid_status = {item.value for item in FormStatus}
        for record in self._records:
            if not _FORM_KEY_RE.match(record.form_key):
                issues.add(f"表单标识格式非法：{record.form_key!r}（须 {FORM_KEY_PATTERN}）")
            if record.form_key in seen_keys:
                issues.add(f"表单标识重复（跨表全局唯一）：{record.form_key!r}")
            seen_keys.add(record.form_key)
            if not _TABLE_RE.match(record.table):
                issues.add(f"表名格式非法：{record.form_key!r} → {record.table!r}")
            if record.table in seen_tables:
                issues.add(f"表名重复登记：{record.table!r}")
            seen_tables.add(record.table)
            if not record.name:
                issues.add(f"名称缺失：{record.form_key!r}")
            if record.kind not in valid_kinds:
                issues.add(f"类型取值非法：{record.form_key!r} → {record.kind!r}")
            if record.status not in valid_status:
                issues.add(f"状态取值非法：{record.form_key!r} → {record.status!r}")
            if not record.data_source_key:
                issues.add(f"数据源标识缺失：{record.form_key!r}")
            elif not _FORM_KEY_RE.match(record.data_source_key):
                issues.add(f"数据源标识格式非法：{record.form_key!r} → {record.data_source_key!r}")
        return issues
