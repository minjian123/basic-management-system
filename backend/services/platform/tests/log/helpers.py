"""审计日志用例事件构造器（06_01）：事件 / 月份轴命名空间 / 用例专属租户。"""

from datetime import datetime

from bms_core.audit.events import LOGIN_LOG_EVENT, OPERATION_LOG_EVENT
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.events.base import EventEnvelope
from bms_core.metrics.base import BaseMetrics, MetricLabels
from bms_core.testing.namespace import Namespace

NOVEMBER = datetime(2026, 11, 15, 10, 0, 0)
DECEMBER = datetime(2026, 12, 20, 8, 0, 0)

_MONTH_BASE_YEAR = 2100
"""月份轴命名空间起始年（远离真实月份，避免与他人用例同月分片）。"""

_MONTH_YEARS = 3900
"""可分配年数（2100 ~ 5999）。"""

_MONTH_PAIRS = _MONTH_YEARS * 12 // 2
"""可分配槽位数：每例占**相邻两个月**且起点必为偶数，故不同用例的月份对互不重叠。"""


def log_months(ns: Namespace) -> tuple[datetime, datetime]:
    """取本用例专属的两个月份时刻（月份轴命名空间）。

    为什么需要：链校验 `AuditChainVerifier.verify()` 按**整月分片**遍历、不按租户过滤，
    「整月记录数 / 断裂序号」这类断言在共享库上会被同月的他人数据污染。分片表以月份为粒度，
    于是**月度轴本身就是天然的命名空间**：按命名空间前缀给每个用例分配一对互不重叠的合成
    月份，整月口径的断言就只落在自己的行上；需求里要保留「跨月衔接」的语义也不受影响。

    前缀含会话随机盐 → 同一用例跨会话落到不同月份，复用共享库时不会与自己上一轮的行相撞。

    Args:
        ns: 用例命名空间。

    Returns:
        tuple[datetime, datetime]: （较早月份写入时刻, 次月写入时刻）。
    """
    index = (int(ns.prefix[2:], 16) % _MONTH_PAIRS) * 2
    year = _MONTH_BASE_YEAR + index // 12
    month = index % 12 + 1
    next_year = year + 1 if month == 12 else year
    next_month = month % 12 + 1
    return (
        datetime(year, month, 15, 10, 0, 0),
        datetime(next_year, next_month, 20, 8, 0, 0),
    )


def log_tenant(ns: Namespace, index: int = 0) -> int:
    """取本用例专属租户主键（分片链按租户隔离，不与他人串链）。

    Args:
        ns: 用例命名空间。
        index: 租户序号（同一用例需要多个租户时递增）。

    Returns:
        int: 租户主键（1 亿 ~ 8.9 亿段，与 `test_log_write` 的 9 亿段错开）。
    """
    return 100_000_000 + (int(ns.prefix[2:], 16) * 2 + index) % 790_000_000


def operation_event(
    event_id: str,
    *,
    tenant_id: str | None = "1001",
    user_id: str = "7",
    module: str = "user",
    action: str = "user:create",
    status: int = 200,
    occurred_at: datetime = NOVEMBER,
    **overrides: object,
) -> EventEnvelope:
    """构造操作日志事件。"""
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "username": "alice",
            "module": module,
            "action": action,
            "method": "POST",
            "path": "/api/v1/users",
            "ip": "10.0.0.1",
            "user_agent": "pytest",
            "cost_time": 5,
            "status": status,
        }
    )
    for key, value in overrides.items():
        payload.set(key, value)
    return EventEnvelope(
        event_type=OPERATION_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}" if tenant_id else "global",
    )


def login_event(
    event_id: str,
    *,
    tenant_id: str = "1001",
    username: str = "alice",
    status: str = "success",
    ip: str = "10.0.0.1",
    occurred_at: datetime = NOVEMBER,
) -> EventEnvelope:
    """构造登录日志事件。"""
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": "1",
            "username": username,
            "ip": ip,
            "user_agent": "pytest",
            "status": status,
        }
    )
    if status != "success":
        payload.set("fail_reason", "bad_credentials")
    return EventEnvelope(
        event_type=LOGIN_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}",
    )


class RecordingMetrics(BaseMetrics):
    """指标器替身：记录三入口的调用参数（容量指标断言用）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.counters: ConcurrentStableList[tuple[str, float, MetricLabels | None]] = ConcurrentStableList()
        self.gauges: ConcurrentStableList[tuple[str, float, MetricLabels | None]] = ConcurrentStableList()
        self.histograms: ConcurrentStableList[tuple[str, float, MetricLabels | None]] = ConcurrentStableList()

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """记录计数器。"""
        self.counters.add((name, value, labels))

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录瞬时值。"""
        self.gauges.add((name, value, labels))

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录直方图。"""
        self.histograms.add((name, value, labels))
