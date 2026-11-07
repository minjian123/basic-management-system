"""审计日志事件：类型常量、载荷构造与时间 / 聚合键工具（06_01）。

- `OPERATION_LOG_EVENT` / `LOGIN_LOG_EVENT`：操作 / 登录审计事件类型（事件域均为已登记的 `sys`）。
- `audit_aggregate_key`：分区键（`tenant:{tenant_id}`，无租户 `global`）——审计链组按租户串行。
- `normalize_occurred_at` / `month_of`：事件时间统一为 UTC naive；分片键取**写入时刻**（调用方传当前时间），
  事件时间另存 `occurred_at`。
- `build_operation_event` / `build_login_event`：构造事件信封（可选字段为空时**不写入载荷**，契约字段只增不删）。

载荷中的 `params` / `query` 为**已脱敏**的字符串（中间件负责序列化）；本模块不做脱敏，避免职责重叠。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from bms_core.audit.base import RecordRef, with_audit_extensions
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope

__all__ = [
    "GLOBAL_AUDIT_TENANT",
    "LOGIN_LOG_EVENT",
    "OPERATION_LOG_EVENT",
    "audit_aggregate_key",
    "build_login_event",
    "build_operation_event",
    "month_of",
    "normalize_occurred_at",
]

OPERATION_LOG_EVENT = "sys.operation.logged"
"""操作日志事件类型（topic `bms-sys-operation`）。"""

LOGIN_LOG_EVENT = "sys.login.logged"
"""登录日志事件类型（topic `bms-sys-login`）。"""

GLOBAL_AUDIT_TENANT = "global"
"""无租户（平台级）链分条标识（与 `hashchain.GLOBAL_CHAIN_TENANT` 同值，避免跨模块取值）。"""


def normalize_occurred_at(value: datetime | None = None) -> datetime:
    """把事件时间统一为 UTC naive（跨库存储口径）。

    Args:
        value: 事件时间（可带时区）；None 取当前 UTC。

    Returns:
        datetime: UTC naive 时间。
    """
    if value is None:
        return datetime.now(UTC).replace(tzinfo=None)
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def month_of(value: datetime) -> str:
    """取时间所在月（`yyyyMM`，分片后缀口径）。

    Args:
        value: 时间（UTC naive）。

    Returns:
        str: `yyyyMM`。
    """
    return f"{value.year:04d}{value.month:02d}"


def audit_aggregate_key(tenant_id: str | None) -> str:
    """构造审计事件分区键（租户内串行）。

    Args:
        tenant_id: 租户主键（雪花 id 十进制字符串）；None 为平台级。

    Returns:
        str: `tenant:{id}` / `global`。
    """
    return f"tenant:{tenant_id}" if tenant_id else GLOBAL_AUDIT_TENANT


def _put(payload: ConcurrentStableDict[str, object], key: str, value: object) -> None:
    """写入非空字段（可选字段为空时不落载荷）。

    Args:
        payload: 载荷。
        key: 字段名。
        value: 字段值（None 不写）。
    """
    if value is not None and value != "":
        payload.set(key, value)


def build_operation_event(
    *,
    tenant_id: str | None,
    user_id: int | None,
    username: str | None,
    module: str,
    action: str,
    method: str,
    path: str,
    query: str | None,
    params: str | None,
    ip: str | None,
    user_agent: str | None,
    cost_time: int | None,
    status: int,
    error_msg: str | None,
    occurred_at: datetime | None = None,
    trace_id: str | None = None,
    module_key: str | None = None,
    resource_key: str | None = None,
    record_ref: RecordRef | None = None,
    extensions: Mapping[str, object] | None = None,  # bare-collections:allow（只读映射入参）
) -> EventEnvelope:
    """构造操作日志事件信封。

    Args:
        tenant_id: 租户主键（字符串；无租户为空）。
        user_id: 操作人主键。
        username: 操作账号快照。
        module: 模块。
        action: 动作（权限码或回落动词）。
        method: HTTP 方法。
        path: 请求路径。
        query: 查询串（已脱敏）。
        params: 请求体参数（已脱敏的 JSON 字符串）。
        ip: 客户端 IP。
        user_agent: User-Agent。
        cost_time: 耗时（毫秒）。
        status: HTTP 状态码。
        error_msg: 错误摘要。
        occurred_at: 事件时间；None 取当前 UTC。
        trace_id: 链路 id。
        module_key: 模块注册键（作用域第二级；无作用域事件为空，不写载荷）。
        resource_key: 资源标识（作用域第三级；模块级作用域为空，不写载荷）。
        record_ref: 记录级定位（涉及具体记录的操作才给；07D `02_04`）。
        extensions: 产品自定义标量字段（键不得占用标准字段名；07D `02_04`）。

    Returns:
        EventEnvelope: 事件信封（信封租户位与载荷同值）。

    Raises:
        ParamError: 记录级定位或扩展位非法（10001）。
    """
    occurred = normalize_occurred_at(occurred_at)
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "module": module,
            "action": action,
            "method": method,
            "path": path,
            "status": int(status),
        }
    )
    _put(payload, "tenant_id", tenant_id)
    _put(payload, "module_key", module_key)
    _put(payload, "resource_key", resource_key)
    _put(payload, "user_id", None if user_id is None else str(user_id))
    _put(payload, "username", username)
    _put(payload, "query", query)
    _put(payload, "params", params)
    _put(payload, "ip", ip)
    _put(payload, "user_agent", user_agent)
    _put(payload, "cost_time", cost_time)
    _put(payload, "error_msg", error_msg)
    return with_audit_extensions(
        EventEnvelope(
            event_type=OPERATION_LOG_EVENT,
            payload=payload,
            tenant_id=tenant_id,
            trace_id=trace_id,
            occurred_at=occurred,
            aggregate_key=audit_aggregate_key(tenant_id),
        ),
        record_ref=record_ref,
        extensions=extensions,
    )


def build_login_event(
    *,
    tenant_id: str | None,
    user_id: int | None,
    username: str,
    ip: str | None,
    user_agent: str | None,
    status: str,
    fail_reason: str | None = None,
    occurred_at: datetime | None = None,
    trace_id: str | None = None,
) -> EventEnvelope:
    """构造登录日志事件信封。

    Args:
        tenant_id: 租户主键（字符串）。
        user_id: 命中用户主键（可为空）。
        username: 登录名。
        ip: 客户端 IP。
        user_agent: User-Agent。
        status: 结果（`success` / `failed`）。
        fail_reason: 失败原因（成功为空）。
        occurred_at: 事件时间；None 取当前 UTC。
        trace_id: 链路 id。

    Returns:
        EventEnvelope: 事件信封。
    """
    occurred = normalize_occurred_at(occurred_at)
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "username": username,
            "status": status,
        }
    )
    _put(payload, "tenant_id", tenant_id)
    _put(payload, "user_id", None if user_id is None else str(user_id))
    _put(payload, "ip", ip)
    _put(payload, "user_agent", user_agent)
    _put(payload, "fail_reason", fail_reason)
    return EventEnvelope(
        event_type=LOGIN_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        trace_id=trace_id,
        occurred_at=occurred,
        aggregate_key=audit_aggregate_key(tenant_id),
    )
