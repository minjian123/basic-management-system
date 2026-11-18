"""首页工作台业务域公共出口（D2 唯一跨域引用面）。

对外提供：只读 DTO（`BadgeCountView`）与领域端口（`RolePort` / `TodoCountPort` /
`NotificationBadgePort` / `DatasetProbePort`）。**本模块只做再导出**，不承载业务规则；
实现类、仓储与路由不出现在出口。
"""

from bms_platform.domains.dashboard.dto import BadgeCountView as BadgeCountView
from bms_platform.domains.dashboard.ports import DatasetProbePort as DatasetProbePort
from bms_platform.domains.dashboard.ports import NotificationBadgePort as NotificationBadgePort
from bms_platform.domains.dashboard.ports import RolePort as RolePort
from bms_platform.domains.dashboard.ports import RoleSummaryView as RoleSummaryView
from bms_platform.domains.dashboard.ports import TodoCountPort as TodoCountPort

__all__ = [
    "BadgeCountView",
    "DatasetProbePort",
    "NotificationBadgePort",
    "RolePort",
    "RoleSummaryView",
    "TodoCountPort",
]
