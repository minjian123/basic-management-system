"""配额投影契约（07D `02_03`）：字段语义统一 + 四态判定。

产品按本契约返回自有配额维度，平台按同一形状对外呈现——**同一形状**是「平台只读可见且与产品侧
一致」的前提：字段语义（限额 / 用量 / 单位 / 周期 / 软硬限 / 更新时间 / 来源）在契约里唯一确定，
各产品不再自定结构。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from bms_core.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_QUOTA_CALL_TIMEOUT",
    "QuotaProjectionItem",
    "QuotaProjectionState",
    "judge_quota_state",
]

DEFAULT_QUOTA_CALL_TIMEOUT = 5.0
"""配额取数超时（秒）；运营视图低频调用，超时即降级 `unavailable`、不重试。"""


class QuotaProjectionState(StrEnum):
    """配额投影状态（四态：需求三态 + 正常态）。"""

    OK = "ok"
    """有值且未触硬限。"""

    DEFAULT = "default"
    """产品未提供该维度（缺省无限制）。"""

    UNAVAILABLE = "unavailable"
    """取数失败 / 超时 / 结构非法 / 无用量值。"""

    EXCEEDED = "exceeded"
    """用量达到或超过硬限。"""


class QuotaProjectionItem(BaseSchema):
    """单个配额维度的投影条目（产品返回与平台呈现**同一形状**）。"""

    quota_key: str = Field(description="配额维度键（取自声明的 `quota_dimensions`）")
    product_key: str = Field(description="产品键（声明方）")
    module_key: str = Field(description="模块注册键（作用域第二级）")
    resource_type: str | None = Field(default=None, description="资源类型标识（按资源聚合时给）")
    resource_key: str | None = Field(default=None, description="资源标识（按资源聚合时给）")
    limit: int | None = Field(default=None, description="限额；`None` = 不限")
    usage: int | None = Field(default=None, description="用量；`None` = 不可用（不得用 0 冒充）")
    unit: str = Field(description="单位（count / bytes / qps / rpm / percent）")
    period: str = Field(description="周期（none / hour / day / month）")
    soft_limit: int | None = Field(default=None, description="软限（告警线）")
    hard_limit: int | None = Field(default=None, description="硬限（拒绝线）")
    updated_at: datetime | None = Field(default=None, description="产品侧数据时间（UTC）")
    source: str = Field(description="来源标识（产品键 + 数据源键；不含内部地址）")
    state: QuotaProjectionState = Field(description="四态（基座统一判定）")


def judge_quota_state(
    *,
    provided: bool,
    usage: int | None,
    hard_limit: int | None,
) -> QuotaProjectionState:
    """判定投影状态（基座统一口径）。

    Args:
        provided: 产品是否提供了该维度。
        usage: 用量（`None` = 无值）。
        hard_limit: 硬限（`None` = 不限）。

    Returns:
        QuotaProjectionState: 四态之一。
    """
    if not provided:
        return QuotaProjectionState.DEFAULT
    if usage is None:
        return QuotaProjectionState.UNAVAILABLE
    if hard_limit is not None and usage >= hard_limit:
        return QuotaProjectionState.EXCEEDED
    return QuotaProjectionState.OK
