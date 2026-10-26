"""产品登记清单解析与装载（Kiwi 2359）：结构校验 / 归属校验 / 缺省降级 / 相对路径基准。

口径（04_05 决策 q2=B）：清单相对路径按**后端工程根**解析（不随工作目录变化）；
本套用例覆盖解析的全部错误分支与缺省降级，装配期的视图合并由注入表用例另行覆盖。
"""

# pyright: reportUnusedFunction=false
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import bms_core.registry.products as products
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.datasource.registry import data_source_records_view, reset_data_source_records
from bms_core.registry.products import (
    ProductManifest,
    load_product_manifest,
    load_product_manifests,
    register_manifest,
)
from bms_core.services.module_registry import (
    product_catalog_view,
    product_routes_view,
    reset_product_records,
    reset_product_routes,
    reset_service_records,
    service_catalog_view,
)


def _full_payload() -> Any:
    """完整清单内容（四类记录各一条）。

    Returns:
        Any: 清单内容（可直接 JSON 序列化）。
    """
    return {
        "product_key": "demo",
        "products": [
            {
                "product_key": "demo",
                "name": "演示产品",
                "frontend_package_source": "demo#frontend",
                "status": "enabled",
            }
        ],
        "services": [
            {
                "module_key": "demo",
                "service_key": "demo",
                "name": "演示服务",
                "table_prefix": "demo_",
                "business_code": "demo",
                "errcode_segment": "39",
                "event_domain": "demo",
                "service_group": "product",
                "build_batch": 3,
                "service_version": "0.2.0",
                "contract_version": "0.2.0",
                "product_key": "demo",
                "status": "enabled",
            }
        ],
        "product_routes": [{"product_key": "demo", "domain": "demo", "service_key": "demo", "description": "演示域"}],
        "data_sources": [
            {
                "data_source_key": "demo_dept",
                "name": "部门",
                "data_source": "demo.demo.dept",
                "kind": "dict",
                "origin": "product",
                "product_key": "demo",
                "path": "/data-source/dept-tree",
                "allowlist": ["code", "label"],
                "cascade": True,
                "strategies": ["select", "region"],
                "status": "enabled",
            }
        ],
    }


def _write(tmp_path: Path, payload: object, name: str = "demo.json") -> Path:
    """把清单内容写到临时目录。

    Args:
        tmp_path: 临时目录。
        payload: 清单内容（可为非法结构，用于反例）。
        name: 文件名。

    Returns:
        Path: 清单文件路径。
    """
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _reset_catalogs() -> None:
    """清空四张注入登记表（用例隔离用）。"""
    reset_service_records()
    reset_product_records()
    reset_product_routes()
    reset_data_source_records()


@pytest.fixture(autouse=True)
def _isolate_catalogs() -> Iterator[None]:
    """每例前后清空注入登记表（进程级全局状态，不污染其他用例）。

    Yields:
        None: 用例运行期。
    """
    _reset_catalogs()
    yield
    _reset_catalogs()


@pytest.mark.kiwi_id(2359)
def test_load_full_manifest(tmp_path: Path) -> None:
    """完整清单：四类记录逐字段解析（含可选字段与缺省值）。"""
    manifest = load_product_manifest(_write(tmp_path, _full_payload()))

    assert isinstance(manifest, ProductManifest)
    assert manifest.product_key == "demo"
    product = manifest.products[0]
    assert (product.product_key, product.name, product.frontend_package_source) == ("demo", "演示产品", "demo#frontend")
    service = manifest.services[0]
    assert service.service_key == "demo"
    assert service.business_code == "demo"
    assert service.errcode_segment == "39"
    assert service.service_version == "0.2.0"
    assert service.build_batch == 3
    route = manifest.product_routes[0]
    assert (route.domain, route.service_key, route.description) == ("demo", "demo", "演示域")
    data_source = manifest.data_sources[0]
    assert data_source.data_source_key == "demo_dept"
    assert data_source.allowlist == ["code", "label"]
    assert data_source.strategies == ["select", "region"]
    assert data_source.cascade is True


@pytest.mark.kiwi_id(2359)
def test_load_minimal_manifest_defaults(tmp_path: Path) -> None:
    """最简清单：缺省键为空列表，可选字段走缺省值（不静默使用旧值）。"""
    payload: Any = {
        "product_key": "demo",
        "services": [{"module_key": "demo", "name": "演示服务", "table_prefix": "demo_", "event_domain": "demo"}],
        "data_sources": [{"data_source_key": "demo_dept", "name": "部门", "data_source": "demo.demo.dept"}],
    }

    manifest = load_product_manifest(_write(tmp_path, payload))

    assert manifest.products == []
    assert manifest.product_routes == []
    service = manifest.services[0]
    assert service.service_key is None
    assert service.business_code is None
    assert service.errcode_segment is None
    assert service.service_group == "product"
    assert service.build_batch == 0
    assert service.service_version == "0.1.0"
    assert service.contract_version == "0.1.0"
    assert service.product_key == "demo"
    assert service.status == "enabled"
    data_source = manifest.data_sources[0]
    assert data_source.kind == "dict"
    assert data_source.origin == "product"
    assert data_source.path is None
    assert data_source.allowlist == []
    assert data_source.cascade is False
    assert data_source.strategies == ["select"]


