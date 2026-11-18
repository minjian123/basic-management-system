"""帮助反馈与统计：防重复 / 可改投 / 计数 / 帮助率（Kiwi 2529）。"""

from __future__ import annotations

from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.testing.namespace import Namespace
from bms_platform.domains.help.services.statistics import HelpStatisticsService

from ._support import prepare

pytestmark = pytest.mark.kiwi_id(2529)

_ARTICLES = "/api/v1/help/manage/articles"
_CATEGORIES = "/api/v1/help/manage/categories"
_STATISTICS = "/api/v1/help/manage/statistics"


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


async def _published(client: AsyncClient, ns: Namespace, suffix: str = "fb") -> tuple[int, int]:
    """新建分类与已发布文章，返回（分类主键, 文章主键）。"""
    category = _body(await client.post(_CATEGORIES, json={"name": f"{ns.prefix}_{suffix}_cat"}))
    assert category["code"] == 0
    category_id = int(category["data"]["id"])
    article = _body(
        await client.post(
            _ARTICLES,
            json={
                "category_id": category_id,
                "title": f"{ns.prefix}_{suffix}_文章",
                "content": "<p>正文</p>",
                "status": "published",
            },
        )
    )
    assert article["code"] == 0
    return category_id, int(article["data"]["id"])


async def test_feedback_upsert_and_counts(client: AsyncClient, ns: Namespace) -> None:
    """首次有帮助 +1；同值重投 changed=false；改投交换两侧计数。"""
    _category_id, article_id = await _published(client, ns)
    first = _body(
        await client.post(
            f"/api/v1/help/articles/{article_id}/feedback",
            json={"feedback": "helpful", "comment": "解决了问题"},
        )
    )
    assert first["code"] == 0
    assert first["data"] == {
        "feedback": "helpful",
        "comment": "解决了问题",
        "helpful_count": 1,
        "unhelpful_count": 0,
        "changed": True,
    }

    repeated = _body(await client.post(f"/api/v1/help/articles/{article_id}/feedback", json={"feedback": "helpful"}))
    assert repeated["code"] == 0
    assert repeated["data"]["changed"] is False
    assert repeated["data"]["helpful_count"] == 1

    switched = _body(await client.post(f"/api/v1/help/articles/{article_id}/feedback", json={"feedback": "unhelpful"}))
    assert switched["code"] == 0
    assert switched["data"]["changed"] is True
    assert switched["data"]["helpful_count"] == 0
    assert switched["data"]["unhelpful_count"] == 1

    detail = _body(await client.get(f"/api/v1/help/articles/{article_id}"))
    assert detail["data"]["my_feedback"] == "unhelpful"
    assert detail["data"]["unhelpful_count"] == 1


async def test_feedback_validation(client: AsyncClient, ns: Namespace) -> None:
    """反馈类型非法 40020；评论超长由请求模型拒绝（10001）；文章不可见 40016。"""
    _category_id, article_id = await _published(client, ns)
    invalid = _body(await client.post(f"/api/v1/help/articles/{article_id}/feedback", json={"feedback": "maybe"}))
    assert invalid["code"] == 40020
    too_long = _body(
        await client.post(
            f"/api/v1/help/articles/{article_id}/feedback",
            json={"feedback": "helpful", "comment": "x" * 501},
        )
    )
    assert too_long["code"] == 10001
    assert (await client.post("/api/v1/help/articles/999999/feedback", json={"feedback": "helpful"})).json()[
        "code"
    ] == 40016


async def test_statistics_rates_and_grouping(client: AsyncClient, ns: Namespace) -> None:
    """文章 / 分类两种分组；帮助率 = helpful/(helpful+unhelpful)，无反馈为 null。"""
    category_id, article_id = await _published(client, ns, "stat")
    await client.get(f"/api/v1/help/articles/{article_id}")
    await client.post(f"/api/v1/help/articles/{article_id}/feedback", json={"feedback": "helpful"})

    article_view = _body(await client.get(_STATISTICS, params={"group_by": "article", "category_id": category_id}))
    assert article_view["code"] == 0
    data = article_view["data"]
    assert data["group_by"] == "article"
    assert data["summary"]["article_count"] >= 1
    assert data["summary"]["helpful_count"] >= 1
    row = next(item for item in data["articles"] if int(item["article_id"]) == article_id)
    assert row["helpful_count"] == 1
    assert row["unhelpful_count"] == 0
    assert row["helpful_rate"] == 1.0
    assert row["feedback_rate"] is not None

    category_view = _body(await client.get(_STATISTICS, params={"group_by": "category", "category_id": category_id}))
    assert category_view["code"] == 0
    category_data = category_view["data"]
    assert category_data["group_by"] == "category"
    assert category_data["articles"] == []
    category_row = next(item for item in category_data["categories"] if int(item["category_id"]) == category_id)
    assert category_row["article_count"] == 1
    assert category_row["published_count"] == 1
    assert category_row["helpful_rate"] == 1.0

    no_feedback_view = _body(await client.get(_STATISTICS, params={"group_by": "article", "keyword": "不存在的关键字"}))
    assert no_feedback_view["data"]["total"] == 0


async def test_statistics_service_rejects_bad_params() -> None:
    """分组维度非法 / 每页超限由服务层拒绝（10001）。"""
    service = HelpStatisticsService(session=cast("DbSession", object()))
    with pytest.raises(ParamError):
        await service.load(group_by="bad", category_id=None, keyword=None, page=1, size=20)
    with pytest.raises(ParamError):
        await service.load(group_by="article", category_id=None, keyword=None, page=1, size=201)
