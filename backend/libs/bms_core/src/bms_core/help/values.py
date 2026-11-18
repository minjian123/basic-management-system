"""帮助内容的静态值域：文章状态 / 来源 / 目标类型 / 包状态（08_03）。

这些值域是**业务闭集**（运行期不可增长），由代码常量约束，不登记选项集；菜单 / 表单 /
字段 / 按钮 / 动作码上的锚点格式与数值域见 `help/anchors.py`。模型默认值、装载器校验与
解析实现共用本模块，避免三处各写一份字符串。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.help.anchors import PLATFORM_PRODUCT_KEY

__all__ = [
    "ARTICLE_SOURCES",
    "ARTICLE_SOURCE_BUILTIN",
    "ARTICLE_SOURCE_PRODUCT",
    "ARTICLE_SOURCE_TENANT",
    "ARTICLE_STATUSES",
    "ARTICLE_STATUS_DRAFT",
    "ARTICLE_STATUS_OFFLINE",
    "ARTICLE_STATUS_PUBLISHED",
    "FEEDBACK_HELPFUL",
    "FEEDBACK_UNHELPFUL",
    "FEEDBACK_VALUES",
    "GENERATED_BY_AI",
    "GENERATED_BY_MANUAL",
    "GENERATED_BY_VALUES",
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

ARTICLE_STATUS_DRAFT = "draft"
"""文章状态：草稿（仅后台可见，不进入解析与检索）。"""

ARTICLE_STATUS_PUBLISHED = "published"
"""文章状态：已发布（前台可见、参与解析）。"""

ARTICLE_STATUS_OFFLINE = "offline"
"""文章状态：已下架（前台隐藏；包内移除只置本状态，不物理删）。"""

ARTICLE_STATUSES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (ARTICLE_STATUS_DRAFT, ARTICLE_STATUS_PUBLISHED, ARTICLE_STATUS_OFFLINE)
)
"""文章状态全集（插入序）。"""

ARTICLE_SOURCE_BUILTIN = "builtin"
"""文章来源：平台内建（`product_key = platform` 的帮助包）。"""

ARTICLE_SOURCE_PRODUCT = "product"
"""文章来源：产品帮助包（`product_key` 非 platform）。"""

ARTICLE_SOURCE_TENANT = "tenant"
"""文章来源：租户自建（后台人工维护，或租户对包文章的本地编辑）。"""

ARTICLE_SOURCES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (ARTICLE_SOURCE_BUILTIN, ARTICLE_SOURCE_PRODUCT, ARTICLE_SOURCE_TENANT)
)
"""文章来源全集（插入序即优先级：builtin > product > tenant）。"""

SOURCE_PRIORITY: ConcurrentStableFrozenDict[str, int] = ConcurrentStableFrozenDict(
    {
        ARTICLE_SOURCE_BUILTIN: 0,
        ARTICLE_SOURCE_PRODUCT: 1,
        ARTICLE_SOURCE_TENANT: 2,
    }
)
"""来源优先级（数值越小越优先）。"""

TARGET_TYPE_GLOBAL = "global"
"""目标类型：全局（无元数据锚点，解析链最后一级）。"""

TARGET_TYPE_MODULE = "module"
"""目标类型：模块（菜单锚点）。"""

TARGET_TYPE_FORM = "form"
"""目标类型：表单（表单锚点）。"""

TARGET_TYPE_FIELD = "field"
"""目标类型：字段（字段锚点）。"""

TARGET_TYPE_ACTION = "action"
"""目标类型：动作（按钮锚点或动作码全局兜底锚点）。"""

TARGET_TYPES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (TARGET_TYPE_GLOBAL, TARGET_TYPE_MODULE, TARGET_TYPE_FORM, TARGET_TYPE_FIELD, TARGET_TYPE_ACTION)
)
"""目标类型全集（插入序）。"""

PACKAGE_STATUS_LOADED = "loaded"
"""包状态：当前版本（同一产品同一时刻最多一行）。"""

PACKAGE_STATUS_OUTDATED = "outdated"
"""包状态：已被更高版本取代。"""

PACKAGE_STATUS_UNLOADED = "unloaded"
"""包状态：已卸载（按产品清理后写入）。"""

PACKAGE_STATUSES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (PACKAGE_STATUS_LOADED, PACKAGE_STATUS_OUTDATED, PACKAGE_STATUS_UNLOADED)
)
"""包状态全集（插入序）。"""

PACKAGE_SCHEMA_VERSION = 1
"""当前接受的帮助包格式版本。"""

GENERATED_BY_MANUAL = "manual"
"""内容生成方式：人工。"""

GENERATED_BY_AI = "ai"
"""内容生成方式：AI 草稿。"""

GENERATED_BY_VALUES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (GENERATED_BY_MANUAL, GENERATED_BY_AI)
)
"""内容生成方式全集（插入序）。"""

FEEDBACK_HELPFUL = "helpful"
"""阅读反馈：有帮助。"""

FEEDBACK_UNHELPFUL = "unhelpful"
"""阅读反馈：无帮助。"""

FEEDBACK_VALUES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList((FEEDBACK_HELPFUL, FEEDBACK_UNHELPFUL))
"""阅读反馈类型全集（业务闭集，插入序）。"""


def source_for_product(product_key: str) -> str:
    """按产品键派生文章来源。

    Args:
        product_key: 帮助包产品键。

    Returns:
        str: `platform` 为 builtin，其余为 product。
    """
    return ARTICLE_SOURCE_BUILTIN if product_key == PLATFORM_PRODUCT_KEY else ARTICLE_SOURCE_PRODUCT
