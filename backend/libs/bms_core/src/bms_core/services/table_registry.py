"""表归属登记：表 → 「归属服务 + 库类别」单一来源（06_03）。

- `TABLE_OWNERSHIP` 是种子（`ops/seed_tables.py`）、启动 / CI 双向对账（`ops/check_tables.py`）、
  静态硬校验与运行时守卫、迁移链表集派生的**单一来源**（与服务目录 `SERVICE_CATALOG` 同源模式）。
- 归属语义：每张表有唯一归属服务；`sys_` 为平台共享前缀，按**表级归属**判定（不再整前缀放行）。
- 基础设施表（发件箱三表）归「每服务自有」（`OWNER_EVERY_SERVICE`），不参与跨服务归属判定，
  每条链（平台 / 租户）各含三表。
- 库类别（`Datasource`）：`platform` / `tenant` / `archive`；基础设施表取 `both`（两链各有）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_table_ownership`）。
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from bms_core.core.base import BaseObject
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord

TABLE_OWNERSHIP_NAME = "sys_table_ownership"
"""归属登记表名（平台链）。"""

OWNER_EVERY_SERVICE = "*"
"""归属哨兵：每服务自有（仅基础设施表可用）。"""

RESERVED_SERVICE_KEYS: tuple[str, ...] = ("permission",)
"""预留服务标识（尚未建设、但归属已定案的服务；随服务目录登记后收敛）。"""

_TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SHARED_TABLE_PREFIX = "sys_"
"""平台共享前缀：`sys_` 表按表级归属判定，不要求与归属服务表前缀一致。"""


class Datasource(StrEnum):
    """库类别（`sys_table_ownership.datasource`）。"""

    PLATFORM = "platform"
    TENANT = "tenant"
    ARCHIVE = "archive"
    BOTH = "both"
    """两链各有（仅基础设施表可用）。"""


class TableStatus(StrEnum):
    """归属登记状态（`sys_table_ownership.status`）。"""

    ENABLED = "enabled"
    """已定案且进入迁移链（`chain_tables` 取之）。"""

    PLANNED = "planned"
    """归属已定但未定稿 / 未落库（含预留归属与骨架表）：库位「寄放」，**不进链**，随所属阶段转 `enabled`。"""


@dataclass(frozen=True)
class TableRecord(BaseObject):
    """表归属登记记录（字段与 `sys_table_ownership` 对齐）。"""

    table_name: str
    owner: str
    datasource: str = Datasource.TENANT
    status: str = TableStatus.ENABLED
    note: str = ""

    @classmethod
    def from_row(cls, row: object) -> TableRecord:
        """按登记字段从 ORM 行（或任意同构对象）构造记录（接库对账用）。

        Args:
            row: 具备登记字段的对象（如 `SysTableOwnership` 行）。

        Returns:
            TableRecord: 归属登记记录。
        """
        data = cast("Any", row)
        return cls(
            table_name=cast("str", data.table_name),
            owner=cast("str", data.owner),
            datasource=cast("str", data.datasource),
            status=cast("str", data.status),
            note=cast("str", data.note or ""),
        )


TABLE_OWNERSHIP: tuple[TableRecord, ...] = (
    # ---- 归属登记自身（自举登记）----
    TableRecord(
        table_name=TABLE_OWNERSHIP_NAME,
        owner="platform",
        datasource=Datasource.PLATFORM,
        note="表归属登记表（自举）",
    ),
    # ---- 基础设施：每服务自有（不参与跨服务归属判定）----
    TableRecord(
        table_name="sys_outbox",
        owner=OWNER_EVERY_SERVICE,
        datasource=Datasource.BOTH,
        note="事务性发件箱（每服务每链各一）",
    ),
    TableRecord(
        table_name="sys_event_consumed",
        owner=OWNER_EVERY_SERVICE,
        datasource=Datasource.BOTH,
        note="消费幂等去重（每服务每链各一）",
    ),
    TableRecord(
        table_name="sys_event_dead_letter",
        owner=OWNER_EVERY_SERVICE,
        datasource=Datasource.BOTH,
        note="死信（每服务每链各一）",
    ),
    # ---- 平台层表（库类别 platform）----
    TableRecord(table_name="sys_tenant", owner="tenant", datasource=Datasource.PLATFORM, note="租户注册"),
    TableRecord(table_name="sys_module", owner="platform", datasource=Datasource.PLATFORM, note="服务目录登记"),
    TableRecord(table_name="sys_module_i18n", owner="platform", datasource=Datasource.PLATFORM, note="服务目录多语言"),
    TableRecord(
        table_name="sys_tenant_quota",
        owner="tenant",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="租户配额（预留，寄放平台库）",
    ),
    TableRecord(
        table_name="sys_tenant_module",
        owner="tenant",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="租户模块开关（预留，寄放平台库）",
    ),
    TableRecord(
        table_name="sys_menu",
        owner="permission",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="平台菜单（权限服务未建，预留）",
    ),
    TableRecord(
        table_name="sys_business",
        owner="permission",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="业务权限码（预留）",
    ),
    TableRecord(
        table_name="sys_action",
        owner="permission",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="动作权限码（预留）",
    ),
    TableRecord(
        table_name="sys_form",
        owner="platform",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="平台表单（归属随表单定制阶段复评）",
    ),
    TableRecord(
        table_name="sys_field",
        owner="platform",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="表单字段（同上）",
    ),
    TableRecord(
        table_name="sys_button",
        owner="platform",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="表单按钮（同上）",
    ),
    TableRecord(
        table_name="sys_form_layout",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="表单三级布局（预留）",
    ),
    TableRecord(
        table_name="sys_field_ext",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="租户自建字段（预留）",
    ),
    TableRecord(
        table_name="sys_admin",
        owner="identity",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="平台运营账号（预留）",
    ),
    TableRecord(
        table_name="sys_user_identity",
        owner="identity",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="SSO 全局身份映射（预留）",
    ),
    TableRecord(
        table_name="sys_user",
        owner="org",
        datasource=Datasource.TENANT,
        note="用户最小模型（本地登录凭据 / 状态 / 锁定字段）",
    ),
    TableRecord(
        table_name="sys_session",
        owner="identity",
        datasource=Datasource.TENANT,
        note="会话记录（登录 / 刷新 / 登出载体）",
    ),
    TableRecord(
        table_name="sys_account_lock",
        owner="identity",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="账号锁定（预留）",
    ),
    TableRecord(
        table_name="sys_identity_provider",
        owner="identity",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="租户外部 IdP 配置（预留）",
    ),
    TableRecord(
        table_name="sys_client",
        owner="identity",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="第三方应用客户端（预留）",
    ),
    TableRecord(
        table_name="sys_ai_provider",
        owner="ai",
        datasource=Datasource.PLATFORM,
        status=TableStatus.PLANNED,
        note="AI 端点配置（预留）",
    ),
    # ---- 租户层表（库类别 tenant）----
    TableRecord(table_name="sys_dict_type", owner="platform", datasource=Datasource.TENANT, note="字典类型"),
    TableRecord(table_name="sys_dict_item", owner="platform", datasource=Datasource.TENANT, note="字典条目"),
    TableRecord(table_name="sys_dict_type_i18n", owner="platform", datasource=Datasource.TENANT, note="字典类型多语言"),
    TableRecord(table_name="sys_dict_item_i18n", owner="platform", datasource=Datasource.TENANT, note="字典条目多语言"),
    TableRecord(table_name="sys_dict_attr", owner="platform", datasource=Datasource.TENANT, note="字典扩展属性"),
    TableRecord(table_name="sys_dict_attr_i18n", owner="platform", datasource=Datasource.TENANT, note="字典属性多语言"),
    TableRecord(table_name="sys_query_scheme", owner="platform", datasource=Datasource.TENANT, note="查询方案"),
    TableRecord(
        table_name="sys_task",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="定时任务定义（未定稿，不进链）",
    ),
    TableRecord(
        table_name="sys_task_log",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="定时任务执行记录（未定稿，不进链）",
    ),
    TableRecord(
        table_name="sys_user_preference",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="用户偏好（未定稿，不进链）",
    ),
    TableRecord(
        table_name="sys_icon",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="租户自定义图标（未定稿，不进链）",
    ),
    TableRecord(
        table_name="sys_icon_i18n",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="图标多语言（未定稿，不进链）",
    ),
    TableRecord(
        table_name="sys_notification",
        owner="notification",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="站内信 / 待办（未定稿，不进链）",
    ),
    TableRecord(
        table_name="ai_chat_log",
        owner="ai",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="AI 交互审计（未定稿，不进链）",
    ),
    TableRecord(
        table_name="demo",
        owner="platform",
        datasource=Datasource.TENANT,
        status=TableStatus.PLANNED,
        note="平台服务五层示例表（无表前缀；未定稿，不进链）",
    ),
)
"""表归属登记（单一来源）。

