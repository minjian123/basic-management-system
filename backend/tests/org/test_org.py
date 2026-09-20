"""组织主数据查询基座测试（Kiwi 843）：两契约 / 常量与数据契约 / 空实现 / 错误码 / 依赖解析 / 占位路由。"""

from collections.abc import Sequence

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_org_data_source, get_org_name_resolver
from app.core.capability import BaseCapability, BaseNullObject
from app.core.error_codes import ErrorCode
from app.core.plugin import BasePluggable, resolve_plugin
from app.main import ApplicationFactory, lifespan
from app.org.base import (
    DEFAULT_ORG_PAGE_SIZE,
    ORG_STATUSES,
    ORG_TARGETS,
    BaseOrgDataSource,
    BaseOrgNameResolver,
    OrgDept,
    OrgNameRef,
    OrgPost,
    OrgUser,
)
from app.org.null import NullOrgDataSource, NullOrgNameResolver
from app.schemas.pagination import BasePageResponse

API = "/api/v1/org"


class _InMemoryOrgDataSource(BaseOrgDataSource):
    """测试用内存组织查询（验证参数透传与取数；真实 DB 随 RBAC 阶段）。"""

    def __init__(self) -> None:
        self.last_users: dict[str, object] = {}

    async def users(
        self,
        keyword: str | None = None,
        *,
        dept_id: int | None = None,
        include_children: bool = False,
        status: str | None = None,
        page: int = 1,
        size: int = DEFAULT_ORG_PAGE_SIZE,
    ) -> BasePageResponse[OrgUser]:
        self.last_users = {
            "keyword": keyword,
            "dept_id": dept_id,
            "include_children": include_children,
            "status": status,
            "page": page,
            "size": size,
        }
        item = OrgUser(id=7, username="u7", nickname="研发张三", dept_id=dept_id, status=status or "enabled")
        return BasePageResponse[OrgUser](list=[item], total=1, page=page, size=size)

    async def posts(
        self,
        keyword: str | None = None,
        *,
        dept_id: int | None = None,
        include_children: bool = False,
        status: str | None = None,
        page: int = 1,
        size: int = DEFAULT_ORG_PAGE_SIZE,
    ) -> BasePageResponse[OrgPost]:
        del keyword, dept_id, include_children, status, page, size
        return BasePageResponse[OrgPost](
            list=[OrgPost(id=9, code="dev", name="开发岗", dept_id=1)], total=1, page=1, size=DEFAULT_ORG_PAGE_SIZE
        )

    async def dept_tree(self, *, status: str | None = None) -> Sequence[OrgDept]:
        del status
        child = OrgDept(id=2, parent_id=1, name="子部门")
        return (OrgDept(id=1, name="根部门", children=[child]),)


class _InMemoryOrgNameResolver(BaseOrgNameResolver):
    """测试用内存批量回显。"""

    async def resolve_names(self, target: str, ids: Sequence[int]) -> Sequence[OrgNameRef]:
        return tuple(OrgNameRef(id=item, name=f"{target}:{item}", target=target) for item in ids)


@pytest.mark.kiwi_id(843)
def test_contract_inheritance_and_identity() -> None:
    """两契约继承与能力域标识；两空实现占位标记。"""
    for contract in (BaseOrgDataSource, BaseOrgNameResolver):
        assert issubclass(contract, BasePluggable)
        assert issubclass(contract, BaseCapability)
    assert BaseOrgDataSource.key == BaseOrgDataSource.plugin_key == "org_data_source"
    assert BaseOrgNameResolver.key == BaseOrgNameResolver.plugin_key == "org_name_resolver"

    for null_cls in (NullOrgDataSource, NullOrgNameResolver):
        assert issubclass(null_cls, BaseNullObject)

    service = NullOrgDataSource()
    assert service.placeholder is True
    assert "占位实现" in service.describe()


@pytest.mark.kiwi_id(843)
def test_constants_and_data_contracts() -> None:
    """常量取值、数据契约字段集 / 默认值、脱敏声明与嵌套部门树。"""
    assert ORG_STATUSES == ("enabled", "disabled")
    assert ORG_TARGETS == ("user", "post", "dept")
    assert DEFAULT_ORG_PAGE_SIZE == 20

    assert set(OrgUser.model_fields) == {
        "id",
        "username",
        "nickname",
        "dept_id",
        "status",
        "avatar",
        "phone",
        "email",
    }
    assert OrgUser.masked_fields == frozenset({"phone", "email"})
    assert set(OrgPost.model_fields) == {"id", "code", "name", "dept_id", "status", "sort"}
    assert set(OrgDept.model_fields) == {"id", "parent_id", "name", "sort", "status", "children"}
    assert set(OrgNameRef.model_fields) == {"id", "name", "target", "exists", "status"}

    user = OrgUser(id=1, username="u")
    assert user.nickname == ""
    assert user.dept_id is None
    assert user.status == "enabled"
    assert user.avatar is None
    assert user.phone is None
    assert user.email is None

    ref = OrgNameRef(id=1, name="n")
    assert ref.target == "user"
    assert ref.exists is True
    assert ref.status == "enabled"

    tree = OrgDept(id=1, name="根", children=[OrgDept(id=2, parent_id=1, name="子")])
    assert tree.children[0].parent_id == 1


