"""打印模板与导出 PDF 基座契约测试（Kiwi 906）：契约 / 常量 / 数据契约 / 占位语义 / 错误码 / 依赖解析 / 占位路由。"""

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_idempotency_store, get_print_template_provider
from app.api.print import router as print_router
from app.core.capability import BaseCapability, BaseNullObject
from app.core.error_codes import ErrorCode, ErrorSegment
from app.core.exceptions import (
    BizError,
    FileError,
    PrintArtifactNotFoundError,
    PrintBatchLimitError,
    PrintError,
    PrintTemplateNotFoundError,
)
from app.core.plugin import BasePluggable, resolve_plugin
from app.main import ApplicationFactory, lifespan
from app.print.base import (
    DEFAULT_PAPER,
    NULL_PRINT_BIZ_KEY,
    NULL_PRINT_URL,
    PRINT_BATCH_MODES,
    PRINT_CONTENT_TYPE,
    PRINT_OBJECT_DOMAIN,
    PRINT_ORIENTATIONS,
    PRINT_PAPERS,
    PRINT_PLACEHOLDER_MESSAGE,
    PRINT_TEMPLATE_STATUSES,
    PRINT_TONES,
    BasePrintExporter,
    BasePrintTemplateProvider,
    PrintBatchResult,
    PrintDocument,
    PrintExportResult,
    PrintOptions,
    PrintTemplateInfo,
    PrintVariable,
    build_print_object_key,
)
from app.print.null import NullPrintExporter, NullPrintTemplateProvider
from app.storage.base import DEFAULT_PRESIGN_TTL

API = "/api/v1/prints"

_TEMPLATE = PrintTemplateInfo(
    key="order",
    name="销售订单",
    biz_type="sale",
    variables=[PrintVariable(key="customer", label="客户")],
    status="active",
)


class _StubTemplateProvider:
    """模板来源测试替身：固定返回一条模板（覆盖模板映射分支；不继承能力端口，不参与注册表）。"""

    async def list(self, *, biz_type: str | None = None) -> list[PrintTemplateInfo]:
        """取模板清单（替身固定一条）。

        Args:
            biz_type: 单据类型（替身忽略）。

        Returns:
            list[PrintTemplateInfo]: 单条模板清单。
        """
        del biz_type
        return [_TEMPLATE]

    async def get(self, template_key: str) -> PrintTemplateInfo:
        """取单模板定义（替身固定返回）。

        Args:
            template_key: 模板键（替身忽略）。

        Returns:
            PrintTemplateInfo: 固定模板定义。
        """
        del template_key
        return _TEMPLATE


class _RecordingIdempotency:
    """幂等基座测试替身：内存首次结果表（不继承能力端口，避免以占位名污染进程级注册表）。"""

    def __init__(self) -> None:
        """初始化空首次结果表。"""
        self.keys: list[str] = []
        self._payloads: dict[str, dict[str, object]] = {}

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键（首次为 True）。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 首次 True。
        """
        del ttl
        self.keys.append(key)
        return key not in self._payloads

    async def load(self, key: str) -> dict[str, object] | None:
        """取首次结果载荷。

        Args:
            key: 幂等键。

        Returns:
            dict[str, object] | None: 首次结果；未缓存为 None。
        """
        return self._payloads.get(key)

    async def save(self, key: str, payload: dict[str, object], *, ttl: int | None = None) -> None:
        """写首次结果。

        Args:
            key: 幂等键。
            payload: 首次结果载荷。
            ttl: 键有效期（替身忽略）。
        """
        del ttl
        self._payloads[key] = payload


class _StaleIdempotency(_RecordingIdempotency):
    """幂等基座替身：非首次且首次结果不可读（占位期并发穿透，应继续执行）。"""

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键并恒返回非首次。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 恒 False（非首次）。
        """
        await super().begin(key, ttl=ttl)
        return False

    async def load(self, key: str) -> dict[str, object] | None:
        """取首次结果（恒不可读）。

        Args:
            key: 幂等键。

        Returns:
            dict[str, object] | None: 恒 None。
        """
        del key
        return None


@pytest.mark.kiwi_id(906)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BasePrintTemplateProvider, BasePluggable)
    assert issubclass(BasePrintTemplateProvider, BaseCapability)
    assert issubclass(BasePrintExporter, BasePluggable)
    assert issubclass(BasePrintExporter, BaseCapability)
    assert issubclass(NullPrintTemplateProvider, BasePrintTemplateProvider)
    assert issubclass(NullPrintTemplateProvider, BaseNullObject)
    assert issubclass(NullPrintExporter, BasePrintExporter)
    assert issubclass(NullPrintExporter, BaseNullObject)
    assert BasePrintTemplateProvider.key == "print_template"
    assert BasePrintTemplateProvider.plugin_key == "print_template"
    assert BasePrintExporter.key == "print_exporter"
    assert BasePrintExporter.plugin_key == "print_exporter"

    for instance in (NullPrintTemplateProvider(), NullPrintExporter()):
        assert instance.placeholder is True
        assert "占位实现" in instance.describe()


