"""关键表审计白名单（06_02）：哪些表纳入字段级变更审计。

口径（用户拍板 2026-11-16）：

- **基座常量** `AUDITED_TABLES`：平台关键表（出处《概要设计 · 审计合规》§2.2）；
- **产品注册** `register_audited_tables()`：产品仓装载期追加自己的表（与
  `services/table_registry.py` 的 `register_table_records()` 同构、幂等）；
- **配置增删** `[audit_capture].extra_tables` / `exclude_tables`：现场按合规要求临时增减，不改代码；
  `exclude_tables` 优先级最高（用于临时关掉噪声表）；
- **硬排除**：基础设施账本表（发件箱 / 消费去重 / 死信 / 作业）与审计自身表一律不审计——
  否则捕获会自审计递归（写发件箱触发新审计）。基础设施表即使被配置显式加入也不生效。

判定入口 `is_audited_table()` 是**唯一**判定点：ORM 捕获与显式留痕实现都读它，不各写一份名单。
"""

from __future__ import annotations

from collections.abc import Iterable

from bms_core.core.concurrent import ConcurrentStableFrozenSet, ConcurrentStableSet
from bms_core.core.config import get_settings

__all__ = [
    "AUDITED_TABLES",
    "AUDIT_SELF_TABLES",
    "INFRA_TABLES",
    "is_audited_table",
    "register_audited_tables",
    "reset_audited_tables",
]

AUDITED_TABLES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "sys_user",
        "sys_role",
        "sys_user_role",
        "sys_role_permission",
        "sys_role_field",
        "sys_notice",
        "sys_help_article",
        "wf_process",
    )
)
"""基座关键表清单（《概要设计 · 审计合规》§2.2 中归属 platform 的表）。

`sys_tenant_quota` 等**归属其他服务**的关键表不在本常量内——基座不得引用他人服务库的表名
（跨服务库访问门禁）；由该服务在装载期经 `register_audited_tables()` 自行注册（tenant 服务已注册
`sys_tenant_quota`）。主数据表与产品业务表同理，由产品仓注册后纳入。
"""

INFRA_TABLES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
        "sys_job",
        "sys_job_error",
        "sys_job_type",
        "sys_job_monitor",
    )
)
"""基础设施账本表（硬排除：写这些表本身不产生审计，避免自审计递归）。"""

AUDIT_SELF_TABLES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "sys_data_audit_log",
        "sys_operation_log",
        "sys_login_log",
        "sys_open_log",
        "sys_audit_shard",
    )
)
"""审计自身表（硬排除：审计数据只追加，绝不自我审计）。"""

_REGISTERED: ConcurrentStableSet[str] = ConcurrentStableSet()
"""产品侧注册的表（装载期经 `register_audited_tables()` 登记；插入序）。"""


def register_audited_tables(tables: Iterable[str]) -> None:
    """注册产品侧纳入审计的表（**装载期**调用；同值重复登记无操作，幂等）。

    产品服务在应用装配（`BaseServiceApplicationFactory.table_records()` 同时机）调用本函数；
    登记后 `is_audited_table()` 即生效。

    Args:
        tables: 逻辑表名（插入序）。
    """
    for table in tables:
        _REGISTERED.add(table)


def reset_audited_tables() -> None:
    """清空产品注册表（**测试隔离用**；不影响基座常量）。"""
    _REGISTERED.clear()


def is_audited_table(table: str) -> bool:
    """判断表是否纳入字段级审计（唯一判定点）。

    直接读三个来源判定而不构造合并集合（每次 flush 都会调用，避免反复建集合）。

    Args:
        table: 逻辑表名。

    Returns:
        bool: 纳入为 True（基础设施表与审计自身表恒为 False）。
    """
    if not table or table in INFRA_TABLES or table in AUDIT_SELF_TABLES:
        return False
    settings = get_settings().audit_capture
    if table in settings.exclude_tables:
        return False
    return table in AUDITED_TABLES or table in _REGISTERED or table in settings.extra_tables