- `TableStatus.ENABLED`：归属已定案且进入迁移链（`chain_tables`）；
- `TableStatus.PLANNED`：归属已定但**未定稿 / 未落库**（骨架表与演示表），不进链，
  随所属阶段补表文件与模型并转 `enabled` 时自动进链（见《数据库开发规范》「迁移与建表口径」）；
- `sys_` 为平台共享前缀，按**表级归属**判定（不再整前缀放行）。
"""


def _owner_label(record: ModuleRecord) -> str:
    """服务目录行的归属标签（`service_key` 优先，缺省回落 `module_key`）。

    Args:
        record: 服务目录登记行。

    Returns:
        str: 归属标签。
    """
    return record.service_key or record.module_key


def known_service_keys() -> frozenset[str]:
    """可作为归属标签的服务标识集合（服务目录标签 ∪ 预留服务标识）。

    Returns:
        frozenset[str]: 归属标签集合。
    """
    return frozenset(_owner_label(record) for record in SERVICE_CATALOG) | frozenset(RESERVED_SERVICE_KEYS)


def service_table_prefixes() -> dict[str, frozenset[str]]:
    """服务标识 → 该服务在服务目录登记的表前缀集合。

    Returns:
        dict[str, frozenset[str]]: 归属标签到前缀集合。
    """
    prefixes: dict[str, set[str]] = {}
    for record in SERVICE_CATALOG:
        prefixes.setdefault(_owner_label(record), set()).add(record.table_prefix)
    return {label: frozenset(values) for label, values in prefixes.items()}


def table_owner(table_name: str) -> str | None:
    """取表名归属（未登记返回 None）。

    Args:
        table_name: 表名。

    Returns:
        str | None: 归属服务标识；基础设施表返回 `*`；未登记返回 None。
    """
    for record in TABLE_OWNERSHIP:
        if record.table_name == table_name:
            return record.owner
    return None


def table_record(table_name: str) -> TableRecord | None:
    """取表归属登记记录（未登记返回 None）。

    Args:
        table_name: 表名。

    Returns:
        TableRecord | None: 登记记录。
    """
    return next((record for record in TABLE_OWNERSHIP if record.table_name == table_name), None)


def owned_tables_for(service: str, *, datasource: str | None = None, include_planned: bool = True) -> frozenset[str]:
    """取某服务名下的表集合（可按库类别与状态过滤）。

    Args:
        service: 服务标识（归属标签）。
        datasource: 库类别过滤（`platform` / `tenant` / `archive` / `both`）；None 取全部。
        include_planned: 是否含预留归属（`planned`）。

    Returns:
        frozenset[str]: 表名集合。
    """
    return frozenset(
        record.table_name
        for record in TABLE_OWNERSHIP
        if record.owner == service
        and (datasource is None or record.datasource == datasource)
        and (include_planned or record.status == TableStatus.ENABLED)
    )


def infrastructure_tables() -> frozenset[str]:
    """基础设施表集合（每服务自有，不参与跨服务归属判定）。

    Returns:
        frozenset[str]: 表名集合。
    """
    return frozenset(
        record.table_name
        for record in TABLE_OWNERSHIP
        if record.owner == OWNER_EVERY_SERVICE and record.datasource == Datasource.BOTH
    )


def chain_tables(service: str, datasource: str) -> frozenset[str]:
    """取迁移链 / 自动建表的**目标表集**（归属登记派生：该服务表 + 基础设施表）。

    口径（06_02 收口）：
    - 只取 `status = enabled` 的归属表——`planned`（未定稿 / 未落库）不参与，随所属阶段转
      `enabled` 时**自动进链**；
    - 基础设施表（发件箱三表）只进入 `platform` / `tenant` 链，**归档链不含**；
    - 目标表集与「已有模型」取交集后才是实际建表集（见 `db/migration.py::chain_metadata`）。

    Args:
        service: 服务标识（归属标签）。
        datasource: 库类别（`platform` / `tenant` / `archive`）。

    Returns:
        frozenset[str]: 表名集合（保序无关）。
    """
    owned = {
        record.table_name
        for record in TABLE_OWNERSHIP
        if record.owner == service and record.datasource == datasource and record.status == TableStatus.ENABLED
    }
    if datasource == Datasource.ARCHIVE:
        return frozenset(owned)
    infra = {
        record.table_name
        for record in TABLE_OWNERSHIP
        if record.owner == OWNER_EVERY_SERVICE
        and record.datasource in (datasource, Datasource.BOTH)
        and record.status == TableStatus.ENABLED
    }
    return frozenset(owned | infra)


def table_names() -> frozenset[str]:
    """全部已登记表名。

    Returns:
        frozenset[str]: 表名集合。
    """
    return frozenset(record.table_name for record in TABLE_OWNERSHIP)


def registered_services() -> frozenset[str]:
    """有表登记在册的服务标识（含预留）。

    Returns:
        frozenset[str]: 服务标识集合。
    """
    return frozenset(record.owner for record in TABLE_OWNERSHIP if record.owner != OWNER_EVERY_SERVICE)


def _duplicates(values: list[str]) -> list[str]:
    """取重复值（保持首次出现顺序）。

    Args:
        values: 待检查值列表。

    Returns:
        list[str]: 重复出现的值。
    """
    counter = Counter(values)
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if counter[value] > 1 and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class TableOwnershipRegistry(BaseObject):
    """表归属校验 / 清单查询（离线，与服务目录校验同源模式）。"""

    def __init__(self, tables: Sequence[TableRecord] = TABLE_OWNERSHIP) -> None:
        """初始化。

        Args:
            tables: 归属清单；默认全量 `TABLE_OWNERSHIP`。
        """
        self._tables = list(tables)

    def list_tables(
        self,
        *,
        owner: str | None = None,
        datasource: str | None = None,
        status: str | None = None,
    ) -> list[TableRecord]:
        """返回归属清单（可按归属 / 库类别 / 状态筛选）。

        Args:
            owner: 归属服务标识过滤；None 返回全部。
            datasource: 库类别过滤；None 返回全部。
            status: 状态过滤；None 返回全部。

        Returns:
            list[TableRecord]: 归属记录列表。
        """
        result = self._tables
        if owner is not None:
            result = [record for record in result if record.owner == owner]
        if datasource is not None:
            result = [record for record in result if record.datasource == datasource]
        if status is not None:
            result = [record for record in result if record.status == status]
        return list(result)

    def validate(self) -> list[str]:
        """校验归属清单：表名唯一与格式 + 归属 / 库类别 / 状态合法 + 前缀归属一致。

        Returns:
            list[str]: 非法明细；空列表表示通过。
        """
        errors: list[str] = []
        for record in self._tables:
            errors.extend(self._validate_record(record))
        for duplicate in _duplicates([record.table_name for record in self._tables]):
            errors.append(f"表名重复登记：{duplicate}")
        return errors

    def _validate_record(self, record: TableRecord) -> list[str]:
        """校验单条归属记录。

        Args:
            record: 归属记录。

        Returns:
            list[str]: 非法明细。
        """
        errors: list[str] = []
        name = record.table_name
        if not _TABLE_NAME_RE.match(name):
            errors.append(f"{name}：表名非法")
        services = known_service_keys()
        if record.owner != OWNER_EVERY_SERVICE and record.owner not in services:
            errors.append(f"{name}：归属服务未登记（{record.owner}）")
        if record.owner == OWNER_EVERY_SERVICE and record.datasource != Datasource.BOTH:
            errors.append(f"{name}：`{OWNER_EVERY_SERVICE}` 归属须为 `both` 库类别（现 {record.datasource}）")
        if record.datasource not in tuple(Datasource):
            errors.append(f"{name}：库类别非法（{record.datasource}）")
        elif record.datasource == Datasource.BOTH and record.owner != OWNER_EVERY_SERVICE:
            errors.append(f"{name}：`both` 库类别仅限「每服务自有」基础设施表")
        if record.status not in tuple(TableStatus):
            errors.append(f"{name}：状态非法（{record.status}）")
        errors.extend(self._validate_prefix(record))
        return errors

    def _validate_prefix(self, record: TableRecord) -> list[str]:
        """校验表名前缀归属（`sys_` 共享前缀与无前缀表跳过）。

        Args:
            record: 归属记录。

        Returns:
            list[str]: 非法明细。
        """
        name = record.table_name
        if "_" not in name or name.startswith(_SHARED_TABLE_PREFIX):
            return []
        prefix = f"{name.split('_', 1)[0]}_"
        prefixes = service_table_prefixes().get(record.owner, frozenset())
        if prefix not in prefixes:
            return [f"{name}：表前缀 {prefix} 不属于归属服务 {record.owner}（已登记前缀 {sorted(prefixes) or '无'}）"]
        return []


def validate_table_ownership(
    ownership: Sequence[TableRecord],
    records: Sequence[TableRecord],
) -> list[str]:
    """接库表归属校验（启动 / CI 共用）：库内校验 + 与清单双向对账。

    Args:
        ownership: 归属清单（`TABLE_OWNERSHIP`）。
        records: 库中未软删行转换结果（`TableRecord.from_row`）。

    Returns:
        list[str]: 冲突 / 非法明细；空列表表示通过。
    """
    errors = TableOwnershipRegistry(records).validate()
    errors.extend(_diff_ownership(ownership, records))
    return errors


def _diff_ownership(ownership: Iterable[TableRecord], records: Sequence[TableRecord]) -> list[str]:
    """清单与库记录双向对账（缺行 / 清单外行 / 字段不符）。

    Args:
        ownership: 归属清单。
        records: 库中未软删行转换结果。

    Returns:
        list[str]: 对账明细。
    """
    expected = {record.table_name: record for record in ownership}
    actual = {record.table_name: record for record in records}
    errors: list[str] = []
    for name in sorted(actual.keys() - expected.keys()):
        errors.append(f"库中登记行不在清单：{name}")
    for name in sorted(expected.keys() - actual.keys()):
        errors.append(f"库中缺登记行：{name}")
    for name in sorted(expected.keys() & actual.keys()):
        for field in ("owner", "datasource", "status", "note"):
            expected_value = getattr(expected[name], field)
            actual_value = getattr(actual[name], field)
            if expected_value != actual_value:
                errors.append(f"{name}：{field} 与清单不一致（库 {actual_value!r}，清单 {expected_value!r}）")
    return errors