@pytest.mark.kiwi_id(906)
def test_constants_and_object_key() -> None:
    """取值集合常量与产物对象 key 助手。"""
    assert PRINT_PAPERS == ("A4", "A5", "custom")
    assert PRINT_ORIENTATIONS == ("portrait", "landscape")
    assert PRINT_TONES == ("color", "mono")
    assert PRINT_BATCH_MODES == ("separate", "merged")
    assert PRINT_TEMPLATE_STATUSES == ("active", "disabled")
    assert PRINT_CONTENT_TYPE == "application/pdf"
    assert DEFAULT_PAPER == "A4"
    assert PRINT_OBJECT_DOMAIN == "prints"
    assert PRINT_PLACEHOLDER_MESSAGE == "导出未就绪（占位）"
    assert NULL_PRINT_URL == "null-print-url"
    assert NULL_PRINT_BIZ_KEY == "null"

    assert build_print_object_key(template_key="order", biz_key="SO-001") == "bms:global:prints:order:SO-001"
    assert (
        build_print_object_key(template_key="order", biz_key="SO-001", tenant="demo") == "bms:demo:prints:order:SO-001"
    )


@pytest.mark.kiwi_id(906)
def test_data_contract_defaults() -> None:
    """六数据契约字段口径与缺省值。"""
    variable = PrintVariable(key="customer", label="客户")
    assert variable.key == "customer"
    assert variable.label == "客户"

    template = PrintTemplateInfo(key="order", name="销售订单")
    assert template.biz_type is None
    assert template.variables == []
    assert template.status == "active"

    document = PrintDocument()
    assert document.biz_key is None
    assert document.fields == {}
    assert document.rows == []

    options = PrintOptions()
    assert options.paper == DEFAULT_PAPER
    assert options.orientation == "portrait"
    assert options.tone == "color"
    assert options.watermark == ""
    assert options.printed_by is None

    result = PrintExportResult(object_key="k", file_name="order.pdf")
    assert result.file_id is None
    assert result.size == 0
    assert result.content_type == PRINT_CONTENT_TYPE
    assert result.url is None
    assert result.expires_in == 0
    assert result.message is None

    batch = PrintBatchResult()
    assert batch.task_id is None
    assert batch.total == 0
    assert batch.succeeded == 0
    assert batch.failed == 0
    assert batch.items == []
    assert batch.message is None


@pytest.mark.kiwi_id(906)
async def test_null_template_list_is_empty() -> None:
    """占位模板清单：固定空清单，不区分单据类型。"""
    provider = NullPrintTemplateProvider()

    templates = await provider.list()
    assert templates == []

    assert await provider.list(biz_type="sale") == []


@pytest.mark.kiwi_id(906)
async def test_null_template_get_not_found() -> None:
    """占位模板详情：恒定未命中（50201 / 404）。"""
    provider = NullPrintTemplateProvider()
    with pytest.raises(PrintTemplateNotFoundError) as excinfo:
        await provider.get("order")

    assert excinfo.value.code == ErrorCode.PRINT_TEMPLATE_NOT_FOUND
    assert excinfo.value.http_status == 404
    assert "order" in str(excinfo.value)


@pytest.mark.kiwi_id(906)
async def test_null_export_pdf_placeholder_artifact() -> None:
    """占位单条导出：固定占位产物、零副作用、忽略渲染选项。"""
    exporter = NullPrintExporter()
    document = PrintDocument(biz_key="SO-001", fields={"customer": "甲"}, rows=[{"item": "A"}])

    result = await exporter.export_pdf("order", document)
    assert result.object_key == "bms:global:prints:order:SO-001"
    assert result.file_name == "order.pdf"
    assert result.file_id is None
    assert result.size == 0
    assert result.content_type == PRINT_CONTENT_TYPE
    assert result.url == NULL_PRINT_URL
    assert result.expires_in == DEFAULT_PRESIGN_TTL
    assert result.message == PRINT_PLACEHOLDER_MESSAGE

    assert await exporter.export_pdf("order", document) == result
    assert await exporter.export_pdf("order", document, options=PrintOptions(paper="A5", tone="mono")) == result


