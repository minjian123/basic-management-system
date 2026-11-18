"""帮助内容缓存：解析结果的键、编解码与降级读写（12_01）。

口径（详细设计 §5.9）：

- **版本键**：`bms:{tenant}:help:content_version`，租户级内容版本号（`aincrease`，不过期）。
  分类 / 文章 / 帮助包的写操作递增版本，解析缓存旧键自然失效；
- **解析缓存键**：`bms:{tenant}:help:resolve:v{version}:{locale}:{digest}`，TTL 60 秒；
  `digest` 取候选链（级别 + 锚点）的 SHA-256 前 16 位——候选已由解析侧排好序，同一上下文得到同一键；
- **降级**：缓存读写失败（`BizError` / `OSError`）一律按未命中处理并告警，不阻断页面；
  缓存值只存结构与非文案字段（文案已按请求语言解析，随 locale 进键）；
- **脏载荷**：解码失败返回 `None`，由调用方回源重建（与 08_02 锚点索引同口径）。
"""

from __future__ import annotations

import hashlib
from typing import cast

from bms_core.cache.base import CacheRegion, build_cache_key
from bms_core.core.concurrent import (
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import BizError
from bms_core.core.logging import get_logger
from bms_core.help.content import (
    HelpAnchorCandidate,
    HelpArticle,
    HelpArticleSummary,
    HelpCategory,
    HelpContentResult,
    HelpLevel,
)

__all__ = [
    "CONTENT_VERSION_TTL",
    "RESOLVE_CACHE_TTL",
    "bump_content_version",
    "content_version",
    "content_version_key",
    "decode_help_result",
    "encode_help_result",
    "load_cached_result",
    "resolve_cache_key",
    "store_cached_result",
]

_LOGGER = get_logger("bms.help")

CACHE_DOMAIN = "help"
"""帮助内容缓存域（key 形如 `bms:{tenant}:help:{业务键}`）。"""

CONTENT_VERSION_TTL = 0
"""版本键不过期（计数器到期回退会让旧版本键被复用）。"""

RESOLVE_CACHE_TTL = 60
"""解析结果缓存有效期（秒）。"""

_VERSION_BUSINESS_KEY = "content_version"
"""版本键业务段。"""


def content_version_key(*, tenant: str | None) -> str:
    """取租户级内容版本键。

    Args:
        tenant: 租户编码（None 为全局）。

    Returns:
        str: 版本键。
    """
    return build_cache_key(tenant=tenant, domain=CACHE_DOMAIN, business_key=_VERSION_BUSINESS_KEY)


async def content_version(cache: CacheRegion, *, tenant: str | None) -> int:
    """读租户内容版本号（缓存不可用 / 未初始化按 0）。

    Args:
        cache: 缓存 Region。
        tenant: 租户编码。

    Returns:
        int: 版本号。
    """
    try:
        raw = await cache.aget(content_version_key(tenant=tenant))
    except (BizError, OSError) as exc:
        _LOGGER.warning("help_content_version_read_failed", error=str(exc))
        return 0
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0


async def bump_content_version(cache: CacheRegion, *, tenant: str | None) -> int | None:
    """递增租户内容版本号（失败只告警，不影响业务写）。

    Args:
        cache: 缓存 Region。
        tenant: 租户编码。

    Returns:
        int | None: 新版本号；缓存不可用返回 None。
    """
    try:
        return await cache.aincrease(content_version_key(tenant=tenant))
    except (BizError, OSError) as exc:
        _LOGGER.warning("help_content_version_bump_failed", error=str(exc))
        return None


def resolve_cache_key(
    *,
    tenant: str | None,
    version: int,
    locale: str,
    candidates: ConcurrentStableList[HelpAnchorCandidate],
) -> str:
    """构造解析结果缓存键。

    Args:
        tenant: 租户编码。
        version: 内容版本号。
        locale: 请求语言。
        candidates: 有序候选链。

    Returns:
        str: 缓存键。
    """
    digest = _candidates_digest(candidates)
    return build_cache_key(
        tenant=tenant,
        domain=CACHE_DOMAIN,
        business_key=f"resolve:v{version}:{locale}:{digest}",
    )


def _candidates_digest(candidates: ConcurrentStableList[HelpAnchorCandidate]) -> str:
    """把候选链压成稳定摘要（16 位十六进制）。

    Args:
        candidates: 有序候选链。

    Returns:
        str: 摘要。
    """
    parts: ConcurrentStableList[str] = ConcurrentStableList(
        f"{candidate.level.value}:{candidate.help_key or ''}" for candidate in candidates
    )
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def encode_help_result(result: HelpContentResult) -> object:
    """把解析结果编码为 JSON 可往返结构（Redis Region 以 JSON 存取）。

    Args:
        result: 解析结果。

    Returns:
        object: 内置 dict / list / 标量结构。
    """
    article = result.article
    return {
        "level": result.level.value if result.level is not None else None,
        "help_key": result.help_key,
        "article": (
            None
            if article is None
            else {
                "article_id": article.article_id,
                "title": article.title,
                "content": article.content,
                "source": article.source,
            }
        ),
        "related": [
            {"article_id": item.article_id, "title": item.title, "source": item.source} for item in result.related
        ],
        "categories": [
            {"category_id": item.category_id, "name": item.name, "path": item.path} for item in result.categories
        ],
    }


def decode_help_result(payload: object) -> HelpContentResult | None:
    """把缓存载荷解码为解析结果（结构不符返回 None，由调用方重建）。

    Args:
        payload: 缓存读出的结构。

    Returns:
        HelpContentResult | None: 解析结果；脏载荷为 None。
    """
    if not isinstance(payload, dict):
        return None
    data = cast("dict[str, object]", payload)
    level = _level_of(data.get("level"))
    if data.get("level") is not None and level is None:
        return None
    help_key = data.get("help_key")
    if help_key is not None and not isinstance(help_key, str):
        return None
    article = _article_of(data.get("article"))
    if data.get("article") is not None and article is None:
        return None
    related = _related_of(data.get("related"))
    if related is None:
        return None
    categories = _categories_of(data.get("categories"))
    if categories is None:
        return None
    return HelpContentResult(
        level=level,
        help_key=help_key,
        article=article,
        related=related,
        categories=categories,
    )


def _level_of(value: object) -> HelpLevel | None:
    """把缓存值还原为解析层级（未知值 / 非字符串返回 None）。

    Args:
        value: 缓存值。

    Returns:
        HelpLevel | None: 层级；非法为 None。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        return HelpLevel(value)
    except ValueError:
        return None


def _article_of(value: object) -> HelpArticle | None:
    """把缓存值还原为命中文章（结构不符返回 None）。

    Args:
        value: 缓存值。

    Returns:
        HelpArticle | None: 文章；非法为 None。
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    data = cast("dict[str, object]", value)
    article_id = data.get("article_id")
    title = data.get("title")
    content = data.get("content")
    source = data.get("source")
    if not isinstance(article_id, int) or isinstance(article_id, bool):
        return None
    if not isinstance(title, str) or not isinstance(content, str) or not isinstance(source, str):
        return None
    return HelpArticle(article_id=article_id, title=title, content=content, source=source)


def _related_of(value: object) -> ConcurrentStableFrozenList[HelpArticleSummary] | None:
    """把缓存值还原为相关内容清单（结构不符返回 None）。

    Args:
        value: 缓存值。

    Returns:
        ConcurrentStableFrozenList[HelpArticleSummary] | None: 摘要清单；非法为 None。
    """
    if not isinstance(value, list):
        return None
    items: ConcurrentStableList[HelpArticleSummary] = ConcurrentStableList()
    for entry in cast("list[object]", value):
        if not isinstance(entry, dict):
            return None
        data = cast("dict[str, object]", entry)
        article_id = data.get("article_id")
        title = data.get("title")
        source = data.get("source")
        if not isinstance(article_id, int) or isinstance(article_id, bool):
            return None
        if not isinstance(title, str) or not isinstance(source, str):
            return None
        items.add(HelpArticleSummary(article_id=article_id, title=title, source=source))
    return ConcurrentStableFrozenList(items)


def _categories_of(value: object) -> ConcurrentStableFrozenList[HelpCategory] | None:
    """把缓存值还原为分类清单（结构不符返回 None）。

    Args:
        value: 缓存值。

    Returns:
        ConcurrentStableFrozenList[HelpCategory] | None: 分类清单；非法为 None。
    """
    if not isinstance(value, list):
        return None
    items: ConcurrentStableList[HelpCategory] = ConcurrentStableList()
    for entry in cast("list[object]", value):
        if not isinstance(entry, dict):
            return None
        data = cast("dict[str, object]", entry)
        category_id = data.get("category_id")
        name = data.get("name")
        path = data.get("path")
        if not isinstance(category_id, int) or isinstance(category_id, bool):
            return None
        if not isinstance(name, str) or not isinstance(path, str):
            return None
        items.add(HelpCategory(category_id=category_id, name=name, path=path))
    return ConcurrentStableFrozenList(items)


async def load_cached_result(cache: CacheRegion, key: str) -> HelpContentResult | None:
    """读缓存解析结果（失败 / 脏载荷返回 None）。

    Args:
        cache: 缓存 Region。
        key: 缓存键。

    Returns:
        HelpContentResult | None: 缓存的解析结果；未命中为 None。
    """
    try:
        payload = await cache.aget(key)
    except (BizError, OSError) as exc:
        _LOGGER.warning("help_content_cache_get_failed", error=str(exc))
        return None
    if payload is None:
        return None
    return decode_help_result(payload)


async def store_cached_result(cache: CacheRegion, key: str, result: HelpContentResult) -> None:
    """写解析结果缓存（失败只告警）。

    Args:
        cache: 缓存 Region。
        key: 缓存键。
        result: 解析结果。
    """
    try:
        await cache.aset(key, encode_help_result(result), RESOLVE_CACHE_TTL)
    except (BizError, OSError) as exc:
        _LOGGER.warning("help_content_cache_set_failed", error=str(exc))
