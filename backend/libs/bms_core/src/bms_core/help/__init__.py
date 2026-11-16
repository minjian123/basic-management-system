"""帮助锚点（`help_key`）：格式、形状与归一。

模块入口见 `bms_core/help/anchors.py`（唯一校验实现）。
"""

from bms_core.help.anchors import (
    ANCHOR_TABLES,
    HELP_KEY_MAX_LENGTH,
    HELP_KEY_MAX_SEGMENT_LENGTH,
    HELP_KEY_SEGMENT_COUNT,
    HELP_KEY_SEGMENT_NAMES,
    PLATFORM_PRODUCT_KEY,
    HelpAnchorKind,
    help_key_segment,
    help_key_segments,
    normalize_help_key,
    validate_help_key,
)

__all__ = [
    "ANCHOR_TABLES",
    "HELP_KEY_MAX_LENGTH",
    "HELP_KEY_MAX_SEGMENT_LENGTH",
    "HELP_KEY_SEGMENT_COUNT",
    "HELP_KEY_SEGMENT_NAMES",
    "PLATFORM_PRODUCT_KEY",
    "HelpAnchorKind",
    "help_key_segment",
    "help_key_segments",
    "normalize_help_key",
    "validate_help_key",
]