@pytest.mark.kiwi_id(906)
async def test_null_export_pdf_without_biz_key() -> None:
    """占位单条导出：单据数据未带单据键时回落缺省位。"""
    result = await NullPrintExporter().export_pdf("order", PrintDocument())

    assert result.object_key == f"bms:global:prints:order:{NULL_PRINT_BIZ_KEY}"


@pytest.mark.kiwi_id(906)
async def test_null_batch_print_modes() -> None:
    """占位批量打印：空键空汇总、逐份逐键明细、合并单条明细。"""
    exporter = NullPrintExporter()

    empty = await exporter.batch_print([], template_key="order")
    assert empty.task_id is None
    assert empty.total == 0
    assert empty.succeeded == 0
    assert empty.failed == 0
    assert empty.items == []
    assert empty.message == PRINT_PLACEHOLDER_MESSAGE

    separate = await exporter.batch_print(["SO-1", "SO-2"], template_key="order")
    assert separate.total == 2
    assert separate.succeeded == 2
    assert separate.failed == 0
    assert separate.task_id is None
    assert [item.file_name for item in separate.items] == ["order-SO-1.pdf", "order-SO-2.pdf"]
    assert [item.object_key for item in separate.items] == [
        "bms:global:prints:order:SO-1",
        "bms:global:prints:order:SO-2",
    ]

    merged = await exporter.batch_print(["SO-1", "SO-2"], template_key="order", mode="merged")
    assert merged.total == 2
    assert merged.succeeded == 2
    assert len(merged.items) == 1
    assert merged.items[0].file_name == "order.pdf"
    assert merged.items[0].object_key == "bms:global:prints:order:SO-1"


@pytest.mark.kiwi_id(906)
def test_error_codes_and_segment_base() -> None:
    """打印错误码：码位 / HTTP 状态 / 段位基继承链。"""
    assert ErrorCode.PRINT_TEMPLATE_NOT_FOUND == 50201
    assert ErrorCode.PRINT_ARTIFACT_NOT_FOUND == 50202
    assert ErrorCode.PRINT_BATCH_LIMIT_EXCEEDED == 50203

    assert issubclass(PrintError, FileError)
    assert issubclass(FileError, BizError)
    assert issubclass(PrintTemplateNotFoundError, PrintError)
    assert issubclass(PrintArtifactNotFoundError, PrintError)
    assert issubclass(PrintBatchLimitError, PrintError)

    template_missing = PrintTemplateNotFoundError()
    artifact_missing = PrintArtifactNotFoundError()
    batch_limit = PrintBatchLimitError()
    assert (template_missing.code, template_missing.http_status) == (50201, 404)
    assert (artifact_missing.code, artifact_missing.http_status) == (50202, 404)
    assert (batch_limit.code, batch_limit.http_status) == (50203, 200)
    assert template_missing.code // 10000 == ErrorSegment.FILE
    assert artifact_missing.code // 10000 == ErrorSegment.FILE
    assert batch_limit.code // 10000 == ErrorSegment.FILE


@pytest.mark.kiwi_id(906)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配两占位实现；两提供者分别解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        exporter = app.state.print_exporter
        provider = app.state.print_template
        assert isinstance(exporter, NullPrintExporter)
        assert isinstance(provider, NullPrintTemplateProvider)
        assert resolve_plugin("print_exporter", None) is exporter
        assert resolve_plugin("print_template", None) is provider
        assert app.state.plugin_providers["print_exporter"] == "null"
        assert app.state.plugin_providers["print_template"] == "null"


@pytest.mark.kiwi_id(906)
def test_route_auth_scope() -> None:
    """登录口径：四端点均挂登录依赖（路由级统一）。"""
    routes = [route for route in print_router.routes if isinstance(route, APIRoute)]
    assert print_router.key == "print"
    assert {route.path for route in routes} == {
        "/prints/exports",
        "/prints/batch",
        "/prints/templates",
        "/prints/templates/{template_key}",
    }
    assert {route.path: len(route.dependencies) for route in routes} == {
        "/prints/exports": 1,
        "/prints/batch": 1,
        "/prints/templates": 1,
        "/prints/templates/{template_key}": 1,
    }


