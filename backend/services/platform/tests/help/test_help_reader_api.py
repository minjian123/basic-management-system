"""帮助读者面：可见性 / 置顶 / 停用分类 / 阅读计数去重 / 分页 / 分类树（Kiwi 2529）。"""

from __future__ import annotations

from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.models.platform.help import SysHelpArticle
from bms_core.testing.namespace import Namespace
from bms_platform.domains.help.services.reader import HelpReaderService, summary_of
from tests_support.help import seed_article, tenant_url

from ._support import prepare

pytestmark = pytest.mark.kiwi_id(2529)

_ARTICLES = "/api/v1/help/manage/articles"
_CATEGORIES = "/api/v1/help/manage/categories"
_READER_ARTICLES = "/api/v1/help/articles"
_READER_CATEGORIES = "/api/v1/help/categories"


def _body(response: Any) -> Any:
    """取响应体。"""
    return response.json()


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """准备权限主体与帮助表。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()


async def _category(client: AsyncClient, ns: Namespace, suffix: str = "cat") -> int:
    """新建分类并返回主键。"""
    response = _body(await client.post(_CATEGORIES, json={"name": f"{ns.prefix}_{suffix}"}))
    assert response["code"] == 0
    return int(response["data"]["id"])


async def _publish(client: AsyncClient, category_id: int, title: str, **extra: object) -> int:
    """新建并发布一篇文章，返回主键。"""
    response = _body(
        await client.post(
            _ARTICLES,
            json={
                "category_id": category_id,
                "title": title,
                "content": "<p>读者面正文</p>",
                "status": "published",
                **extra,
            },
        )
    )
    assert response["code"] == 0
    return int(response["data"]["id"])


def _find(nodes: object, category_id: int) -> Any:
    """在树中按主键找节点。"""
    for node in cast("list[Any]", nodes):
        if int(node["id"]) == category_id:
            return node
        found = _find(node["children"], category_id)
        if found is not None:
            return found
    return None


async def test_reader_visibility_by_status(client: AsyncClient, ns: Namespace) -> None:
    """发布可见；草稿 / 下架列表不含且详情 40016。"""
    category_id = await _category(client, ns)
    published_id = await _publish(client, category_id, f"{ns.prefix}_可见")
    draft = _body(
        await client.post(
            _ARTICLES,
            json={"category_id": category_id, "title": f"{ns.prefix}_草稿", "content": "<p>正文</p>"},
        )
    )
    assert draft["code"] == 0
    draft_id = int(draft["data"]["id"])
    offline_id = await seed_article(tenant_url(), category_id=category_id, title=f"{ns.prefix}_下架", status="offline")

    page = _body(await client.get(_READER_ARTICLES, params={"category_id": category_id}))
    assert page["code"] == 0
    ids = [int(item["id"]) for item in page["data"]["list"]]
    assert published_id in ids
    assert draft_id not in ids
    assert offline_id not in ids
    assert page["data"]["total"] == 1

    assert (await client.get(f"{_READER_ARTICLES}/{draft_id}")).json()["code"] == 40016
    assert (await client.get(f"{_READER_ARTICLES}/{offline_id}")).json()["code"] == 40016


async def test_reader_list_top_first(client: AsyncClient, ns: Namespace) -> None:
    """置顶文章排在前面。"""
    category_id = await _category(client, ns)
    normal_id = await _publish(client, category_id, f"{ns.prefix}_普通")
    top_id = await _publish(client, category_id, f"{ns.prefix}_置顶", is_top=True)
    page = _body(await client.get(_READER_ARTICLES, params={"category_id": category_id}))
    ids = [int(item["id"]) for item in page["data"]["list"]]
    assert ids[0] == top_id
    assert normal_id in ids


async def test_disabled_category_hides_from_list_keeps_detail(client: AsyncClient, ns: Namespace) -> None:
    """分类停用：树与列表不显示，详情仍可读。"""
    category_id = await _category(client, ns, "disabled")
    assert (await client.put(f"{_CATEGORIES}/{category_id}", json={"status": "disabled"})).json()["code"] == 0
    article_id = await _publish(client, category_id, f"{ns.prefix}_停用分类文章")

    page = _body(await client.get(_READER_ARTICLES, params={"category_id": category_id}))
    assert page["data"]["total"] == 0
    tree = _body(await client.get(_READER_CATEGORIES))["data"]
    assert _find(tree["items"], category_id) is None
    detail = _body(await client.get(f"{_READER_ARTICLES}/{article_id}"))
    assert detail["code"] == 0


async def test_view_count_dedup(client: AsyncClient, ns: Namespace) -> None:
    """同用户同文章 60 秒内只计一次阅读。"""
    category_id = await _category(client, ns)
    article_id = await _publish(client, category_id, f"{ns.prefix}_阅读")
    first = _body(await client.get(f"{_READER_ARTICLES}/{article_id}"))["data"]
    second = _body(await client.get(f"{_READER_ARTICLES}/{article_id}"))["data"]
    assert first["view_count"] == 1
    assert second["view_count"] == 1


async def test_reader_pagination(client: AsyncClient, ns: Namespace) -> None:
    """分页：total 为筛选内总数，size 控制单页。"""
    category_id = await _category(client, ns)
    await _publish(client, category_id, f"{ns.prefix}_分页甲")
    await _publish(client, category_id, f"{ns.prefix}_分页乙")
    page = _body(await client.get(_READER_ARTICLES, params={"category_id": category_id, "size": 1}))
    assert page["data"]["total"] == 2
    assert len(page["data"]["list"]) == 1
    unfiltered = _body(await client.get(_READER_ARTICLES))
    assert unfiltered["code"] == 0
    assert unfiltered["data"]["total"] >= 2


async def test_reader_category_tree_counts(client: AsyncClient, ns: Namespace) -> None:
    """分类树含子孙已发布文章数；停用分类不出现。"""
    root_id = await _category(client, ns, "tree")
    child = _body(await client.post(_CATEGORIES, json={"name": f"{ns.prefix}_tree_child", "parent_id": root_id}))
    assert child["code"] == 0
    child_id = int(child["data"]["id"])
    await _publish(client, root_id, f"{ns.prefix}_树甲")
    await _publish(client, child_id, f"{ns.prefix}_树乙")

    tree = _body(await client.get(_READER_CATEGORIES))["data"]
    node = _find(tree["items"], root_id)
    assert node is not None
    assert node["published_count"] == 1
    assert node["subtree_published_count"] == 2
    child_node = _find(node["children"], child_id)
    assert child_node is not None
    assert child_node["published_count"] == 1


class _BrokenCache(CacheRegion):
    """不可用缓存替身（读写均抛 `RedisUnavailableError`）。"""

    @property
    def domain(self) -> str:
        """业务域。"""
        return "broken"

    def get(self, key: str) -> object | None:
        """读缓存（恒失败）。"""
        raise RedisUnavailableError("cache down")

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（恒失败）。"""
        raise RedisUnavailableError("cache down")

    def delete(self, key: str) -> bool:
        """删缓存（恒失败）。"""
        raise RedisUnavailableError("cache down")

    def get_global_version(self) -> int:
        """全局版本号。"""
        return 0

    async def aget(self, key: str) -> object | None:
        """异步读（恒失败）。"""
        raise RedisUnavailableError("cache down")

    async def aset(self, key: str, value: object, ttl: int | None = None) -> None:
        """异步写（恒失败）。"""
        raise RedisUnavailableError("cache down")

    async def aincrease(self, key: str) -> int:
        """原子自增（恒失败）。"""
        raise RedisUnavailableError("cache down")


