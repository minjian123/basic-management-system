"""帮助内容侧端口：解析命中的文章、相关内容与分类（08_02）。

帮助机制分三层：**声明面**（元数据上的 `help_key`，08_01）、**装载面**（产品帮助包，08_03）、
**内容面**（分类 / 文章 / 反馈，12_01）。五级解析发生在声明面与内容面之间——本模块只定义
「内容面如何被消费」的契约，不承载文章表、不实现来源优先级，也不决定缓存。

设计口径（见任务 08_02 详细设计 §5.3）：

- 解析侧按「字段 → 动作 → 表单 → 模块 → 全局」排好候选，**按序**交给内容侧；内容侧取首个有
  已发布文章的候选，同锚点多篇按 `builtin > product > tenant` 取一篇、其余放「相关内容」；
- 未命中不是错误：返回空结果（`level` / `help_key` / `article` 均为 `None`、清单为空），
  由调用方据 `article` 是否为空判定按钮显隐；
- 缺省实现为 `null`（恒定未命中），真实实现随帮助内容维护任务接入，本层代码不改。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.config import Settings
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "BaseHelpContentResolver",
    "HelpArticle",
    "HelpArticleSummary",
    "HelpCategory",
    "HelpContentQuery",
    "HelpContentResult",
    "HelpLevel",
    "get_help_content_resolver",
]

HELP_CONTENT_PLUGIN_KEY = "help_content"
"""内容侧能力域插件键（配置段 `[help_content]`）。"""


class HelpLevel(StrEnum):
    """帮助解析层级（由最贴近上下文到最宽，逐级降级）。"""

    FIELD = "field"
    ACTION = "action"
    FORM = "form"
    MODULE = "module"
    GLOBAL = "global"


@dataclass(frozen=True)
class HelpAnchorCandidate(BaseValueObject):
    """一个待探询的解析候选（层级 + 锚点值）。

    Attributes:
        level: 解析层级。
        help_key: 该级锚点值；全局级无元数据锚点，为 `None`。
    """

    level: HelpLevel
    help_key: str | None


@dataclass(frozen=True)
class HelpArticle(BaseValueObject):
    """命中文章（含正文，页面内帮助一次请求即可弹窗）。

    Attributes:
        article_id: 文章主键。
        title: 标题（已按请求语言解析）。
        content: 正文（已清洗 HTML）。
        source: 来源（`builtin` / `product` / `tenant`，内容侧口径）。
    """

    article_id: int
    title: str
    content: str
    source: str


@dataclass(frozen=True)
class HelpArticleSummary(BaseValueObject):
    """文章摘要（「相关内容」列表用，不含正文）。

    Attributes:
        article_id: 文章主键。
        title: 标题。
        source: 来源。
    """

    article_id: int
    title: str
    source: str


@dataclass(frozen=True)
class HelpCategory(BaseValueObject):
    """帮助分类摘要（未命中时前端据此打开分类列表）。

    Attributes:
        category_id: 分类主键。
        name: 分类名（已按请求语言解析）。
        path: 分类路径（`/` 分隔，自根到本节点）。
    """

    category_id: int
    name: str
    path: str


@dataclass(frozen=True)
class HelpContentQuery(BaseValueObject):
    """内容侧解析请求（解析侧已排好候选顺序）。

    Attributes:
        locale: 请求语言标识。
        candidates: 有序候选（首项最贴近当前上下文；末项恒为全局级）。
        module_key: 模块键（内容侧按分类归属取数用；可空）。
        form_key: 表单键（内容侧按分类归属取数用；可空）。
        action_code: 动作码（内容侧按分类归属取数用；可空）。
    """

    locale: str
    candidates: ConcurrentStableFrozenList[HelpAnchorCandidate]
    module_key: str | None = None
    form_key: str | None = None
    action_code: str | None = None


@dataclass(frozen=True)
class HelpContentResult(BaseValueObject):
    """内容侧解析结果；全字段为空表示未命中。

    Attributes:
        level: 命中的解析层级（未命中为 `None`）。
        help_key: 命中的锚点（全局级与未命中均为 `None`）。
        article: 命中文章（未命中为 `None`）。
        related: 同一锚点的其余文章摘要（「相关内容」）。
        categories: 分类摘要（未命中时用于打开分类列表）。
    """

    level: HelpLevel | None = None
    help_key: str | None = None
    article: HelpArticle | None = None
    related: ConcurrentStableFrozenList[HelpArticleSummary] = field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    categories: ConcurrentStableFrozenList[HelpCategory] = field(default_factory=lambda: ConcurrentStableFrozenList())

    @property
    def matched(self) -> bool:
        """是否命中可展示文章（按钮显隐判据）。

        Returns:
            bool: 命中文章为 True。
        """
        return self.article is not None


class BaseHelpContentResolver(BasePluggable, ABC):
    """帮助内容解析契约：按有序候选取首个有已发布文章的锚点。

    实现按环境选择（缺省 `null`）：内容表落地后由帮助内容域提供真实实现，本契约与解析链不变。
    """

    key: str = HELP_CONTENT_PLUGIN_KEY
    plugin_key: str = HELP_CONTENT_PLUGIN_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def resolve(self, query: HelpContentQuery, *, request: Request | None = None) -> HelpContentResult:
        """按候选顺序解析帮助内容。

        Args:
            query: 解析请求（候选有序，末项为全局级）。
            request: 当前请求（实现可按需读取应用装配状态与租户上下文；占位实现忽略）。

        Returns:
            HelpContentResult: 解析结果；无内容返回空结果（不是错误）。
        """


def get_help_content_resolver(request: Request) -> BaseHelpContentResolver:
    """取应用装配的帮助内容解析实现（依赖注入提供者）。

    Args:
        request: 当前请求（读应用配置）。

    Returns:
        BaseHelpContentResolver: 按 `[help_content].provider` 解析的实现（缺省空实现）。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseHelpContentResolver",
        resolve_plugin(
            HELP_CONTENT_PLUGIN_KEY,
            settings.help_content.provider,
            expected_version=BaseHelpContentResolver.contract_version,
        ),
    )
