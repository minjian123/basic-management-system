"""通知类型常量（跨生产方 / 消费方共用，避免两处口径漂移）。"""

from bms_core.core.concurrent import ConcurrentStableFrozenList

__all__ = [
    "NOTIFICATION_TYPES",
    "NOTIFICATION_TYPE_ALERT",
    "NOTIFICATION_TYPE_APPROVAL",
    "NOTIFICATION_TYPE_IMPORT",
    "NOTIFICATION_TYPE_SYSTEM",
]

NOTIFICATION_TYPE_SYSTEM = "system"
"""系统提示。"""

NOTIFICATION_TYPE_APPROVAL = "approval"
"""审批待办。"""

NOTIFICATION_TYPE_ALERT = "alert"
"""告警。"""

NOTIFICATION_TYPE_IMPORT = "import"
"""导入 / 导出任务结果。"""

NOTIFICATION_TYPES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        NOTIFICATION_TYPE_SYSTEM,
        NOTIFICATION_TYPE_APPROVAL,
        NOTIFICATION_TYPE_ALERT,
        NOTIFICATION_TYPE_IMPORT,
    )
)
"""通知类型固定取值（非法类型拒绝）。"""