async def test_view_dedup_cache_unavailable_counts_each_time() -> None:
    """缓存不可用时降级按次计数（不阻断阅读）。"""
    service = HelpReaderService(
        session=cast("DbSession", object()),
        uow=cast("UnitOfWork", object()),
        cache=_BrokenCache(),
        locale="zh-CN",
        default_locale="zh-CN",
    )
    assert await service.should_count_view(user_id=1, article_id=1) is True
    assert await service.should_count_view(user_id=1, article_id=1) is True


def test_localized_fallbacks() -> None:
    """语言回退：无附表 / 无匹配 → 主表快照；默认语言行优先命中。"""
    service = HelpReaderService(
        session=cast("DbSession", object()),
        uow=cast("UnitOfWork", object()),
        cache=MemoryCacheRegion(),
        locale="fr-FR",
        default_locale="en-US",
    )
    row = SysHelpArticle(category_id=1, title="主表标题", content="<p>主表正文</p>")
    assert service._localized(row, None) == ("主表标题", "<p>主表正文</p>")  # pyright: ignore[reportPrivateUsage]
    empty: ConcurrentStableFrozenDict[str, tuple[str, str]] = ConcurrentStableFrozenDict()
    assert service._localized(row, empty) == ("主表标题", "<p>主表正文</p>")  # pyright: ignore[reportPrivateUsage]
    no_match: ConcurrentStableFrozenDict[str, tuple[str, str]] = ConcurrentStableFrozenDict(
        {"zh-CN": ("中文", "<p>中文</p>")}
    )
    assert service._localized(row, no_match) == ("主表标题", "<p>主表正文</p>")  # pyright: ignore[reportPrivateUsage]
    default_hit: ConcurrentStableFrozenDict[str, tuple[str, str]] = ConcurrentStableFrozenDict(
        {"en-US": ("English", "<p>English</p>")}
    )
    assert service._localized(row, default_hit) == ("English", "<p>English</p>")  # pyright: ignore[reportPrivateUsage]


def testsummary_of_empty_and_truncated() -> None:
    """摘要：空正文空串；超长截断并加省略号。"""
    assert summary_of("") == ""
    assert summary_of("<p>短文本</p>") == "短文本"
    long_text = summary_of("<p>" + "长" * 200 + "</p>")
    assert long_text.endswith("…")
    assert len(long_text) == 121