@pytest.mark.kiwi_id(906)
async def test_placeholder_route_export(client: AsyncClient) -> None:
    """占位路由：单条导出返回占位产物；空模板键 → 10001。"""
    resp = await client.post(
        f"{API}/exports",
        json={"template_key": "order", "document": {"biz_key": "SO-001", "fields": {"customer": "甲"}}},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["object_key"] == "bms:global:prints:order:SO-001"
    assert data["file_name"] == "order.pdf"
    assert data["url"] == NULL_PRINT_URL
    assert data["content_type"] == PRINT_CONTENT_TYPE
    assert data["expires_in"] == DEFAULT_PRESIGN_TTL
    assert data["message"] == PRINT_PLACEHOLDER_MESSAGE

    invalid = await client.post(f"{API}/exports", json={"template_key": "   ", "document": {}})
    assert invalid.json()["code"] == 10001

    with_options = await client.post(
        f"{API}/exports",
        json={
            "template_key": "order",
            "document": {"biz_key": "SO-001"},
            "options": {
                "paper": "A5",
                "orientation": "landscape",
                "tone": "mono",
                "watermark": "样张",
                "printed_by": "甲",
            },
        },
    )
    assert with_options.json()["data"] == data


@pytest.mark.kiwi_id(906)
async def test_placeholder_route_batch(client: AsyncClient) -> None:
    """占位路由：批量打印逐份明细与单据数一致；空单据键集合 → 10001。"""
    resp = await client.post(f"{API}/batch", json={"template_key": "order", "keys": ["SO-1", "SO-2"]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert data["task_id"] is None
    assert [item["file_name"] for item in data["items"]] == ["order-SO-1.pdf", "order-SO-2.pdf"]

    invalid = await client.post(f"{API}/batch", json={"template_key": "order", "keys": []})
    assert invalid.json()["code"] == 10001


@pytest.mark.kiwi_id(906)
async def test_export_idempotency_reuses_first_result() -> None:
    """导出按幂等键复用首次结果（作用域绑当前租户位）。"""
    app = ApplicationFactory().create(None)
    double = _RecordingIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: double
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            f"{API}/exports",
            json={"template_key": "order", "document": {"biz_key": "SO-1"}},
            headers={"Idempotency-Key": "k-1"},
        )
        second = await client.post(
            f"{API}/exports",
            json={"template_key": "other", "document": {"biz_key": "SO-2"}},
            headers={"Idempotency-Key": "k-1"},
        )

    assert first.json()["data"]["file_name"] == "order.pdf"
    assert second.json()["data"] == first.json()["data"]
    assert double.keys == ["bms:demo:idem:k-1", "bms:demo:idem:k-1"]


@pytest.mark.kiwi_id(906)
async def test_batch_idempotency_without_cached_result_executes() -> None:
    """批量：幂等键非首次但首次结果不可读时继续执行（并发穿透不阻断）。"""
    app = ApplicationFactory().create(None)
    stale = _StaleIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: stale
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"{API}/batch",
            json={"template_key": "order", "keys": ["SO-1"]},
            headers={"Idempotency-Key": "k-2"},
        )

    assert resp.json()["data"]["total"] == 1
    assert stale.keys == ["bms:demo:idem:k-2"]


@pytest.mark.kiwi_id(906)
async def test_batch_idempotency_reuses_first_result() -> None:
    """批量按幂等键复用首次结果（作用域绑当前租户位）。"""
    app = ApplicationFactory().create(None)
    double = _RecordingIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: double
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            f"{API}/batch",
            json={"template_key": "order", "keys": ["SO-1"]},
            headers={"Idempotency-Key": "k-3"},
        )
        second = await client.post(
            f"{API}/batch",
            json={"template_key": "other", "keys": ["SO-9"]},
            headers={"Idempotency-Key": "k-3"},
        )

    assert first.json()["data"]["total"] == 1
    assert second.json()["data"] == first.json()["data"]
    assert double.keys == ["bms:demo:idem:k-3", "bms:demo:idem:k-3"]


@pytest.mark.kiwi_id(906)
async def test_placeholder_route_templates(client: AsyncClient) -> None:
    """占位路由：模板清单为空、模板详情 404 且业务码 50201。"""
    listed = await client.get(f"{API}/templates")
    assert listed.status_code == 200
    assert listed.json()["data"] == {"templates": []}

    filtered = await client.get(f"{API}/templates", params={"biz_type": "sale"})
    assert filtered.json()["data"] == {"templates": []}

    missing = await client.get(f"{API}/templates/order")
    assert missing.status_code == 404
    assert missing.json()["code"] == ErrorCode.PRINT_TEMPLATE_NOT_FOUND


@pytest.mark.kiwi_id(906)
async def test_route_templates_mapping_with_stub_provider() -> None:
    """模板映射分支：替身来源返回模板时清单与详情字段一一对应。"""
    app = ApplicationFactory().create(None)
    app.dependency_overrides[get_print_template_provider] = _StubTemplateProvider
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get(f"{API}/templates")
        detail = await client.get(f"{API}/templates/order")

    expected = {
        "key": "order",
        "name": "销售订单",
        "biz_type": "sale",
        "variables": [{"key": "customer", "label": "客户"}],
        "status": "active",
    }
    assert listed.json()["data"] == {"templates": [expected]}
    assert detail.json()["data"] == expected
