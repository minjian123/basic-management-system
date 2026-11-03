"""审计日志域：分片表结构、月份工具与规范化记录（06_01）。

- 两张日志表为**逻辑表名**，物理表按月分片 `{逻辑表名}_{yyyyMM}`；本模块用 SQLAlchemy Core
  动态声明分片表（不进入 `Base.metadata`，不参与迁移链），由 `ensure_shard` 幂等建表。
- 规范化记录是哈希链的**唯一口径**：写入与校验共用 `canonical_record`，键集合与值形态固定
  （ID 一律字符串、时间一律 UTC naive ISO8601 微秒），保证两侧重算逐字节一致。
- `shard_of_id`：由雪花 ID 反解时间戳定位分片（详情查询免扫全部分片）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, Text

from bms_core.audit.events import normalize_occurred_at
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.id_bits import EPOCH_MS, TIMESTAMP_SHIFT
from bms_core.models.base import SnowflakeId

__all__ = [
    "LOGIC_TABLES",
    "LOGIN_RECORD_FIELDS",
    "LOG_TYPE_LOGIN",
    "LOG_TYPE_OPERATION",
    "OPERATION_RECORD_FIELDS",
    "build_shard_table",
    "canonical_record",
    "month_key",
    "month_shift",
    "parse_month",
    "shard_of_id",
    "shard_table_name",
]

LOG_TYPE_OPERATION = "operation"
"""操作日志类型。"""

LOG_TYPE_LOGIN = "login"
"""登录日志类型。"""

LOGIC_TABLES: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {LOG_TYPE_OPERATION: "sys_operation_log", LOG_TYPE_LOGIN: "sys_login_log"}
)
"""日志类型 → 逻辑表名。"""

OPERATION_RECORD_FIELDS: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "id",
        "event_id",
        "tenant_id",
        "user_id",
        "username",
        "module",
        "action",
        "method",
        "path",
        "query_params",
        "params",
        "ip",
        "user_agent",
        "cost_time",
        "status",
        "error_msg",
        "occurred_at",
    )
)
"""操作日志参与链计算的字段（顺序即规范化顺序）。"""

LOGIN_RECORD_FIELDS: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "id",
        "event_id",
        "tenant_id",
        "user_id",
        "username",
        "ip",
        "user_agent",
        "status",
        "fail_reason",
        "occurred_at",
    )
)
"""登录日志参与链计算的字段。"""

_RECORD_FIELDS: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict(
    {LOG_TYPE_OPERATION: OPERATION_RECORD_FIELDS, LOG_TYPE_LOGIN: LOGIN_RECORD_FIELDS}
)


def month_key(value: datetime) -> str:
    """取时间所在月（`yyyyMM`）。

    Args:
        value: 时间（UTC naive / 带时区均可）。

    Returns:
        str: `yyyyMM`。
    """
    normalized = normalize_occurred_at(value)
    return f"{normalized.year:04d}{normalized.month:02d}"


def parse_month(month: str) -> tuple[int, int]:
    """解析 `yyyyMM`。

    Args:
        month: 月份键。

    Returns:
        tuple[int, int]: （年，月）。

    Raises:
        ValueError: 形态非法或月份越界。
    """
    if len(month) != 6 or not month.isdigit():
        raise ValueError(f"月份键非法（应为 yyyyMM）：{month!r}")
    year, month_number = int(month[:4]), int(month[4:])
    if not 1 <= month_number <= 12:
        raise ValueError(f"月份键非法（月份越界）：{month!r}")
    return year, month_number


def month_shift(month: str, delta: int) -> str:
    """月份加减。

    Args:
        month: 起始月份（`yyyyMM`）。
        delta: 偏移（正数向后、负数向前）。

    Returns:
        str: 目标月份。

    Raises:
        ValueError: 起始月份非法。
    """
    year, month_number = parse_month(month)
    index = year * 12 + (month_number - 1) + delta
    return f"{index // 12:04d}{index % 12 + 1:02d}"


def shard_table_name(log_type: str, month: str) -> str:
    """分片物理表名（`{逻辑表名}_{yyyyMM}`）。

    Args:
        log_type: 日志类型。
        month: 月份键。

    Returns:
        str: 物理表名。

    Raises:
        KeyError: 日志类型未登记。
    """
    return f"{LOGIC_TABLES[log_type]}_{month}"


def shard_of_id(record_id: int) -> str:
    """由雪花 ID 反解写入月份（详情查询定位分片）。

    Args:
        record_id: 雪花 ID。

    Returns:
        str: `yyyyMM`。
    """
    timestamp_ms = (record_id >> TIMESTAMP_SHIFT) + EPOCH_MS
    return month_key(datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC))


def _operation_columns() -> list[Column[Any]]:  # bare-collections:allow（SQLAlchemy 列声明顺序由 Table 决定）
    """操作日志分片列定义。"""
    return [
        Column("id", SnowflakeId, primary_key=True, autoincrement=False, comment="主键（雪花 ID）"),
        Column("event_id", String(64), nullable=False, comment="事件幂等键"),
        Column("tenant_id", SnowflakeId, nullable=True, comment="租户主键"),
        Column("user_id", SnowflakeId, nullable=True, comment="操作人主键"),
        Column("username", String(64), nullable=True, comment="操作账号快照"),
        Column("module", String(32), nullable=False, comment="模块"),
        Column("action", String(64), nullable=False, comment="动作（权限码 / 回落动词）"),
        Column("method", String(8), nullable=False, comment="HTTP 方法"),
        Column("path", String(512), nullable=False, comment="请求路径"),
        Column("query_params", Text, nullable=True, comment="查询串（已脱敏）"),
        Column("params", Text, nullable=True, comment="请求体参数 JSON（已脱敏）"),
        Column("ip", String(64), nullable=True, comment="客户端 IP"),
        Column("user_agent", String(512), nullable=True, comment="User-Agent"),
        Column("cost_time", Integer, nullable=True, comment="耗时（毫秒）"),
        Column("status", Integer, nullable=False, comment="HTTP 状态码"),
        Column("error_msg", String(512), nullable=True, comment="错误摘要"),
        Column("occurred_at", DateTime, nullable=False, comment="事件发生时间（UTC）"),
        Column("prev_hash", String(64), nullable=False, comment="前一条记录哈希"),
        Column("record_hash", String(64), nullable=False, comment="本条记录哈希"),
        Column("created_at", DateTime, nullable=False, comment="写入时间（UTC；分片键）"),
    ]


def _login_columns() -> list[Column[Any]]:  # bare-collections:allow（SQLAlchemy 列声明顺序由 Table 决定）
    """登录日志分片列定义。"""
    return [
        Column("id", SnowflakeId, primary_key=True, autoincrement=False, comment="主键（雪花 ID）"),
        Column("event_id", String(64), nullable=False, comment="事件幂等键"),
        Column("tenant_id", SnowflakeId, nullable=True, comment="租户主键"),
        Column("user_id", SnowflakeId, nullable=True, comment="命中用户主键"),
        Column("username", String(64), nullable=False, comment="登录名"),
        Column("ip", String(64), nullable=True, comment="客户端 IP"),
        Column("user_agent", String(512), nullable=True, comment="User-Agent"),
        Column("status", String(16), nullable=False, comment="结果（success / failed）"),
        Column("fail_reason", String(32), nullable=True, comment="失败原因"),
        Column("occurred_at", DateTime, nullable=False, comment="事件发生时间（UTC）"),
        Column("prev_hash", String(64), nullable=False, comment="前一条记录哈希"),
        Column("record_hash", String(64), nullable=False, comment="本条记录哈希"),
        Column("created_at", DateTime, nullable=False, comment="写入时间（UTC；分片键）"),
    ]


def build_shard_table(log_type: str, physical_table: str) -> Table:
    """声明一张分片表（独立 `MetaData`，不影响全局元数据）。

    Args:
        log_type: 日志类型。
        physical_table: 物理表名。

    Returns:
        Table: 分片表定义（索引随表创建）。

    Raises:
        KeyError: 日志类型未登记。
    """
    metadata = MetaData()
    columns = _operation_columns() if log_type == LOG_TYPE_OPERATION else _login_columns()
    table = Table(physical_table, metadata, *columns)
    Index(f"uq_{physical_table}_event_id", table.c.event_id, unique=True)
    Index(f"idx_{physical_table}_tenant_id_id", table.c.tenant_id, table.c.id)
    if log_type == LOG_TYPE_OPERATION:
        Index(f"idx_{physical_table}_user_id_occurred_at", table.c.user_id, table.c.occurred_at)
        Index(f"idx_{physical_table}_module_action", table.c.module, table.c.action)
        Index(f"idx_{physical_table}_occurred_at", table.c.occurred_at)
    else:
        Index(f"idx_{physical_table}_username_occurred_at", table.c.username, table.c.occurred_at)
        Index(f"idx_{physical_table}_status_occurred_at", table.c.status, table.c.occurred_at)
        Index(f"idx_{physical_table}_ip", table.c.ip)
        Index(f"idx_{physical_table}_occurred_at", table.c.occurred_at)
    return table


def _normalize_value(value: object) -> object:
    """规范化单个字段值（ID / 时间统一形态）。"""
    if isinstance(value, datetime):
        return normalize_occurred_at(value).isoformat(timespec="microseconds")
    if isinstance(value, int):
        return str(value)
    return value


def canonical_record(log_type: str, values: ConcurrentStableDict[str, object]) -> ConcurrentStableDict[str, object]:
    """构造参与哈希计算的规范化记录（字段集合固定、缺失为 None）。

    Args:
        log_type: 日志类型。
        values: 行值（DB 列名 → 值）。

    Returns:
        ConcurrentStableDict[str, object]: 规范化记录。

    Raises:
        KeyError: 日志类型未登记。
    """
    fields = _RECORD_FIELDS[log_type]
    return ConcurrentStableDict({field: _normalize_value(values.get(field)) for field in fields})
