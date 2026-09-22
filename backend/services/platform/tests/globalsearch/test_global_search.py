"""全文检索查询契约测试（Kiwi 821）：三契约 / 常量与数据契约 / 降级 / 错误码 / 空实现 / 依赖解析 / 占位路由。"""

from collections.abc import Sequence
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_audit_search, get_file_content_search, get_global_search
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.error_codes import ErrorCode
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.globalsearch.base import (
    DEFAULT_GLOBAL_SEARCH_SIZE,
    DEGRADE_REASONS,
    GLOBAL_SEARCH_DOMAINS,
    GLOBAL_SEARCH_MAX_PAGE,
    NULL_DEGRADE_REASON,
    NULL_SEARCH_ALTERNATIVE,
    AuditLogHit,
    AuditSearchResult,
    BaseAuditSearch,
    BaseFileContentSearch,
    BaseGlobalSearch,
    FileContentHit,
    FileContentSearchResult,
    GlobalSearchGroup,
    GlobalSearchHit,
    GlobalSearchResult,
)
from bms_core.globalsearch.null import NullAuditSearch, NullFileContentSearch, NullGlobalSearch
from bms_platform.main import ApplicationFactory, lifespan

API = "/api/v1/search"


class _InMemoryGlobalSearch(BaseGlobalSearch):
    """测试用内存多域聚合（验证分组与域过滤；真实 ES 随全文检索阶段）。"""

    def __init__(self) -> None:
        self._hits: dict[str, list[GlobalSearchHit]] = {
            "user": [GlobalSearchHit(doc_type="user", biz_id="u1", title="张三")],
            "dept": [GlobalSearchHit(doc_type="dept", biz_id="d1", title="研发部")],
        }

    async def domains(self) -> Sequence[str]:
        return tuple(self._hits)

    async def search(
        self,
        q: str,
        *,
        types: Sequence[str] | None = None,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> GlobalSearchResult:
        allowed = list(types) if types else list(self._hits)
        groups = [
            GlobalSearchGroup(doc_type=doc_type, hits=self._hits[doc_type], total=len(self._hits[doc_type]))
            for doc_type in allowed
            if doc_type in self._hits
        ]
        total = sum(group.total for group in groups)
        return GlobalSearchResult(groups=groups, total=total)


class _InMemoryAuditSearch(BaseAuditSearch):
    """测试用内存审计日志检索。"""

    async def audit_logs(
        self,
        q: str,
        *,
        log_type: str | None = None,
        start_time: datetime,
        end_time: datetime,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> AuditSearchResult:
        del start_time, end_time, page, size
        if q != "login":
            return AuditSearchResult(hits=[], total=0)
        return AuditSearchResult(
            hits=[AuditLogHit(log_type=log_type or "login", record_id="r1", title="登录成功")],
            total=1,
        )


class _InMemoryFileContentSearch(BaseFileContentSearch):
    """测试用内存文件内容检索。"""

    async def file_content(
        self,
        q: str,
        *,
        file_type: str | None = None,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> FileContentSearchResult:
        del file_type, page, size
        if q != "合同":
            return FileContentSearchResult(hits=[], total=0)
        return FileContentSearchResult(
            hits=[FileContentHit(file_id="f1", name="合同.pdf", mime_type="application/pdf")],
            total=1,
        )


@pytest.mark.kiwi_id(821)
def test_contract_inheritance_and_identity() -> None:
    """三契约继承与能力域标识；三空实现占位标记。"""
    for contract in (BaseGlobalSearch, BaseAuditSearch, BaseFileContentSearch):
        assert issubclass(contract, BasePluggable)
        assert issubclass(contract, BaseCapability)
    assert BaseGlobalSearch.key == BaseGlobalSearch.plugin_key == "global_search"
    assert BaseAuditSearch.key == BaseAuditSearch.plugin_key == "audit_search"
    assert BaseFileContentSearch.key == BaseFileContentSearch.plugin_key == "file_content_search"

    for null_cls in (NullGlobalSearch, NullAuditSearch, NullFileContentSearch):
        assert issubclass(null_cls, BaseNullObject)

    service = NullGlobalSearch()
    assert service.placeholder is True
    assert "占位实现" in service.describe()


@pytest.mark.kiwi_id(821)
def test_constants_and_data_contracts() -> None:
    """常量取值与数据契约字段集 / 默认值 / 降级字段。"""
    assert GLOBAL_SEARCH_DOMAINS == ("user", "dept", "role", "dict", "purchase", "file_meta", "help_article")
    assert DEGRADE_REASONS == ("unavailable", "timeout", "fallback")
    assert NULL_DEGRADE_REASON == "unavailable"
    assert NULL_SEARCH_ALTERNATIVE == "db_fuzzy"
    assert DEFAULT_GLOBAL_SEARCH_SIZE == 20
    assert GLOBAL_SEARCH_MAX_PAGE == 100

    assert set(GlobalSearchHit.model_fields) == {"doc_type", "biz_id", "title", "highlight", "updated_at"}
    assert set(GlobalSearchGroup.model_fields) == {"doc_type", "hits", "total"}
    assert set(GlobalSearchResult.model_fields) == {
        "groups",
        "total",
        "degraded",
        "degrade_reason",
        "alternative",
    }
    assert set(AuditSearchResult.model_fields) == {"hits", "total", "degraded", "degrade_reason", "alternative"}
    assert set(FileContentSearchResult.model_fields) == {
        "hits",
        "total",
        "degraded",
        "degrade_reason",
        "alternative",
    }

    hit = GlobalSearchHit(doc_type="user", biz_id="u1")
    assert hit.title == ""
    assert hit.highlight == {}
    assert hit.updated_at is None

    result = GlobalSearchResult()
    assert result.groups == []
    assert result.total == 0
    assert result.degraded is False
    assert result.degrade_reason is None
    assert result.alternative is None


@pytest.mark.kiwi_id(821)
def test_search_error_codes_registered() -> None:
    """检索错误码 10101~10107 登记且取值正确。"""
    assert ErrorCode.SEARCH_UNAVAILABLE == 10101
    assert ErrorCode.SEARCH_TIMEOUT == 10102
    assert ErrorCode.SEARCH_DEGRADED == 10103
    assert ErrorCode.SEARCH_INDEX_NOT_READY == 10104
    assert ErrorCode.SEARCH_REBUILD_RUNNING == 10105
    assert ErrorCode.SEARCH_FILE_NOT_SEARCHABLE == 10106
    assert ErrorCode.SEARCH_TIME_RANGE_EXCEEDED == 10107


@pytest.mark.kiwi_id(821)
async def test_null_fixed_returns_with_degrade() -> None:
    """占位实现：域空 / 空结果 + 降级标记。"""
    global_search = NullGlobalSearch()
    assert await global_search.domains() == ()
    result = await global_search.search("x", types=["user"])
    assert result.groups == []
    assert result.total == 0
    assert result.degraded is True
    assert result.degrade_reason == NULL_DEGRADE_REASON
    assert result.alternative == NULL_SEARCH_ALTERNATIVE

    audit = await NullAuditSearch().audit_logs("x", start_time=datetime(2026, 9, 1), end_time=datetime(2026, 9, 2))
    assert audit.hits == []
    assert audit.degraded is True

    files = await NullFileContentSearch().file_content("x")
    assert files.hits == []
    assert files.degraded is True


@pytest.mark.kiwi_id(821)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配三空实现；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.global_search, NullGlobalSearch)
        assert isinstance(app.state.audit_search, NullAuditSearch)
        assert isinstance(app.state.file_content_search, NullFileContentSearch)
        assert resolve_plugin("global_search", None) is app.state.global_search
        assert resolve_plugin("audit_search", None) is app.state.audit_search
        assert resolve_plugin("file_content_search", None) is app.state.file_content_search


@pytest.mark.kiwi_id(821)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：三路径固定空结果 + 降级标记。"""
    global_resp = await client.get(f"{API}/global", params={"q": "x", "types": ["user", "dept"]})
    assert global_resp.status_code == 200
    global_data = global_resp.json()["data"]
    assert global_data["groups"] == []
    assert global_data["total"] == 0
    assert global_data["degraded"] is True
    assert global_data["degrade_reason"] == NULL_DEGRADE_REASON
    assert global_data["alternative"] == NULL_SEARCH_ALTERNATIVE

    logs = await client.get(
        f"{API}/logs",
        params={"q": "x", "start_time": "2026-09-01T00:00:00", "end_time": "2026-09-02T00:00:00"},
    )
    assert logs.status_code == 200
    assert logs.json()["data"]["hits"] == []
    assert logs.json()["data"]["degraded"] is True

    missing_range = await client.get(f"{API}/logs", params={"q": "x"})
    assert missing_range.status_code == 200
    assert missing_range.json()["code"] == 10001

    files = await client.get(f"{API}/files", params={"q": "合同"})
    assert files.status_code == 200
    assert files.json()["data"]["hits"] == []
    assert files.json()["data"]["degraded"] is True


@pytest.mark.kiwi_id(821)
async def test_routes_with_in_memory_implementations() -> None:
    """占位路由 + 内存实现：多域分组 / 域过滤 / 审计与文件命中。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        app.dependency_overrides[get_global_search] = lambda: _InMemoryGlobalSearch()
        app.dependency_overrides[get_audit_search] = lambda: _InMemoryAuditSearch()
        app.dependency_overrides[get_file_content_search] = lambda: _InMemoryFileContentSearch()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            grouped = await client.get(f"{API}/global", params={"q": "张"})
            groups = grouped.json()["data"]["groups"]
            assert {group["doc_type"] for group in groups} == {"user", "dept"}
            assert grouped.json()["data"]["total"] == 2

            filtered = await client.get(f"{API}/global", params={"q": "张", "types": ["user"]})
            filtered_groups = filtered.json()["data"]["groups"]
            assert [group["doc_type"] for group in filtered_groups] == ["user"]

            logs = await client.get(
                f"{API}/logs",
                params={
                    "q": "login",
                    "start_time": "2026-09-01T00:00:00",
                    "end_time": "2026-09-02T00:00:00",
                },
            )
            assert logs.json()["data"]["hits"][0]["record_id"] == "r1"

            files = await client.get(f"{API}/files", params={"q": "合同"})
            assert files.json()["data"]["hits"][0]["file_id"] == "f1"
