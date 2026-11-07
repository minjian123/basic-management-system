"""配额只读回显能力域（07D `02_03`）：投影契约、四态判定与只读装载。

**口径**：产品自维护配额值与执行点（单一事实源在产品侧），平台**只读装载**用于运营视图；
平台不写产品维度、不双写、不代产品执行配额（架构 41 §5.3）。

**四态**（`state`，基座统一判定，不由产品自报）：

| 值 | 条件 |
| --- | --- |
| `ok` | 取数成功、有值、未触硬限 |
| `default` | 产品未提供该维度 → 按「缺省无限制」呈现（`limit=None`） |
| `unavailable` | 取数失败 / 超时 / 响应结构非法 / 该维度无用量值 |
| `exceeded` | `hard_limit` 非空且 `usage >= hard_limit` |
"""

from bms_core.quota.reader import QuotaProjectionReader
from bms_core.quota.schemas import (
    DEFAULT_QUOTA_CALL_TIMEOUT,
    QuotaProjectionItem,
    QuotaProjectionState,
    judge_quota_state,
)

__all__ = [
    "DEFAULT_QUOTA_CALL_TIMEOUT",
    "QuotaProjectionItem",
    "QuotaProjectionReader",
    "QuotaProjectionState",
    "judge_quota_state",
]
