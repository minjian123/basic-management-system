"""富文本能力域：HTML 白名单清洗与内容安全口径（公告 / 帮助中心共用）。"""

from bms_core.richtext.sanitize import (
    MAX_NOTICE_CONTENT_BYTES,
    MAX_NOTICE_TITLE_LENGTH,
    html_text_length,
    sanitize_html,
)

__all__ = [
    "MAX_NOTICE_CONTENT_BYTES",
    "MAX_NOTICE_TITLE_LENGTH",
    "html_text_length",
    "sanitize_html",
]
