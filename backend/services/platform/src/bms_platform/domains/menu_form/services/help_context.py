"""帮助解析服务（`menu_form` 域读面）：锚点索引 → 五级候选链 → 内容侧 → 响应（08_02）。

- **锚点索引**：按元数据版本号缓存（与 `my_menus` 同源失效），请求期只做内存查表；
- **候选链**：字段 → 动作（按钮 → 动作码兜底）→ 表单 → 模块 → 全局，纯逻辑在 `bms_core/help/context.py`；
- **内容侧**：经 `help_content` 能力域端口取文章 / 相关内容 / 分类，缺省空实现（恒定未命中）；
- **命中判据**：锚点已登记**且**有可展示文章；`button_visible` 恒等于 `matched`。
"""

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.help.content import BaseHelpContentResolver, HelpContentResult
from bms_core.help.context import HelpContextInput, build_help_candidates, has_anchor, resolve_help_context
from bms_core.help.index import load_cached_help_anchor_index
from bms_core.repositories.help_anchor import load_help_anchor_index
from bms_platform.domains.menu_form.schemas.help import (
    HelpArticleItem,
    HelpArticleSummaryItem,
    HelpCategoryItem,
    HelpContextResponse,
)
from bms_platform.services.metadata_cache import metadata_version

__all__ = ["HelpContextService"]


class HelpContextService(BaseFrameworkObject):
    """页面内帮助解析服务（索引缓存 + 候选链 + 内容侧）。"""

    def __init__(self, *, session: DbSession, cache: CacheRegion, resolver: BaseHelpContentResolver) -> None:
        """初始化。

        Args:
            session: 平台库会话（锚点索引回源）。
            cache: 缓存 Region（锚点索引与元数据版本）。
            resolver: 内容侧解析实现（应用按 `[help_content].provider` 装配）。
        """
        self._session = session
        self._cache = cache
        self._resolver = resolver

    async def resolve(
        self,
        context: HelpContextInput,
        *,
        locale: str,
        ttl: int,
        request: Request | None = None,
    ) -> HelpContextResponse:
        """解析页面内帮助。

        Args:
            context: 解析上下文入参。
            locale: 请求语言标识。
            ttl: 锚点索引缓存有效期（秒）。
            request: 当前请求（透传内容侧实现；可空）。

        Returns:
            HelpContextResponse: 解析结果（未命中时 `matched=false` + 分类列表）。
        """
        version = await metadata_version(self._cache)
        index = await load_cached_help_anchor_index(
            self._cache,
            version=version,
            ttl=ttl,
            build=lambda: load_help_anchor_index(self._session),
        )
        candidates = build_help_candidates(index, context)
        result = await resolve_help_context(
            index=index,
            context=context,
            locale=locale,
            resolver=self._resolver,
            request=request,
            candidates=candidates,
        )
        return _to_response(result, anchor_found=has_anchor(candidates))


def _to_response(result: HelpContentResult, *, anchor_found: bool) -> HelpContextResponse:
    """解析结果 → 接口契约（值对象 → 响应模型）。

    Args:
        result: 内容侧解析结果。
        anchor_found: 候选链中是否存在已登记锚点（页面内按钮显隐判据）。

    Returns:
        HelpContextResponse: 帮助解析响应。
    """
    article = result.article
    return HelpContextResponse(
        matched=result.matched,
        level=result.level.value if result.level is not None else None,
        help_key=result.help_key,
        article=(
            None
            if article is None
            else HelpArticleItem(
                id=article.article_id,
                title=article.title,
                content=article.content,
                source=article.source,
            )
        ),
        related=ConcurrentStableList(
            HelpArticleSummaryItem(id=item.article_id, title=item.title, source=item.source) for item in result.related
        ),
        categories=ConcurrentStableList(
            HelpCategoryItem(id=item.category_id, name=item.name, path=item.path) for item in result.categories
        ),
        button_visible=result.matched,
        anchor_found=anchor_found,
    )