@pytest.mark.kiwi_id(843)
def test_org_error_codes_registered() -> None:
    """组织查询错误码 30101~30103 登记且取值正确。"""
    assert ErrorCode.ORG_SOURCE_UNAVAILABLE == 30101
    assert ErrorCode.ORG_TARGET_UNSUPPORTED == 30102
    assert ErrorCode.ORG_DEPT_NOT_FOUND == 30103


@pytest.mark.kiwi_id(843)
async def test_null_fixed_and_batch_returns() -> None:
    """空实现：用户 / 岗位固定单条页、部门树两节点、批量回显按 ids。"""
    source = NullOrgDataSource()
    users = await source.users("张", dept_id=1, include_children=True, status="enabled", page=2, size=5)
    assert users.total == 1
    assert users.page == 2
    assert users.size == 5
    assert users.list[0].username == "null-user"

    posts = await source.posts()
    assert posts.total == 1
    assert posts.list[0].code == "null-post"

    tree = await source.dept_tree()
    assert len(tree) == 1
    assert tree[0].name == "占位根部门"
    assert len(tree[0].children) == 1
    assert tree[0].children[0].parent_id == 1

    refs = await NullOrgNameResolver().resolve_names("post", [1, 2])
    assert [ref.id for ref in refs] == [1, 2]
    assert refs[0].name == "占位#1"
    assert all(ref.target == "post" and ref.exists is True for ref in refs)


@pytest.mark.kiwi_id(843)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配两空实现；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.org_data_source, NullOrgDataSource)
        assert isinstance(app.state.org_name_resolver, NullOrgNameResolver)
        assert resolve_plugin("org_data_source", None) is app.state.org_data_source
        assert resolve_plugin("org_name_resolver", None) is app.state.org_name_resolver


@pytest.mark.kiwi_id(843)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：四路径固定返回、部门树不分页。"""
    users = await client.get(f"{API}/users", params={"keyword": "张", "dept_id": 1, "include_children": True})
    assert users.status_code == 200
    users_data = users.json()["data"]
    assert users_data["total"] == 1
    assert users_data["list"][0]["username"] == "null-user"

    posts = await client.get(f"{API}/posts", params={"status": "enabled"})
    assert posts.status_code == 200
    assert posts.json()["data"]["list"][0]["code"] == "null-post"

    tree = await client.get(f"{API}/dept-tree")
    assert tree.status_code == 200
    tree_data = tree.json()["data"]
    assert isinstance(tree_data, list)
    assert tree_data[0]["name"] == "占位根部门"
    assert tree_data[0]["children"][0]["name"] == "占位子部门"

    refs = await client.get(f"{API}/resolve-names", params={"target": "dept", "id_in": "1,2"})
    assert refs.status_code == 200
    assert [item["id"] for item in refs.json()["data"]] == ["1", "2"]

    bad = await client.get(f"{API}/resolve-names", params={"id_in": "1,x"})
    assert bad.status_code == 200
    assert bad.json()["code"] == 10001


@pytest.mark.kiwi_id(843)
async def test_routes_with_in_memory_implementations() -> None:
    """占位路由 + 内存实现：参数透传 / 部门树 / 批量回显。"""
    source = _InMemoryOrgDataSource()
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        app.dependency_overrides[get_org_data_source] = lambda: source
        app.dependency_overrides[get_org_name_resolver] = lambda: _InMemoryOrgNameResolver()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                f"{API}/users",
                params={
                    "keyword": "张",
                    "dept_id": 3,
                    "include_children": True,
                    "status": "disabled",
                    "page": 2,
                    "size": 10,
                },
            )
            assert resp.json()["data"]["list"][0]["nickname"] == "研发张三"
            assert source.last_users == {
                "keyword": "张",
                "dept_id": 3,
                "include_children": True,
                "status": "disabled",
                "page": 2,
                "size": 10,
            }

            tree = await client.get(f"{API}/dept-tree")
            assert tree.json()["data"][0]["children"][0]["name"] == "子部门"

            refs = await client.get(f"{API}/resolve-names", params={"target": "user", "id_in": "5,6"})
            assert [item["name"] for item in refs.json()["data"]] == ["user:5", "user:6"]
