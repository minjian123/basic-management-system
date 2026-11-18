"""帮助反馈请求 / 响应模型（`/help/articles/{id}/feedback`，12_01）。"""

from __future__ import annotations

from pydantic import Field

from bms_core.schemas.base import BaseSchema
from bms_platform.domains.help.constants import MAX_FEEDBACK_COMMENT_LENGTH

__all__ = ["HelpFeedbackRequest", "HelpFeedbackResult"]


class HelpFeedbackRequest(BaseSchema):
    """提交 / 改投反馈请求。"""

    feedback: str = Field(min_length=1, max_length=16, description="反馈类型（helpful / unhelpful）")
    comment: str | None = Field(default=None, max_length=MAX_FEEDBACK_COMMENT_LENGTH, description="评论（可空）")


class HelpFeedbackResult(BaseSchema):
    """反馈结果（含文章最新计数）。"""

    feedback: str = Field(description="当前反馈类型")
    comment: str | None = Field(default=None, description="当前评论")
    helpful_count: int = Field(ge=0, description="有帮助数")
    unhelpful_count: int = Field(ge=0, description="无帮助数")
    changed: bool = Field(description="本次是否改变了既有反馈（同值重投为 False）")