@pytest.mark.kiwi_id(2359)
def test_load_manifest_rejects_structure_errors(tmp_path: Path) -> None:
    """结构反例：根非对象 / 记录非对象 / 数组非数组 / 必填缺失或空串 一律拒绝。"""
    with pytest.raises(CatalogError, match="记录须为对象"):
        load_product_manifest(_write(tmp_path, ["demo"]))

    with pytest.raises(CatalogError, match="须为数组"):
        load_product_manifest(_write(tmp_path, {"product_key": "demo", "services": {}}, "array.json"))

    with pytest.raises(CatalogError, match="记录须为对象"):
        load_product_manifest(_write(tmp_path, {"product_key": "demo", "services": [1]}, "element.json"))

    with pytest.raises(CatalogError, match="缺少必填字段"):
        missing: Any = {
            "product_key": "demo",
            "services": [{"module_key": "demo", "name": "演示", "event_domain": "demo"}],
        }
        load_product_manifest(_write(tmp_path, missing, "missing.json"))

    with pytest.raises(CatalogError, match="缺少必填字段"):
        blank: Any = {
            "product_key": "demo",
            "services": [{"module_key": "demo", "name": "", "table_prefix": "demo_", "event_domain": "demo"}],
        }
        load_product_manifest(_write(tmp_path, blank, "blank.json"))

    with pytest.raises(CatalogError, match="缺少必填字段"):
        load_product_manifest(_write(tmp_path, {"products": []}, "no_key.json"))


@pytest.mark.kiwi_id(2359)
def test_load_manifest_rejects_ownership_mismatch(tmp_path: Path) -> None:
    """归属反例：产品档案 / 服务行 / 产品路由 / 数据源条目与文件 `product_key` 不符即拒。"""
    cases: Any = (
        ("products", "产品档案归属不符"),
        ("services", "服务行产品归属不符"),
        ("product_routes", "路由归属不符"),
        ("data_sources", "数据源产品归属不符"),
    )
    for field, message in cases:
        payload = _full_payload()
        records = payload[field]
        payload[field] = [dict(record, product_key="other") for record in records]
        with pytest.raises(CatalogError, match=message):
            load_product_manifest(_write(tmp_path, payload, f"{field}.json"))


@pytest.mark.kiwi_id(2359)
def test_load_manifest_non_sequence_strings(tmp_path: Path) -> None:
    """`allowlist` / `strategies` 非数组时按空清单处理（数组类策略再回落缺省 `select`）。"""
    payload = _full_payload()
    payload["data_sources"] = [dict(payload["data_sources"][0], allowlist="code", strategies="select")]

    manifest = load_product_manifest(_write(tmp_path, payload))

    assert manifest.data_sources[0].allowlist == []
    assert manifest.data_sources[0].strategies == ["select"]


@pytest.mark.kiwi_id(2359)
def test_load_manifest_file_errors(tmp_path: Path) -> None:
    """文件反例：路径不可读 / JSON 非法均转 `CatalogError`。"""
    with pytest.raises(CatalogError, match="不可读"):
        load_product_manifest(tmp_path / "missing.json")

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(CatalogError, match="JSON 非法"):
        load_product_manifest(broken)


@pytest.mark.kiwi_id(2359)
def test_register_manifest_feeds_all_views(tmp_path: Path) -> None:
    """装载即注册：服务行 / 产品档案 / 产品路由 / 数据源条目四类视图各增一条。"""
    manifest = load_product_manifest(_write(tmp_path, _full_payload()))

    register_manifest(manifest)

    assert "demo" in [record.module_key for record in service_catalog_view()]
    assert "demo" in [record.product_key for record in product_catalog_view()]
    assert "demo" in [record.product_key for record in product_routes_view()]
    assert "demo_dept" in [record.data_source_key for record in data_source_records_view()]


@pytest.mark.kiwi_id(2359)
def test_load_manifests_resolves_relative_path_by_backend_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """相对路径按后端工程根解析（04_05 q2=B）：与工作目录无关；不存在路径静默跳过。"""
    backend = tmp_path / "backend"
    registry = backend / "deploy" / "registry"
    registry.mkdir(parents=True)
    (registry / "demo.json").write_text(json.dumps(_full_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)

    loaded = load_product_manifests(ConcurrentStableList(["deploy/registry/demo.json", "deploy/registry/none.json"]))

    assert len(loaded) == 1
    assert loaded[0].product_key == "demo"
    assert "demo" in [record.module_key for record in service_catalog_view()]
    assert load_product_manifests(ConcurrentStableList([tmp_path / "absent.json"])) == []
