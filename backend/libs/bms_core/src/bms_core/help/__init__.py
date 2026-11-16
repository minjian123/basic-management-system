"""帮助锚点（`help_key`）：格式与形状校验、五级解析、内容侧端口。

- `bms_core/help/anchors.py`：`help_key` 的**唯一校验实现**（格式 / 形状 / 归一）；
- `bms_core/help/content.py`：内容侧端口（文章 / 分类 / 未命中结果）与依赖注入提供者；
- `bms_core/help/context.py`：五级候选链与解析编排；
- `bms_core/help/index.py`：锚点索引值对象与缓存读写。
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
from bms_core.help.content import (
    HELP_CONTENT_PLUGIN_KEY,
    BaseHelpContentResolver,
    HelpAnchorCandidate,
    HelpArticle,
    HelpArticleSummary,
    HelpCategory,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
    get_help_content_resolver,
)
from bms_core.help.context import HelpContextInput, build_help_candidates, resolve_help_context
from bms_core.help.index import (
    HELP_CACHE_DOMAIN,
    HelpAnchorIndex,
    HelpMenuAnchor,
    decode_help_anchor_index,
    encode_help_anchor_index,
    help_anchor_index_key,
    load_cached_help_anchor_index,
)

__all__ = [
    "ANCHOR_TABLES",
    "HELP_CACHE_DOMAIN",
    "HELP_CONTENT_PLUGIN_KEY",
    "HELP_KEY_MAX_LENGTH",
    "HELP_KEY_MAX_SEGMENT_LENGTH",
    "HELP_KEY_SEGMENT_COUNT",
    "HELP_KEY_SEGMENT_NAMES",
    "PLATFORM_PRODUCT_KEY",
    "BaseHelpContentResolver",
    "HelpAnchorCandidate",
    "HelpAnchorIndex",
    "HelpAnchorKind",
    "HelpArticle",
    "HelpArticleSummary",
    "HelpCategory",
    "HelpContentQuery",
    "HelpContentResult",
    "HelpContextInput",
    "HelpLevel",
    "HelpMenuAnchor",
    "build_help_candidates",
    "decode_help_anchor_index",
    "encode_help_anchor_index",
    "get_help_content_resolver",
    "help_anchor_index_key",
    "help_key_segment",
    "help_key_segments",
    "load_cached_help_anchor_index",
    "normalize_help_key",
    "resolve_help_context",
    "validate_help_key",
]
