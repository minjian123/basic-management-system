"""帮助包与内容域的静态规则（文件形态 / 大小上限 / 命令行默认值）。"""

from __future__ import annotations

from typing import Final

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.help.values import (
    ARTICLE_SOURCE_BUILTIN,
    ARTICLE_SOURCE_PRODUCT,
    ARTICLE_SOURCE_TENANT,
    ARTICLE_SOURCES,
    ARTICLE_STATUS_DRAFT,
    ARTICLE_STATUS_OFFLINE,
    ARTICLE_STATUS_PUBLISHED,
    ARTICLE_STATUSES,
    GENERATED_BY_AI,
    GENERATED_BY_MANUAL,
    PACKAGE_SCHEMA_VERSION,
    PACKAGE_STATUS_LOADED,
    PACKAGE_STATUS_OUTDATED,
    PACKAGE_STATUS_UNLOADED,
    PACKAGE_STATUSES,
    SOURCE_PRIORITY,
    TARGET_TYPE_ACTION,
    TARGET_TYPE_FIELD,
    TARGET_TYPE_FORM,
    TARGET_TYPE_GLOBAL,
    TARGET_TYPE_MODULE,
    TARGET_TYPES,
    source_for_product,
)

__all__ = [
    "ARTICLE_SOURCES",
    "ARTICLE_SOURCE_BUILTIN",
    "ARTICLE_SOURCE_PRODUCT",
    "ARTICLE_SOURCE_TENANT",
    "ARTICLE_STATUSES",
    "ARTICLE_STATUS_DRAFT",
    "ARTICLE_STATUS_OFFLINE",
    "ARTICLE_STATUS_PUBLISHED",
    "GENERATED_BY_AI",
    "GENERATED_BY_MANUAL",
    "HELP_PACKAGE_MANIFEST",
    "MAX_ARTICLE_CONTENT_BYTES",
    "MAX_ARTICLE_COUNT",
    "MAX_CATEGORY_COUNT",
    "MAX_LOCALE_COUNT",
    "MAX_PACKAGE_FILE_BYTES",
    "MAX_SOURCE_KEY_LENGTH",
    "MAX_TITLE_LENGTH",
    "PACKAGE_SCHEMA_VERSION",
    "PACKAGE_STATUSES",
    "PACKAGE_STATUS_LOADED",
    "PACKAGE_STATUS_OUTDATED",
    "PACKAGE_STATUS_UNLOADED",
    "SOURCE_PRIORITY",
    "TARGET_TYPES",
    "TARGET_TYPE_ACTION",
    "TARGET_TYPE_FIELD",
    "TARGET_TYPE_FORM",
    "TARGET_TYPE_GLOBAL",
    "TARGET_TYPE_MODULE",
    "source_for_product",
]

HELP_PACKAGE_MANIFEST: Final[str] = "package.yaml"
"""包清单固定文件名（装载器只认这个文件名）。"""

MAX_PACKAGE_FILE_BYTES: Final[int] = 2 * 1024 * 1024
"""单个包文件大小上限（2 MiB；防半成品 / 误引用大文件）。"""

MAX_ARTICLE_COUNT: Final[int] = 2000
"""单包文章数上限。"""

MAX_CATEGORY_COUNT: Final[int] = 500
"""单包分类数上限。"""

MAX_LOCALE_COUNT: Final[int] = 50
"""单篇文章语言数上限（与公告多语言同口径）。"""

MAX_TITLE_LENGTH: Final[int] = 256
"""标题最大字符数（与 `sys_help_article.title` 列宽一致）。"""

MAX_ARTICLE_CONTENT_BYTES: Final[int] = 60000
"""正文清洗后最大 UTF-8 字节数（与公告正文同口径，适配 MySQL TEXT）。"""

MAX_SOURCE_KEY_LENGTH: Final[int] = 128
"""`source_key` 最大长度（与列宽一致）。"""

DEFAULT_DRY_RUN: Final[bool] = True
"""装载 / 卸载的缺省模式：只预演，不写库。"""

DEFAULT_STRICT: Final[bool] = True
"""缺省严格模式：任一文章级错误整包拒收。"""

SUPPORTED_SCHEMA_VERSIONS: ConcurrentStableFrozenList[int] = ConcurrentStableFrozenList((PACKAGE_SCHEMA_VERSION,))
"""可接受的包格式版本。"""
