"""帮助文章管理面：CRUD / 状态机 / 清洗 / 多语言 / AI 校验 / 包来源 / 目标（Kiwi 2529）。"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.testing.namespace import Namespace
from bms_platform.domains.help.services import maintenance as maintenance_module
from tests_support.help import (
    delete_platform_action,
    platform_url,
    seed_article,
    seed_platform_action,
    tenant_url,
)

from ._support import prepare

pytestmark = pytest.mark.kiwi_id(2529)

_ARTICLES = "/api/v1/help/manage/articles"
_CATEGORIES = "/api/v1/help/manage/categories"


def _body(response: Any) -> Any:
    """取响应体。"""
    return response.json()


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """准备权限主体与帮助表，并固定语言清单（避免其他用例改写共享库语言状态）。

    Args:
        tenant_db: 共享测试租户库连接串。
        monkeypatch: pytest monkeypatch 夹具。
    """
    assert tenant_db
    await prepare()

    async def _default_locale(session: object) -> str:
        """固定默认语言。"""
        del session
        return "zh-CN"

    async def _locales(session: object) -> ConcurrentStableFrozenList[str]:
        """固定启用语言清单。"""
        del session
        return ConcurrentStableFrozenList(("zh-CN", "en-US"))

    monkeypatch.setattr(maintenance_module, "load_help_default_locale", _default_locale)
    monkeypatch.setattr(maintenance_module, "load_help_locales", _locales)


async def _category(client: AsyncClient, ns: Namespace, suffix: str = "cat") -> int:
    """新建一个分类并返回主键。"""
    response = _body(await client.post(_CATEGORIES, json={"name": f"{ns.prefix}_{suffix}"}))
    assert response["code"] == 0
    return int(response["data"]["id"])


async def _create(client: AsyncClient, category_id: int, title: str, **extra: object) -> Any:
    """新建文章并返回响应体。"""
    payload = {"category_id": category_id, "title": title, "content": "<p>正文</p>", **extra}
    return _body(await client.post(_ARTICLES, json=payload))


async def test_article_crud_and_state_machine(client: AsyncClient, ns: Namespace) -> None:
    """新建草稿 → 发布 → 重复发布拒 → 下架 → 重复下架拒 → 重新发布 → 编辑 → 删除。"""
    category_id = await _category(client, ns)
    created = await _create(client, category_id, f"{ns.prefix}_文章", content="<p>正文</p>")
    assert created["code"] == 0
    article = created["data"]
    article_id = int(article["id"])
    assert article["status"] == "draft"
    assert article["source"] == "tenant"
    assert article["publish_at"] is None

    published = _body(await client.post(f"{_ARTICLES}/{article_id}/publish"))
    assert published["code"] == 0
    assert published["data"]["status"] == "published"
    assert published["data"]["publish_at"] is not None

    assert (await client.post(f"{_ARTICLES}/{article_id}/publish")).json()["code"] == 40017

    offline = _body(await client.post(f"{_ARTICLES}/{article_id}/offline"))
    assert offline["code"] == 0
    assert offline["data"]["status"] == "offline"
    assert (await client.post(f"{_ARTICLES}/{article_id}/offline")).json()["code"] == 40017

    republished = _body(await client.post(f"{_ARTICLES}/{article_id}/publish"))
    assert republished["code"] == 0

    updated = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"title": f"{ns.prefix}_改名"}))
    assert updated["code"] == 0
    assert updated["data"]["title"] == f"{ns.prefix}_改名"
    assert updated["data"]["status"] == "published"

    deleted = _body(await client.delete(f"{_ARTICLES}/{article_id}"))
    assert deleted["code"] == 0
    assert deleted["data"]["applied"] is True
    assert (await client.get(f"{_ARTICLES}/{article_id}")).json()["code"] == 40016

    draft_id = int((await _create(client, category_id, f"{ns.prefix}_待删草稿"))["data"]["id"])
    assert (await client.delete(f"{_ARTICLES}/{draft_id}")).json()["code"] == 0


async def test_edit_draft_to_offline_rejected(client: AsyncClient, ns: Namespace) -> None:
    """草稿不能靠编辑直接变下架（40017）。"""
    category_id = await _category(client, ns)
    article_id = int((await _create(client, category_id, f"{ns.prefix}_草稿"))["data"]["id"])
    response = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"status": "offline"}))
    assert response["code"] == 40017


async def test_article_update_fields_and_edit_transitions(client: AsyncClient, ns: Namespace) -> None:
    """编辑：分类 / 置顶 / 目标 / 状态迁移（草稿→发布→下架，同态草稿允许）。"""
    category_id = await _category(client, ns, "upd_a")
    other_category = await _category(client, ns, "upd_b")
    article_id = int((await _create(client, category_id, f"{ns.prefix}_编辑"))["data"]["id"])

    same_draft = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"status": "draft"}))
    assert same_draft["code"] == 0

    edited = _body(
        await client.put(
            f"{_ARTICLES}/{article_id}",
            json={
                "category_id": other_category,
                "is_top": True,
                "title": f"{ns.prefix}_编辑改名",
                "targets": [{"type": "global"}],
            },
        )
    )
    assert edited["code"] == 0
    assert int(edited["data"]["category_id"]) == other_category
    assert edited["data"]["is_top"] is True
    assert [item["type"] for item in edited["data"]["targets"]] == ["global"]

    published = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"status": "published"}))
    assert published["code"] == 0
    assert published["data"]["status"] == "published"

    offline = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"status": "offline"}))
    assert offline["code"] == 0
    assert offline["data"]["status"] == "offline"

    action_code = f"{ns.prefix}_upd_act"
    help_key = f"platform::::{action_code}"
    await seed_platform_action(platform_url(), code=action_code, help_key=help_key)
    try:
        republished = _body(
            await client.put(
                f"{_ARTICLES}/{article_id}",
                json={"status": "published", "targets": [{"type": "global"}, {"type": "action", "key": help_key}]},
            )
        )
        assert republished["code"] == 0
        assert republished["data"]["status"] == "published"
        assert len(republished["data"]["targets"]) == 2
    finally:
        await delete_platform_action(platform_url(), action_code)
        await client.delete(f"{_ARTICLES}/{article_id}")


async def test_publish_rejects_empty_content(client: AsyncClient, ns: Namespace) -> None:
    """发布时正文为空被拒（40018）；草稿允许空正文保存。"""
    category_id = await _category(client, ns)
    article_id = await seed_article(
        tenant_url(),
        category_id=category_id,
        title=f"{ns.prefix}_空正文草稿",
        content="<p> </p>",
        status="draft",
    )
    response = _body(await client.post(f"{_ARTICLES}/{article_id}/publish"))
    assert response["code"] == 40018


async def test_article_targets_conflict_with_anchor(client: AsyncClient, ns: Namespace) -> None:
    """非全局目标：首个发布成功（事件带走锚点键），同目标再发布被拒（40019）。"""
    action_code = f"{ns.prefix}_act"
    help_key = f"platform::::{action_code}"
    await seed_platform_action(platform_url(), code=action_code, help_key=help_key)
    first_id = 0
    try:
        category_id = await _category(client, ns)
        target = {"type": "action", "key": help_key}
        first = await _create(
            client,
            category_id,
            f"{ns.prefix}_锚点甲",
            status="published",
            targets=[{"type": "global"}, target],
        )
        assert first["code"] == 0
        first_id = int(first["data"]["id"])
        second = await _create(
            client,
            category_id,
            f"{ns.prefix}_锚点乙",
            status="published",
            targets=[target],
        )
        assert second["code"] == 40019
    finally:
        if first_id:
            await client.delete(f"{_ARTICLES}/{first_id}")
        await delete_platform_action(platform_url(), action_code)


async def test_article_sanitizes_html(client: AsyncClient, ns: Namespace) -> None:
    """正文入库前白名单清洗：脚本 / 事件属性剥离，白名单标签保留。"""
    category_id = await _category(client, ns)
    raw = '<p>保留</p><script>alert(1)</script><img src="x" onerror="alert(2)">'
    created = await _create(client, category_id, f"{ns.prefix}_清洗", content=raw)
    assert created["code"] == 0
    content = created["data"]["content"]
    assert "<script" not in content
    assert "onerror" not in content
    assert "<p>保留</p>" in content


async def test_article_content_validation(client: AsyncClient, ns: Namespace) -> None:
    """空正文 / 超限正文返回 40018；超长标题由请求模型拒绝（10001）。"""
    category_id = await _category(client, ns)
    empty = await _create(client, category_id, f"{ns.prefix}_空正文", content="<p> </p>")
    assert empty["code"] == 40018
    oversized = await _create(client, category_id, f"{ns.prefix}_超限正文", content="<p>" + "a" * 70000 + "</p>")
    assert oversized["code"] == 40018
    long_title = await _create(client, category_id, "长" * 300, content="<p>正文</p>")
    assert long_title["code"] == 10001


async def test_article_i18n_write_and_locale_validation(client: AsyncClient, ns: Namespace) -> None:
    """多语言写入 / 非法语言拒绝 / 读者面按请求语言回退。"""
    category_id = await _category(client, ns)
    created = await _create(
        client,
        category_id,
        f"{ns.prefix}_默认中文",
        content="<p>中文正文</p>",
        i18n={"en-US": {"title": f"{ns.prefix}_English", "content": "<p>English body</p>"}},
    )
    assert created["code"] == 0
    article_id = int(created["data"]["id"])
    assert set(created["data"]["i18n"]) == {"zh-CN", "en-US"}
    assert created["data"]["title"] == f"{ns.prefix}_默认中文"

    invalid = await _create(
        client,
        category_id,
        f"{ns.prefix}_非法语言",
        i18n={"xx-XX": {"title": "x", "content": "<p>x</p>"}},
    )
    assert invalid["code"] == 40022

    assert (await client.post(f"{_ARTICLES}/{article_id}/publish")).json()["code"] == 0
    english = _body(await client.get(f"/api/v1/help/articles/{article_id}", headers={"Accept-Language": "en-US"}))
    assert english["code"] == 0
    assert english["data"]["title"] == f"{ns.prefix}_English"
    assert "English body" in english["data"]["content"]


async def test_ai_article_requires_review(client: AsyncClient, ns: Namespace) -> None:
    """generated_by=ai 未填审核人不得发布；manual 不得带模型。"""
    category_id = await _category(client, ns)
    rejected = await _create(
        client,
        category_id,
        f"{ns.prefix}_AI直发",
        content="<p>正文</p>",
        status="published",
        generated_by="ai",
        ai_model="model-x",
    )
    assert rejected["code"] == 40018

    draft = await _create(
        client,
        category_id,
        f"{ns.prefix}_AI草稿",
        content="<p>正文</p>",
        generated_by="ai",
        ai_model="model-x",
    )
    assert draft["code"] == 0
    article_id = int(draft["data"]["id"])
    assert (await client.post(f"{_ARTICLES}/{article_id}/publish")).json()["code"] == 40018

    reviewed = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"reviewed_by": "审核员甲"}))
    assert reviewed["code"] == 0
    assert reviewed["data"]["reviewed_by"] == "审核员甲"
    assert (await client.post(f"{_ARTICLES}/{article_id}/publish")).json()["code"] == 0

    manual_with_model = await _create(
        client,
        category_id,
        f"{ns.prefix}_人工带模型",
        content="<p>正文</p>",
        ai_model="model-x",
    )
    assert manual_with_model["code"] == 40018


async def test_package_article_sets_local_override_and_cannot_delete(client: AsyncClient, ns: Namespace) -> None:
    """包来源文章编辑自动本地覆盖；删除被拒（引导下架）。"""
    category_id = await _category(client, ns)
    article_id = await seed_article(
        tenant_url(),
        category_id=category_id,
        title=f"{ns.prefix}_包文章",
        source="product",
        status="published",
    )
    updated = _body(await client.put(f"{_ARTICLES}/{article_id}", json={"title": f"{ns.prefix}_包文章改"}))
    assert updated["code"] == 0
    assert updated["data"]["local_override"] is True
    assert updated["data"]["source"] == "product"
    assert (await client.delete(f"{_ARTICLES}/{article_id}")).json()["code"] == 40017
    assert (await client.post(f"{_ARTICLES}/{article_id}/offline")).json()["code"] == 0


async def test_article_targets_validation(client: AsyncClient, ns: Namespace) -> None:
    """目标类型 / 形态 / 重复 / 锚点不存在分别命中 40018 / 40019 / 40008。"""
    category_id = await _category(client, ns)
    bad_type = await _create(
        client,
        category_id,
        f"{ns.prefix}_目标类型",
        content="<p>正文</p>",
        targets=[{"type": "bad", "key": "x"}],
    )
    assert bad_type["code"] == 40018

    bad_shape = await _create(
        client,
        category_id,
        f"{ns.prefix}_目标形态",
        content="<p>正文</p>",
        targets=[{"type": "module", "key": "platform:sys:user:username:"}],
    )
    assert bad_shape["code"] == 40018

    duplicated = await _create(
        client,
        category_id,
        f"{ns.prefix}_目标重复",
        content="<p>正文</p>",
        targets=[{"type": "global"}, {"type": "global"}],
    )
    assert duplicated["code"] == 40019

    missing_anchor = await _create(
        client,
        category_id,
        f"{ns.prefix}_目标缺失",
        content="<p>正文</p>",
        targets=[{"type": "module", "key": f"platform:{ns.prefix}:::"}],
    )
    assert missing_anchor["code"] == 40008

    empty_key = await _create(
        client,
        category_id,
        f"{ns.prefix}_目标空键",
        content="<p>正文</p>",
        targets=[{"type": "module", "key": ""}],
    )
    assert empty_key["code"] == 40018

    valid_global = await _create(
        client,
        category_id,
        f"{ns.prefix}_全局目标",
        content="<p>正文</p>",
        targets=[{"type": "global"}],
    )
    assert valid_global["code"] == 0


async def test_article_provenance_validation(client: AsyncClient, ns: Namespace) -> None:
    """状态 / 生成方式非法 10001；AI 缺模型 40018。"""
    category_id = await _category(client, ns)
    bad_status = await _create(client, category_id, f"{ns.prefix}_坏状态", status="bad")
    assert bad_status["code"] == 10001
    bad_generator = await _create(client, category_id, f"{ns.prefix}_坏生成方式", generated_by="robot")
    assert bad_generator["code"] == 10001
    ai_without_model = await _create(client, category_id, f"{ns.prefix}_AI缺模型", generated_by="ai")
    assert ai_without_model["code"] == 40018


async def test_article_list_filters(client: AsyncClient, ns: Namespace) -> None:
    """列表按分类 / 状态 / 关键字筛选，分页字段完整。"""
    category_id = await _category(client, ns)
    await _create(client, category_id, f"{ns.prefix}_列表甲")
    await _create(client, category_id, f"{ns.prefix}_列表乙", status="published")
    page = _body(
        await client.get(
            _ARTICLES,
            params={
                "category_id": category_id,
                "status": "draft",
                "source": "tenant",
                "keyword": f"{ns.prefix}_列表",
            },
        )
    )
    assert page["code"] == 0
    assert page["data"]["total"] == 1
    assert page["data"]["list"][0]["status"] == "draft"
    assert page["data"]["page"] == 1
    assert page["data"]["size"] == 20
    unfiltered = _body(await client.get(_ARTICLES))
    assert unfiltered["code"] == 0
    assert unfiltered["data"]["total"] >= 1
