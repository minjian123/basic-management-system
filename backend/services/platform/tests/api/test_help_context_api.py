"""页面内帮助解析（`GET /api/v1/help/context`）与动态菜单锚点下发（08_02；Kiwi 2521）。

覆盖：五级命中与逐级降级、未命中分类与按钮显隐、多篇相关内容、入参全空只走全局、
字段级需表单键、模块级产品消歧、`my_menus` 四级下发、登录即可与参数非法。
内容侧以依赖覆盖桩模拟（真实文章表归帮助内容维护任务），解析链与契约形状即被测对象。
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.help.content import (
    BaseHelpContentResolver,
    HelpArticle,
    HelpArticleSummary,
    HelpCategory,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
    get_help_content_resolver,
)
from bms_core.testing.namespace import Namespace
from tests_support.permission_admin import setup_min_tenant

_CONTEXT = "/api/v1/help/context"
_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_FIELDS = "/api/v1/fields"
_BUTTONS = "/api/v1/buttons"
_ACTIONS = "/api/v1/actions"
_BUSINESSES = "/api/v1/businesses"
_PERMISSIONS = "/api/v1/permissions"

_FIELD_ARTICLE_ID = 101
_BUTTON_ARTICLE_ID = 102
_ACTION_ARTICLE_ID = 103
_FORM_ARTICLE_ID = 104
_MODULE_ARTICLE_ID = 105
_GLOBAL_ARTICLE_ID = 106


@pytest_asyncio.fixture(autouse=True)
async def permission_engine(tenant_db: str) -> None:
    """真实权限校验所需的租户库（共享租户库）+ 内置系统管理员主体。

    Args:
        tenant_db: 共享租户库连接串。
    """
    await setup_min_tenant(tenant_db)


def _data(response: Any, label: str) -> Any:
    """取统一响应 `data`；失败时把完整响应体写进断言信息。

    Args:
        response: httpx 响应。
        label: 调用标识。

    Returns:
        Any: `data` 字段。
    """
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


@dataclass(frozen=True)
class _AnchorGraph:
    """一套带五级锚点的元数据（用例自建，路径 / 编码按命名空间隔离）。"""

    menu_id: int
    menu_path: str
    form_id: int
    field_id: int
    button_id: int
    action_id: int
    business_id: int
    permission_id: int
    module_key: str
    business_code: str
    action_code: str
    module_anchor: str
    form_anchor: str
    field_anchor: str
    button_anchor: str
    action_anchor: str


class _StubResolver(BaseHelpContentResolver):
    """内容侧解析桩：按锚点返回预置文章，并记录收到的查询。

    桩不注册为插件实现（未声明实现名），仅经依赖覆盖注入。
    """

    def __init__(self) -> None:
        """初始化（缺省无命中、分类清单固定）。"""
        self.queries: ConcurrentStableList[HelpContentQuery] = ConcurrentStableList()
        self.hits: ConcurrentStableDict[str | None, HelpArticle] = ConcurrentStableDict()
        self.related: ConcurrentStableDict[str | None, ConcurrentStableFrozenList[HelpArticleSummary]] = (
            ConcurrentStableDict()
        )
        self.categories: ConcurrentStableFrozenList[HelpCategory] = ConcurrentStableFrozenList(
            [HelpCategory(category_id=900, name="快速上手", path="快速上手")]
        )

    async def resolve(self, query: HelpContentQuery, *, request: Request | None = None) -> HelpContentResult:
        """按候选顺序取首个有文章的锚点。

        Args:
            query: 解析查询。
            request: 当前请求（忽略）。

        Returns:
            HelpContentResult: 解析结果。
        """
        del request
        self.queries.add(query)
        for candidate in query.candidates:
            article = self.hits.get(candidate.help_key)
            if article is None:
                continue
            return HelpContentResult(
                level=candidate.level,
                help_key=candidate.help_key,
                article=article,
                related=self.related.get(candidate.help_key) or ConcurrentStableFrozenList(),
                categories=self.categories,
            )
        return HelpContentResult(categories=self.categories)


@pytest.fixture
def stub(service_app: FastAPI) -> Iterator[_StubResolver]:
    """把内容侧解析桩注入应用（依赖覆盖）。

    Args:
        service_app: 平台服务应用。

    Yields:
        _StubResolver: 解析桩。
    """
    resolver = _StubResolver()
    service_app.dependency_overrides[get_help_content_resolver] = lambda: resolver
    yield resolver
    service_app.dependency_overrides.pop(get_help_content_resolver, None)


def _article(article_id: int, title: str) -> HelpArticle:
    """构造命中文章。

    Args:
        article_id: 文章主键。
        title: 标题。

    Returns:
        HelpArticle: 文章值对象。
    """
    return HelpArticle(article_id=article_id, title=title, content=f"<p>{title}</p>", source="builtin")


async def _graph(client: AsyncClient, ns: Namespace) -> _AnchorGraph:
    """按命名空间建一套完整元数据（菜单 / 表单 / 字段 / 按钮 / 动作码全带锚点）。

    Args:
        client: 测试客户端。
        ns: 用例命名空间。

    Returns:
        _AnchorGraph: 元数据主键与锚点值。
    """
    module_key = f"{ns.prefix}_helpmod"
    business_code = f"{ns.prefix}_helpbiz"
    action_code = f"{ns.prefix}_helpact"
    module_anchor = f"platform:{module_key}:::"
    form_anchor = f"platform:{module_key}:{business_code}::"
    field_anchor = f"platform:{module_key}:{business_code}:username:"
    button_anchor = f"platform:{module_key}:{business_code}::{action_code}"
    action_anchor = f"platform::::{action_code}"
    menu_path = f"/{ns.prefix}/help"

    menu = _data(
        await client.post(
            _MENUS,
            json={
                "parent_id": 0,
                "path": menu_path,
                "sort": 1,
                "hidden": False,
                "status": "enabled",
                "i18n": {"zh-CN": "帮助解析", "en-US": "Help context"},
                "help_key": module_anchor,
            },
        ),
        "新增菜单",
    )
    business = _data(
        await client.post(_BUSINESSES, json={"code": business_code, "i18n": {"zh-CN": "帮助业务"}}),
        "新增业务码",
    )
    form = _data(
        await client.post(
            _FORMS,
            json={
                "menu_ids": [menu["id"]],
                "business_id": business["id"],
                "status": "enabled",
                "help_key": form_anchor,
            },
        ),
        "新增表单",
    )
    field = _data(
        await client.post(
            _FIELDS,
            json={
                "form_id": form["id"],
                "field_key": "username",
                "type": "input",
                "sort": 1,
                "status": "enabled",
                "i18n": {"zh-CN": "用户名"},
                "help_key": field_anchor,
            },
        ),
        "新增字段",
    )
    action = _data(
        await client.post(
            _ACTIONS,
            json={"code": action_code, "status": "enabled", "i18n": {"zh-CN": "新建"}, "help_key": action_anchor},
        ),
        "新增动作码",
    )
    permission = _data(
        await client.post(_PERMISSIONS, json={"business_id": business["id"], "action_id": action["id"]}),
        "新增权限码",
    )
    button = _data(
        await client.post(
            _BUTTONS,
            json={
                "form_id": form["id"],
                "permission_id": permission["id"],
                "name": "新建",
                "type": "toolbar",
                "sort": 1,
                "status": "enabled",
                "help_key": button_anchor,
            },
        ),
        "新增按钮",
    )
    return _AnchorGraph(
        menu_id=int(menu["id"]),
        menu_path=menu_path,
        form_id=int(form["id"]),
        field_id=int(field["id"]),
        button_id=int(button["id"]),
        action_id=int(action["id"]),
        business_id=int(business["id"]),
        permission_id=int(permission["id"]),
        module_key=module_key,
        business_code=business_code,
        action_code=action_code,
        module_anchor=module_anchor,
        form_anchor=form_anchor,
        field_anchor=field_anchor,
        button_anchor=button_anchor,
        action_anchor=action_anchor,
    )


def _params(graph: _AnchorGraph) -> ConcurrentStableDict[str, str]:
    """完整上下文查询参数。

    Args:
        graph: 元数据图。

    Returns:
        ConcurrentStableDict[str, str]: 查询参数。
    """
    return ConcurrentStableDict(
        {
            "module_key": graph.module_key,
            "form_key": graph.business_code,
            "field_key": "username",
            "action_code": graph.action_code,
        }
    )


async def _context(client: AsyncClient, params: ConcurrentStableDict[str, str]) -> Any:
    """调用解析接口并返回 `data`。

    Args:
        client: 测试客户端。
        params: 查询参数。

    Returns:
        Any: 解析结果。
    """
    return _data(await client.get(_CONTEXT, params=dict(params)), "页面内帮助解析")


@pytest.mark.kiwi_id(2521)
async def test_help_context_five_levels(client: AsyncClient, ns: Namespace, stub: _StubResolver) -> None:
    """五级命中：字段 → 动作（按钮 → 动作码兜底）→ 表单 → 模块 → 全局；全无文章即未命中。"""
    graph = await _graph(client, ns)
    params = _params(graph)

    miss = await _context(client, params)
    assert miss["matched"] is False
    assert miss["level"] is None
    assert miss["button_visible"] is False
    assert miss["article"] is None
    assert miss["categories"][0]["name"] == "快速上手"

    stub.hits.set(graph.field_anchor, _article(_FIELD_ARTICLE_ID, "字段帮助"))
    field_hit = await _context(client, params)
    assert (field_hit["level"], field_hit["help_key"]) == ("field", graph.field_anchor)
    assert field_hit["article"]["title"] == "字段帮助"
    assert field_hit["article"]["content"] == "<p>字段帮助</p>"
    assert field_hit["button_visible"] is True

    stub.hits.get_and_remove(graph.field_anchor)
    stub.hits.set(graph.button_anchor, _article(_BUTTON_ARTICLE_ID, "按钮帮助"))
    button_hit = await _context(client, params)
    assert (button_hit["level"], button_hit["help_key"]) == ("action", graph.button_anchor)

    stub.hits.get_and_remove(graph.button_anchor)
    stub.hits.set(graph.action_anchor, _article(_ACTION_ARTICLE_ID, "动作帮助"))
    action_hit = await _context(client, params)
    assert (action_hit["level"], action_hit["help_key"]) == ("action", graph.action_anchor)

    stub.hits.get_and_remove(graph.action_anchor)
    stub.hits.set(graph.form_anchor, _article(_FORM_ARTICLE_ID, "表单帮助"))
    form_hit = await _context(client, params)
    assert (form_hit["level"], form_hit["help_key"]) == ("form", graph.form_anchor)

    stub.hits.get_and_remove(graph.form_anchor)
    stub.hits.set(graph.module_anchor, _article(_MODULE_ARTICLE_ID, "模块帮助"))
    module_hit = await _context(client, params)
    assert (module_hit["level"], module_hit["help_key"]) == ("module", graph.module_anchor)

    stub.hits.get_and_remove(graph.module_anchor)
    stub.hits.set(None, _article(_GLOBAL_ARTICLE_ID, "全局帮助"))
    global_hit = await _context(client, params)
    assert (global_hit["level"], global_hit["help_key"]) == ("global", None)
    assert global_hit["article"]["title"] == "全局帮助"


@pytest.mark.kiwi_id(2521)
async def test_help_context_degrades_after_anchor_cleared(
    client: AsyncClient, ns: Namespace, stub: _StubResolver
) -> None:
    """逐级降级：清空某级锚点后同请求自动落到下一级（元数据版本变更即时生效）。"""
    graph = await _graph(client, ns)
    params = _params(graph)
    for anchor, article_id, title in (
        (graph.field_anchor, _FIELD_ARTICLE_ID, "字段帮助"),
        (graph.button_anchor, _BUTTON_ARTICLE_ID, "按钮帮助"),
        (graph.action_anchor, _ACTION_ARTICLE_ID, "动作帮助"),
        (graph.form_anchor, _FORM_ARTICLE_ID, "表单帮助"),
        (graph.module_anchor, _MODULE_ARTICLE_ID, "模块帮助"),
    ):
        stub.hits.set(anchor, _article(article_id, title))

    assert (await _context(client, params))["level"] == "field"

    await client.put(
        f"{_FIELDS}/{graph.field_id}",
        json={"type": "input", "sort": 1, "status": "enabled", "i18n": {"zh-CN": "用户名"}, "help_key": None},
    )
    assert (await _context(client, params))["level"] == "action"
    assert (await _context(client, params))["help_key"] == graph.button_anchor

    await client.put(
        f"{_BUTTONS}/{graph.button_id}",
        json={
            "permission_id": graph.permission_id,
            "name": "新建",
            "type": "toolbar",
            "sort": 1,
            "status": "enabled",
            "help_key": None,
        },
    )
    assert (await _context(client, params))["help_key"] == graph.action_anchor

    await client.put(
        f"{_ACTIONS}/{graph.action_id}",
        json={"status": "enabled", "i18n": {"zh-CN": "新建"}, "help_key": None},
    )
    assert (await _context(client, params))["level"] == "form"

    await client.put(
        f"{_FORMS}/{graph.form_id}",
        json={
            "menu_ids": [graph.menu_id],
            "business_id": graph.business_id,
            "component": None,
            "status": "enabled",
            "help_key": None,
        },
    )
    assert (await _context(client, params))["level"] == "module"

    await client.put(
        f"{_MENUS}/{graph.menu_id}",
        json={
            "parent_id": 0,
            "path": graph.menu_path,
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"zh-CN": "帮助解析", "en-US": "Help context"},
            "help_key": None,
        },
    )
    all_cleared = await _context(client, params)
    assert all_cleared["matched"] is False
    assert all_cleared["button_visible"] is False
    assert all_cleared["categories"]


@pytest.mark.kiwi_id(2521)
async def test_help_context_keeps_related_articles(client: AsyncClient, ns: Namespace, stub: _StubResolver) -> None:
    """多篇命中：主文章取一篇，其余进「相关内容」。"""
    graph = await _graph(client, ns)
    stub.hits.set(graph.form_anchor, _article(_FORM_ARTICLE_ID, "表单帮助"))
    stub.related.set(
        graph.form_anchor,
        ConcurrentStableFrozenList([HelpArticleSummary(article_id=901, title="更多表单帮助", source="product")]),
    )
    data = await _context(client, ConcurrentStableDict({"form_key": graph.business_code}))
    assert data["level"] == "form"
    assert data["related"] == [{"id": "901", "title": "更多表单帮助", "source": "product"}]


@pytest.mark.kiwi_id(2521)
async def test_help_context_empty_input_uses_global(client: AsyncClient, stub: _StubResolver) -> None:
    """入参全空：只向内容侧传一个全局候选。"""
    data = _data(await client.get(_CONTEXT), "空上下文解析")
    assert data["matched"] is False
    query = stub.queries[-1]
    assert [(candidate.level, candidate.help_key) for candidate in query.candidates] == [(HelpLevel.GLOBAL, None)]
    assert query.module_key is None
    assert query.form_key is None
    assert query.action_code is None


@pytest.mark.kiwi_id(2521)
async def test_help_context_field_requires_form_key(client: AsyncClient, ns: Namespace, stub: _StubResolver) -> None:
    """字段级缺表单键：不产生字段候选（从动作级开始）。"""
    graph = await _graph(client, ns)
    await _context(client, ConcurrentStableDict({"field_key": "username", "action_code": graph.action_code}))
    query = stub.queries[-1]
    assert HelpLevel.FIELD not in [candidate.level for candidate in query.candidates]
    assert next(candidate.level for candidate in query.candidates) is HelpLevel.ACTION


@pytest.mark.kiwi_id(2521)
async def test_help_context_module_product_disambiguation(
    client: AsyncClient, ns: Namespace, stub: _StubResolver
) -> None:
    """模块级多产品同名段：指定产品段只取该产品，未指定时平台优先。"""
    graph = await _graph(client, ns)
    biz_anchor = f"biz:{graph.module_key}:::"
    _data(
        await client.post(
            _MENUS,
            json={
                "parent_id": 0,
                "path": f"/{ns.prefix}/help-biz",
                "sort": 2,
                "hidden": False,
                "status": "enabled",
                "i18n": {"zh-CN": "产品帮助"},
                "help_key": biz_anchor,
            },
        ),
        "新增产品菜单",
    )
    stub.hits.set(graph.module_anchor, _article(_MODULE_ARTICLE_ID, "平台模块帮助"))
    stub.hits.set(biz_anchor, _article(801, "产品模块帮助"))

    params = ConcurrentStableDict({"module_key": graph.module_key})
    assert (await _context(client, params))["help_key"] == graph.module_anchor
    with_product = ConcurrentStableDict({"module_key": graph.module_key, "product_key": "biz"})
    assert (await _context(client, with_product))["help_key"] == biz_anchor


@pytest.mark.kiwi_id(2521)
async def test_my_menus_delivers_help_keys(client: AsyncClient, ns: Namespace) -> None:
    """`my_menus` 四级（菜单 / 表单 / 按钮 / 字段）随响应下发 help_key。"""
    graph = await _graph(client, ns)
    data = _data(await client.get("/api/v1/menus/my"), "动态菜单")
    node = next(item for item in data["menus"] if item["path"] == graph.menu_path)
    assert node["help_key"] == graph.module_anchor
    form = next(item for item in node["forms"] if int(item["id"]) == graph.form_id)
    assert form["help_key"] == graph.form_anchor
    field = next(item for item in form["fields"] if item["field_key"] == "username")
    assert field["help_key"] == graph.field_anchor
    button = next(item for item in form["buttons"] if int(item["id"]) == graph.button_id)
    assert button["help_key"] == graph.button_anchor


@pytest.mark.kiwi_id(2521)
async def test_help_context_requires_auth_and_rejects_bad_query(client: AsyncClient, service_app: FastAPI) -> None:
    """登录即可；无令牌被拒；参数为空串 / 超长返回 10001。"""
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as anonymous:
        rejected = await anonymous.get(_CONTEXT)
    assert rejected.status_code == 401
    assert rejected.json()["code"] == 20001

    empty_value = await client.get(_CONTEXT, params={"action_code": ""})
    assert empty_value.json()["code"] == 10001
    too_long = await client.get(_CONTEXT, params={"module_key": "a" * 65})
    assert too_long.json()["code"] == 10001
