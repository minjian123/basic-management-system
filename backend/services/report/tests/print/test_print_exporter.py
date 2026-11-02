"""打印模板与导出 PDF 基座契约测试（Kiwi 906）：契约 / 常量 / 数据契约 / 真实导出 / 模板来源 / 错误码 / 幂等 / 鉴权。

04_02 起 `/prints` 走真实实现（reportlab 渲染 + 对象存储 + 限时取址），原「占位语义」用例相应改为真实断言。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_idempotency_store, get_print_exporter
from bms_core.application import service_lifespan as lifespan
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import (
    BizError,
    FileError,
    PrintBatchLimitError,
    PrintError,
    PrintTemplateNotFoundError,
)
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE
from bms_core.print.base import (
    DEFAULT_PAPER,
    PRINT_BATCH_MODES,
    PRINT_CONTENT_TYPE,
    PRINT_CONTRACT_VERSION,
    PRINT_OBJECT_DOMAIN,
    PRINT_ORIENTATIONS,
    PRINT_PAPERS,
    PRINT_TEMPLATE_STATUSES,
    PRINT_TONES,
    BasePrintExporter,
    BasePrintTemplateProvider,
    PrintDocument,
    PrintOptions,
    PrintTemplateInfo,
    PrintVariable,
    build_print_object_key,
)
from bms_core.print.exporter import StoragePrintExporter
from bms_core.print.null import NullPrintExporter, NullPrintTemplateProvider
from bms_core.print.templates import (
    DEFAULT_DOCUMENT_TEMPLATE_KEY,
    DEFAULT_LIST_TEMPLATE_KEY,
    BuiltinPrintTemplateProvider,
)
from bms_core.storage.local import LocalObjectStorage
from bms_report.domains.report.api.print import router as print_router
from bms_report.main import ApplicationFactory
from tests_support.auth import auth_headers

API = "/api/v1/prints"

_TEMPLATE = PrintTemplateInfo(
    key="order",
    name="销售订单",
    biz_type="sale",
    variables=ConcurrentStableList([PrintVariable(key="customer", label="客户")]),
    status="active",
)


class _StubTemplateProvider:
    """模板来源测试替身：固定返回一条模板（覆盖模板映射分支；不参与注册表）。"""

    async def list(self, *, biz_type: str | None = None) -> ConcurrentStableList[PrintTemplateInfo]:
        """取模板清单（替身固定一条）。

        Args:
            biz_type: 单据类型（替身忽略）。

        Returns:
            ConcurrentStableList[PrintTemplateInfo]: 单条模板清单。
        """
        del biz_type
        return ConcurrentStableList([_TEMPLATE])

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
    """幂等基座测试替身：内存首次结果表。"""

    def __init__(self) -> None:
        """初始化空首次结果表。"""
        self.keys: ConcurrentStableList[str] = ConcurrentStableList()
        self._payloads: ConcurrentStableDict[str, IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableDict()

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键（首次为 True）。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 首次 True。
        """
        del ttl
        self.keys.add(key)
        return key not in self._payloads

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果载荷。

        Args:
            key: 幂等键。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次结果；未缓存为 None。
        """
        return self._payloads.get(key)

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int | None = None) -> None:
        """写首次结果。

        Args:
            key: 幂等键。
            payload: 首次结果载荷。
            ttl: 键有效期（替身忽略）。
        """
        del ttl
        self._payloads.set(key, payload)


def _real_exporter(
    storage: LocalObjectStorage, templates: BasePrintTemplateProvider | None = None
) -> BasePrintExporter:
    """构造真实打印导出（本地存储 + 内置模板）。

    Args:
        storage: 本地对象存储。
        templates: 模板来源（None 用内置）。

    Returns:
        BasePrintExporter: 真实导出器。
    """
    return StoragePrintExporter(storage=storage, templates=templates or BuiltinPrintTemplateProvider())


def _storage_root() -> Path:
    """独立临时存储根目录（避免写入仓库目录）。

    Returns:
        Path: 临时目录。
    """
    return Path(mkdtemp(prefix="print-artifacts-"))


@pytest.mark.kiwi_id(906)
def test_contract_inheritance_and_identity() -> None:
    """两契约继承能力端口与可插拔基类；打印导出契约版本 0.2.0。"""
    for contract in (BasePrintExporter, BasePrintTemplateProvider):
        assert issubclass(contract, BaseCapability)
        assert issubclass(contract, BasePluggable)
    for placeholder in (NullPrintExporter(), NullPrintTemplateProvider()):
        assert isinstance(placeholder, BaseNullObject)
    assert BasePrintExporter.contract_version == PRINT_CONTRACT_VERSION == "0.2.0"
    assert BasePrintExporter.key == "print_exporter"
    assert BasePrintTemplateProvider.key == "print_template"


@pytest.mark.kiwi_id(906)
def test_constants_and_object_key() -> None:
    """取值集合与产物 key（路径风格，Windows 安全）。"""
    assert PRINT_PAPERS == ("A4", "A5", "custom")
    assert PRINT_ORIENTATIONS == ("portrait", "landscape")
    assert PRINT_TONES == ("color", "mono")
    assert PRINT_BATCH_MODES == ("separate", "merged")
    assert PRINT_TEMPLATE_STATUSES == ("active", "disabled")
    assert PRINT_CONTENT_TYPE == "application/pdf"
    assert DEFAULT_PAPER == "A4"
    assert PRINT_OBJECT_DOMAIN == "prints"

    assert build_print_object_key(template_key="order", biz_key="SO-1") == "global/prints/order/SO-1.pdf"
    assert build_print_object_key(template_key="order", biz_key="SO-1", tenant="demo") == ("demo/prints/order/SO-1.pdf")
    sanitized = build_print_object_key(template_key="a:b", biz_key="x/y*z", tenant="demo")
    assert sanitized == "demo/prints/a_b/x_y_z.pdf"
    for char in (":", "*", "?", '"', "<", ">", "|"):
        assert char not in sanitized


@pytest.mark.kiwi_id(906)
def test_data_contract_defaults() -> None:
    """数据契约缺省值（单据 / 选项 / 模板）。"""
    document = PrintDocument()
    assert document.biz_key is None
    assert document.fields == {}
    assert document.rows == ()
    options = PrintOptions()
    assert options.paper == DEFAULT_PAPER
    assert options.orientation == "portrait"
    assert options.tone == "color"
    assert options.watermark == ""
    info = PrintTemplateInfo(key="k", name="n")
    assert info.variables == ()
    assert info.status == "active"


@pytest.mark.kiwi_id(906)
async def test_builtin_template_provider_lists_two() -> None:
    """内置模板来源：清单含通用单据 / 通用列表，未命中 50201。"""
    provider = BuiltinPrintTemplateProvider()
    templates = await provider.list()
    assert [item.key for item in templates] == [DEFAULT_DOCUMENT_TEMPLATE_KEY, DEFAULT_LIST_TEMPLATE_KEY]
    with pytest.raises(PrintTemplateNotFoundError):
        await provider.get("not-exists")


@pytest.mark.kiwi_id(906)
def test_error_codes_and_segment_base() -> None:
    """打印子段错误码与异常基类。"""
    assert ErrorCode.PRINT_TEMPLATE_NOT_FOUND == 50201
    assert ErrorCode.PRINT_ARTIFACT_NOT_FOUND == 50202
    assert ErrorCode.PRINT_BATCH_LIMIT_EXCEEDED == 50203
    assert issubclass(PrintError, FileError)
    assert issubclass(BizError, Exception)
    assert 50000 <= ErrorCode.PRINT_TEMPLATE_NOT_FOUND < 51000
    assert PrintBatchLimitError("超限").code == ErrorCode.PRINT_BATCH_LIMIT_EXCEEDED


@pytest.mark.kiwi_id(906)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：真实插件 `builtin` / `reportlab` 可解析（装配期不报错）。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        provider = resolve_plugin(
            "print_template", "builtin", expected_version=BasePrintTemplateProvider.contract_version
        )
        exporter = resolve_plugin("print_exporter", "reportlab", expected_version=BasePrintExporter.contract_version)
    assert isinstance(provider, BasePrintTemplateProvider)
    assert isinstance(exporter, BasePrintExporter)


@pytest.mark.kiwi_id(906)
def test_route_paths_registered() -> None:
    """打印路由路径登记齐全。"""
    paths: set[str] = {cast("APIRoute", route).path for route in print_router.routes}
    assert "/prints/exports" in paths
    assert "/prints/batch" in paths
    assert "/prints/templates" in paths
    assert "/prints/templates/{template_key}" in paths


@pytest.mark.kiwi_id(906)
async def test_real_export_pdf_and_template_routes(service_app: FastAPI) -> None:
    """真实导出：单条 PDF 落存储并返回取址；模板清单 / 详情走内置来源。"""
    storage = LocalObjectStorage(root=_storage_root())
    service_app.dependency_overrides[get_print_exporter] = lambda: _real_exporter(storage)
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
            client.headers.update(auth_headers())
            listed = await client.get(f"{API}/templates")
            assert listed.status_code == 200
            keys = [item["key"] for item in listed.json()["data"]["templates"]]
            assert DEFAULT_DOCUMENT_TEMPLATE_KEY in keys

            detail = await client.get(f"{API}/templates/{DEFAULT_DOCUMENT_TEMPLATE_KEY}")
            assert detail.status_code == 200
            assert detail.json()["data"]["name"] == "通用单据"

            missing = await client.get(f"{API}/templates/not-exists")
            assert missing.json()["code"] == ErrorCode.PRINT_TEMPLATE_NOT_FOUND

            exported = await client.post(
                f"{API}/exports",
                json={  # pyright: ignore[reportUnknownArgumentType]
                    "template_key": DEFAULT_DOCUMENT_TEMPLATE_KEY,
                    "document": {"biz_key": "SO-1", "fields": {"客户": "示例"}, "rows": [{"项目": "A", "金额": 10}]},
                },
            )
            assert exported.status_code == 200, exported.text
            artifact = exported.json()["data"]
            assert artifact["content_type"] == PRINT_CONTENT_TYPE
            assert artifact["url"]
            assert (await storage.get(artifact["object_key"])).startswith(b"%PDF")
    finally:
        service_app.dependency_overrides.pop(get_print_exporter, None)


@pytest.mark.kiwi_id(906)
async def test_real_batch_print_separate_and_merged(service_app: FastAPI) -> None:
    """真实批量打印：逐份多产物 / 合并单份；documents 缺省渲染简版页。"""
    storage = LocalObjectStorage(root=_storage_root())
    service_app.dependency_overrides[get_print_exporter] = lambda: _real_exporter(storage)
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
            client.headers.update(auth_headers())
            separate = await client.post(
                f"{API}/batch",
                json={  # pyright: ignore[reportUnknownArgumentType]
                    "template_key": DEFAULT_DOCUMENT_TEMPLATE_KEY,
                    "keys": ["A", "B"],
                    "documents": [{"biz_key": "A", "fields": {}}, {"biz_key": "B", "fields": {}}],
                },
            )
            assert separate.status_code == 200, separate.text
            data = separate.json()["data"]
            assert data["succeeded"] == 2
            assert len(data["items"]) == 2

            merged = await client.post(
                f"{API}/batch",
                json={"template_key": DEFAULT_DOCUMENT_TEMPLATE_KEY, "keys": ["A", "B"], "mode": "merged"},  # pyright: ignore[reportUnknownArgumentType]
            )
            assert merged.status_code == 200, merged.text
            merged_data = merged.json()["data"]
            assert len(merged_data["items"]) == 1
            assert merged_data["items"][0]["object_key"].endswith("A-merged.pdf")
    finally:
        service_app.dependency_overrides.pop(get_print_exporter, None)


@pytest.mark.kiwi_id(906)
async def test_export_idempotency_reuses_first_result(service_app: FastAPI) -> None:
    """同幂等键：第二次直接复用首次产物（不再渲染）。"""
    storage = LocalObjectStorage(root=_storage_root())
    idempotency = _RecordingIdempotency()
    service_app.dependency_overrides[get_print_exporter] = lambda: _real_exporter(storage)
    service_app.dependency_overrides[get_idempotency_store] = lambda: idempotency
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
            client.headers.update(auth_headers())
            body = {"template_key": DEFAULT_DOCUMENT_TEMPLATE_KEY, "document": {"biz_key": "SO-9"}}
            headers = {"Idempotency-Key": "print-1"}
            first = await client.post(f"{API}/exports", json=body, headers=headers)
            second = await client.post(f"{API}/exports", json=body, headers=headers)
            assert first.json()["data"]["object_key"] == second.json()["data"]["object_key"]
            assert len(set(idempotency.keys)) == 1
    finally:
        service_app.dependency_overrides.pop(get_print_exporter, None)
        service_app.dependency_overrides.pop(get_idempotency_store, None)


@pytest.mark.kiwi_id(906)
async def test_prints_requires_auth() -> None:
    """未登录访问打印端点：401。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"{API}/templates")
    assert response.status_code == 401


@pytest.mark.kiwi_id(906)
async def test_templates_mapping_with_stub_provider(service_app: FastAPI) -> None:
    """模板来源替身：清单 / 详情映射为响应契约（变量一一对应）。"""
    from bms_core.api.deps import get_print_template_provider

    service_app.dependency_overrides[get_print_template_provider] = lambda: _StubTemplateProvider()
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
            client.headers.update(auth_headers())
            listed = await client.get(f"{API}/templates")
            assert listed.status_code == 200
            data = listed.json()["data"]["templates"][0]
            assert data["key"] == "order"
            assert data["variables"][0]["label"] == "客户"
            detail = await client.get(f"{API}/templates/order")
            assert detail.json()["data"]["biz_type"] == "sale"
    finally:
        service_app.dependency_overrides.pop(get_print_template_provider, None)
