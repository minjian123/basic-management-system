"""公告域常量：状态 / 动作 / 选项集标识 / 默认值。

状态与动作是**业务闭集**，由代码常量约束；类型与优先级是**可增长值域**，由选项集
（`deploy/registry/platform.toml`）声明并在运行时校验。
"""

from bms_core.core.concurrent import ConcurrentStableFrozenList

__all__ = [
    "NOTICE_ACTIONS",
    "NOTICE_ACTION_OFFLINE",
    "NOTICE_ACTION_PUBLISHED",
    "NOTICE_ACTION_UPDATED",
    "NOTICE_EVENT",
    "NOTICE_PRIORITY_DEFAULT",
    "NOTICE_PRIORITY_OPTION_SET",
    "NOTICE_STATUSES",
    "NOTICE_STATUS_DRAFT",
    "NOTICE_STATUS_OFFLINE",
    "NOTICE_STATUS_PUBLISHED",
    "NOTICE_TYPE_DEFAULT",
    "NOTICE_TYPE_OPTION_SET",
]

NOTICE_EVENT = "sys.notice.published"
"""公告发布 / 更新 / 过期下线事件名（已登记平台契约）。"""

NOTICE_STATUS_DRAFT = "draft"
"""草稿：可编辑，不展示给普通用户。"""

NOTICE_STATUS_PUBLISHED = "published"
"""发布中：满足时间窗口后对全员展示。"""

NOTICE_STATUS_OFFLINE = "offline"
"""已下线：到期扫描写入，不可再发布，历史与回执保留。"""

NOTICE_STATUSES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (NOTICE_STATUS_DRAFT, NOTICE_STATUS_PUBLISHED, NOTICE_STATUS_OFFLINE)
)
"""公告状态全集（插入序）。"""

NOTICE_ACTION_PUBLISHED = "published"
"""事件动作：发布。"""

NOTICE_ACTION_UPDATED = "updated"
"""事件动作：更新（已发布公告编辑后重新发布）。"""

NOTICE_ACTION_OFFLINE = "offline"
"""事件动作：过期下线。"""

NOTICE_ACTIONS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (NOTICE_ACTION_PUBLISHED, NOTICE_ACTION_UPDATED, NOTICE_ACTION_OFFLINE)
)
"""公告事件动作全集（插入序）。"""

NOTICE_TYPE_OPTION_SET = "bms.notice.type"
"""公告类型选项集标识（可增长）。"""

NOTICE_PRIORITY_OPTION_SET = "bms.notice.priority"
"""公告优先级选项集标识（可增长）。"""

NOTICE_TYPE_DEFAULT = "system"
"""公告类型默认值（选项集 `bms.notice.type` 的 `system`）。"""

NOTICE_PRIORITY_DEFAULT = "normal"
"""公告优先级默认值（选项集 `bms.notice.priority` 的 `normal`）。"""
