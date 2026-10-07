"""服务目录与产品档案清单校验测试（Kiwi 28 / 2162 / 2163 / 2249 / 2250）。

覆盖清单结构 / 分组 / 唯一性与格式校验 / 产品归属与对账 / 产品级路由映射校验 / 模型落库 / 接库校验。
"""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine, Table, UniqueConstraint, create_engine, select
from sqlalchemy.orm import Session

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.services.module_registry import (
    PLATFORM_MODULES,
    PRODUCT_CATALOG,
    PRODUCT_ROUTES,
    SERVICE_CATALOG,
    ModuleRecord,
    ModuleRegistry,
    ModuleStatus,
    ProductRecord,
    ProductRegistry,
    ProductRouteRecord,
    ProductStatus,
    ServiceGroup,
    product_keys,
    validate_catalog,
    validate_product_routes,
    validate_products,
)
from bms_platform.models.catalog import SysModule, SysModuleI18n, SysProduct

_BASE_RECORD = ModuleRecord(
    module_key="pur",
    name="测试",
    table_prefix="pur_",
    event_domain="pur",
    errcode_segment="10",
    service_group=ServiceGroup.PRODUCT,
    product_key="biz",
)


def _record(module_key: str = "pur", **overrides: object) -> ModuleRecord:
    """构造测试注册记录（默认满足格式与产品维度一致性）。"""
    fields: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "module_key": module_key,
            "table_prefix": f"{module_key}_",
            "event_domain": module_key,
        }
    )
    fields.update(overrides.items())
    return replace(_BASE_RECORD, **fields)  # pyright: ignore[reportCallIssue, reportArgumentType]


@pytest.mark.kiwi_id(2162)
def test_service_catalog_shape() -> None:
    """服务目录清单：16 行（平台服务 9 + 产品服务 7，`org` 归 mdm），分组 / 批次 / 版本齐备。"""
    keys = [module.module_key for module in SERVICE_CATALOG]
    assert len(SERVICE_CATALOG) == 16
    assert keys == [
        "sys",
        "identity",
        "tenant",
        "org",
        "file",
        "notification",
        "search",
        "ai",
        "rpt",
        "wf",
        "pur",
        "pay",
        "sale",
        "wh",
        "sup",
        "cw",
    ]
    services = [module for module in SERVICE_CATALOG if module.service_key]
    assert len(services) == 10
    assert {module.service_key for module in services} == {
        "platform",
        "identity",
        "tenant",
        "org",
        "file",
        "notification",
        "search",
        "ai",
        "report",
        "workflow",
    }
    assert [module.module_key for module in PLATFORM_MODULES] == ["sys", "wf", "rpt", "ai"]
    assert [module.module_key for module in ModuleRegistry().list_modules(group=ServiceGroup.PRODUCT)] == [
        "org",
        "pur",
        "pay",
        "sale",
        "wh",
        "sup",
        "cw",
    ]
    assert [module.module_key for module in ModuleRegistry().list_modules(status=ModuleStatus.PLANNED)] == [
        "wf",
        "pur",
        "pay",
        "sale",
        "wh",
        "sup",
        "cw",
    ]
    for module in SERVICE_CATALOG:
        assert module.service_version == "0.1.0"
        # 平台服务（`sys`）契约随 02_03「`sys_form` 多对多」破坏性变更升 0.2.0；其余模块保持 0.1.0
        assert module.contract_version == ("0.2.0" if module.module_key == "sys" else "0.1.0")


@pytest.mark.kiwi_id(28)
def test_validate_accepts_legal_registry() -> None:
    """合法清单：服务目录与业务模块均通过（自定义小清单显式给空路由映射，隔离产品路由校验）。"""
    assert ModuleRegistry().validate() == []
    assert (
        ModuleRegistry(
            ConcurrentStableList([_record(), _record("sale", errcode_segment="12")]),
            routes=ConcurrentStableList(),
        ).validate()
        == []
    )


@pytest.mark.kiwi_id(28)
def test_validate_detects_duplicates() -> None:
    """唯一性：module_key / table_prefix / event_domain 与可空列（service_key / 段位）重复均检出。"""
    registry = ModuleRegistry(
        ConcurrentStableList(
            [
                _record("pur"),
                _record("pur", name="采购2"),
                _record("sale", table_prefix="pur_", event_domain="pur"),
                _record("wh", service_key="biz", errcode_segment="11"),
                _record("sup", service_key="biz", errcode_segment="11"),
            ]
        )
    )
    errors = registry.validate()
    assert any("module_key 重复" in e for e in errors)
    assert any("table_prefix 重复" in e for e in errors)
    assert any("event_domain 重复" in e for e in errors)
    assert any("service_key 重复" in e for e in errors)
    assert any("errcode_segment 重复" in e for e in errors)


@pytest.mark.kiwi_id(28)
def test_validate_detects_bad_format() -> None:
    """格式 / 分组 / 版本：非法前缀、段号、事件域、分组、批次、semver、产品维度均检出。"""
    registry = ModuleRegistry(
        ConcurrentStableList(
            [
                _record("Bad", table_prefix="Bad", event_domain="Bad-Domain", errcode_segment="0"),
                _record("pur", service_group="unknown", build_batch=9, service_version="1.0"),
                _record("pay", product_key=None),
                _record("wh", service_key="Bad Key"),
            ]
        )
    )
    errors = registry.validate()
    assert any("module_key 非法" in e for e in errors)
    assert any("service_key 非法" in e for e in errors)
    assert any("table_prefix 非法" in e for e in errors)
    assert any("event_domain 非法" in e for e in errors)
    assert any("errcode_segment 非法" in e for e in errors)
    assert any("service_group 非法" in e for e in errors)
    assert any("build_batch 越界" in e for e in errors)
    assert any("service_version 非 semver" in e for e in errors)
    joined = "；".join(errors)
    assert "产品分组缺 product_key" in joined
    assert "非产品分组不应有 product_key" in joined


@pytest.mark.kiwi_id(2162)
def test_models_declared_and_persistable(tmp_path: Path) -> None:
    """模型声明：新字段可建表 / 落库；DB 唯一仅 module_key / table_prefix / event_domain。"""
    assert {"sys_module", "sys_module_i18n"} <= set(Base.metadata.tables)
    unique_names = {
        constraint.name for constraint in SysModule.__table_args__ if isinstance(constraint, UniqueConstraint)
    }
    assert unique_names == {
        "uq_sys_module_key_deleted_at",
        "uq_sys_module_prefix_deleted_at",
        "uq_sys_module_domain_deleted_at",
    }
    columns = SysModule.__table__.columns
    assert columns["service_key"].nullable is True
    assert columns["errcode_segment"].nullable is True
    assert columns["product_key"].nullable is True
    assert columns["service_group"].nullable is False

    engine: Engine = create_engine(f"sqlite:///{tmp_path / 'module.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        module = SysModule(
            module_key="identity",
            service_key="identity",
            name="认证与身份服务",
            table_prefix="identity_",
            event_domain="identity",
            service_group="foundation",
            build_batch=0,
        )
        session.add(module)
        session.commit()
        i18n = SysModuleI18n(module_id=module.id, locale="zh-CN", name="认证与身份服务")
        session.add(i18n)
        session.commit()
        assert module.id > 0
        assert module.errcode_segment is None
        assert i18n.id > 0
    engine.dispose()


@pytest.mark.kiwi_id(2163)
def test_module_record_from_row_matches_catalog() -> None:
    """ORM 行转换：按目录字段取值，与清单 identity 行完全一致（接库对账的转换口径）。"""
    row = SysModule(
        module_key="identity",
        service_key="identity",
        name="认证与身份服务",
        table_prefix="identity_",
        event_domain="identity",
        service_group="foundation",
        build_batch=0,
        service_version="0.1.0",
        contract_version="0.1.0",
        status="enabled",
    )
    assert ModuleRecord.from_row(row) == SERVICE_CATALOG[1]


def _catalog_records() -> ConcurrentStableList[ModuleRecord]:
    """服务目录的插入序副本（接库对账用例的「库中行」基线）。

    Returns:
        ConcurrentStableList[ModuleRecord]: 服务目录副本。
    """
    return ConcurrentStableList(SERVICE_CATALOG)


def _replaced(
    catalog: ConcurrentStableList[ModuleRecord], index: int, **changes: object
) -> ConcurrentStableList[ModuleRecord]:
    """按序号替换一条目录行（集合类无下标赋值，按插入序重建）。

    Args:
        catalog: 服务目录清单。
        index: 待替换行序号。
        changes: 字段替换值。

    Returns:
        ConcurrentStableList[ModuleRecord]: 替换后的目录副本。
    """
    return ConcurrentStableList(
        replace(record, **changes) if position == index else record for position, record in enumerate(catalog)
    )


@pytest.mark.kiwi_id(2163)
def test_validate_catalog_roundtrip_and_conflicts() -> None:
    """接库校验：清单自身与主版本兼容通过；缺行 / 清单外 / 字段 / 主版本 / 运行服务逐项检出。"""
    catalog = _catalog_records()
    assert validate_catalog(catalog, _catalog_records()) == []
    assert validate_catalog(catalog, _catalog_records(), service_key="platform", contract_version="0.1.0") == []

    records = _replaced(catalog, 1, contract_version="0.2.0")
    assert validate_catalog(catalog, records) == []

    records = _replaced(catalog, 1, contract_version="1.0.0")
    assert any("契约版本主版本不兼容" in error for error in validate_catalog(catalog, records))

    records = _catalog_records()
    records.remove(catalog[1])
    assert any("库中缺登记行：identity" in error for error in validate_catalog(catalog, records))

    records = _catalog_records()
    records.add(
        ModuleRecord(
            module_key="ghost",
            name="幽灵模块",
            table_prefix="ghost_",
            event_domain="ghost",
            service_group=ServiceGroup.CAPABILITY,
        )
    )
    assert any("库中登记行不在清单：ghost" in error for error in validate_catalog(catalog, records))

    records = _replaced(catalog, 1, name="改过的名字")
    assert any("name 与清单不一致" in error for error in validate_catalog(catalog, records))


@pytest.mark.kiwi_id(2163)
def test_validate_catalog_running_service_rules() -> None:
    """运行服务项：主版本兼容通过；未登记 / 自报非法 / 登记非法逐项检出。"""
    catalog = _catalog_records()

    records = _replaced(catalog, 1, service_key=None)
    errors = validate_catalog(catalog, records, service_key="identity", contract_version="0.1.0")
    assert any("运行服务未登记：identity" in error for error in errors)

    errors = validate_catalog(catalog, _catalog_records(), service_key="platform", contract_version="0.1")
    assert any("运行服务契约版本非法" in error for error in errors)

    records = _replaced(catalog, 0, contract_version="bad")
    errors = validate_catalog(catalog, records, service_key="platform", contract_version="0.1.0")
    assert any("登记契约版本非法" in error for error in errors)


@pytest.mark.kiwi_id(2249)
def test_product_catalog_shape() -> None:
    """产品档案清单：三行（biz / cw / mdm 均已接入），状态齐备；模块产品归属均落在清单内。"""
    assert [product.product_key for product in PRODUCT_CATALOG] == ["biz", "cw", "mdm"]
    assert product_keys() == {"biz", "cw", "mdm"}
    assert {product.product_key: product.status for product in PRODUCT_CATALOG} == {
        "biz": ProductStatus.ENABLED,
        "cw": ProductStatus.ENABLED,
        "mdm": ProductStatus.ENABLED,
    }
    # 前端包来源本期留空（详设 12_01 §9：随 R4.3 前端多包合并回填）
    assert all(product.frontend_package_source is None for product in PRODUCT_CATALOG)
    assert len(ProductRegistry().list_products()) == 3
    assert ProductRegistry().list_products(status=ProductStatus.PLANNED) == []
    # 服务目录中产品模块的 product_key 均须已登记（`mdm` 随 01_01 工程骨架接入，其 `org` 行已登记）
    assert {module.product_key for module in SERVICE_CATALOG if module.product_key} <= product_keys()


@pytest.mark.kiwi_id(2249)
def test_product_registry_validate_and_conflicts() -> None:
    """产品档案校验：合法通过；非法标识 / 空名 / 非法状态 / 空串来源 / 标识重复逐项检出。"""
    assert ProductRegistry().validate() == []
    registry = ProductRegistry(
        ConcurrentStableList(
            [
                ProductRecord(product_key="Bad", name="非法标识"),
                ProductRecord(product_key="ok", name="   "),
                ProductRecord(product_key="bad_status", name="状态非法", status="unknown"),
                ProductRecord(product_key="empty_source", name="空串来源", frontend_package_source="  "),
                ProductRecord(product_key="dup", name="重复甲"),
                ProductRecord(product_key="dup", name="重复乙"),
            ]
        )
    )
    joined = "；".join(registry.validate())
    assert "product_key 非法" in joined
    assert "name 为空" in joined
    assert "status 非法" in joined
    assert "frontend_package_source 为空串" in joined
    assert "product_key 重复：dup" in joined


@pytest.mark.kiwi_id(2249)
def test_module_product_ownership_rules() -> None:
    """产品归属：产品分组模块的 `product_key` 须在产品清单登记；未登记即拒（可注入自定义清单）。"""
    assert (
        ModuleRegistry(
            ConcurrentStableList([_record("pur", product_key="biz")]),
            routes=ConcurrentStableList(),
        ).validate()
        == []
    )
    errors = ModuleRegistry(
        ConcurrentStableList([_record("pur", product_key="ghost")]),
        routes=ConcurrentStableList(),
    ).validate()
    assert any("product_key 未登记（ghost）" in error for error in errors)

    # 产品服务装配（12_03）注入自定义产品清单时，归属基准随之收窄
    errors = ModuleRegistry(
        ConcurrentStableList([_record("pur", product_key="biz")]),
        ConcurrentStableList([ProductRecord(product_key="mdm", name="主数据管理")]),
        routes=ConcurrentStableList(),
    ).validate()
    assert any("product_key 未登记（biz）" in error for error in errors)


@pytest.mark.kiwi_id(2249)
def test_validate_products_roundtrip_and_drift() -> None:
    """产品档案接库对账：清单自身通过；缺行 / 清单外行 / 字段不符逐项检出。"""
    products = ConcurrentStableList(PRODUCT_CATALOG)
    assert validate_products(products, ConcurrentStableList(PRODUCT_CATALOG)) == []

    records = ConcurrentStableList(PRODUCT_CATALOG)
    records.remove(PRODUCT_CATALOG[1])
    assert any("产品档案库中缺登记行：cw" in error for error in validate_products(products, records))

    records = ConcurrentStableList(PRODUCT_CATALOG)
    records.add(ProductRecord(product_key="ghost", name="幽灵产品"))
    assert any("产品档案库中登记行不在清单：ghost" in error for error in validate_products(products, records))

    records = ConcurrentStableList(
        replace(record, status=ProductStatus.PLANNED) if record.product_key == "mdm" else record
        for record in PRODUCT_CATALOG
    )
    assert any("status 与清单不一致" in error for error in validate_products(products, records))


@pytest.mark.kiwi_id(2249)
def test_sys_product_model_declared_and_persistable(tmp_path: Path) -> None:
    """模型声明：`sys_product` 在元数据中、唯一约束 `(product_key, deleted_at)`、软删除索引；可建表落库且键可复用。"""
    assert "sys_product" in Base.metadata.tables
    unique_names = {
        constraint.name for constraint in SysProduct.__table_args__ if isinstance(constraint, UniqueConstraint)
    }
    assert unique_names == {"uq_sys_product_key_deleted_at"}
    assert {index.name for index in cast("Table", SysProduct.__table__).indexes} == {"idx_sys_product_deleted_at"}
    columns = SysProduct.__table__.columns
    assert columns["product_key"].nullable is False
    assert columns["frontend_package_source"].nullable is True
    assert columns["status"].default.arg == ProductStatus.ENABLED

    engine: Engine = create_engine(f"sqlite:///{tmp_path / 'product.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = SysProduct(product_key="mdm", name="主数据管理", status=ProductStatus.PLANNED)
        session.add(first)
        session.commit()
        assert first.id > 0
        first.soft_delete()
        session.commit()
        session.add(SysProduct(product_key="mdm", name="主数据管理", status=ProductStatus.ENABLED))
        session.commit()
        rows = session.execute(select(SysProduct).where(SysProduct.product_key == "mdm")).scalars().all()
        assert len(rows) == 2
        assert sorted(row.deleted_at is None for row in rows) == [False, True]
    engine.dispose()


def _route(
    domain: str = "org",
    *,
    service_key: str = "mdm-org",
    product_key: str = "biz",
) -> ProductRouteRecord:
    """构造产品级路由映射记录。

    Args:
        domain: 外部域段。
        service_key: 上游服务标识。
        product_key: 归属产品标识。

    Returns:
        ProductRouteRecord: 路由映射记录。
    """
    return ProductRouteRecord(product_key=product_key, domain=domain, service_key=service_key)


def _route_modules(*records: ModuleRecord) -> ConcurrentStableList[ModuleRecord]:
    """路由校验用模块清单（默认一条产品分组服务行）。

    Args:
        *records: 自定义模块记录；缺省取 `mdm_org` 服务行。

    Returns:
        ConcurrentStableList[ModuleRecord]: 模块清单。
    """
    if records:
        return ConcurrentStableList(records)
    return ConcurrentStableList([_record("mdm_org", service_key="mdm-org", product_key="biz")])


@pytest.mark.kiwi_id(2250)
def test_product_routes_default_registered_mdm_org() -> None:
    """默认产品级路由映射：`mdm/org → org` 一条（随产品接入登记完成）；默认清单校验无路由违规。"""
    assert [(record.product_key, record.domain, record.service_key) for record in PRODUCT_ROUTES] == [
        ("mdm", "org", "org")
    ]
    errors = ModuleRegistry().validate()
    assert not any("产品级路由" in error for error in errors)
    assert (
        validate_product_routes(ConcurrentStableList(), _route_modules(), ConcurrentStableList(PRODUCT_CATALOG)) == []
    )


@pytest.mark.kiwi_id(2250)
def test_validate_product_routes_accepts_registered_product_service() -> None:
    """合法映射通过：产品已登记、目标服务为产品分组且产品归属一致；`planned`（先注册后建表）放行。"""
    products = ConcurrentStableList(PRODUCT_CATALOG)
    assert validate_product_routes(ConcurrentStableList([_route()]), _route_modules(), products) == []
    planned = _route_modules(_record("mdm_org", service_key="mdm-org", product_key="biz", status=ModuleStatus.PLANNED))
    assert validate_product_routes(ConcurrentStableList([_route()]), planned, products) == []


@pytest.mark.kiwi_id(2250)
def test_validate_product_routes_conflicts_detected() -> None:
    """冲突逐项检出：域段 / 服务键格式、产品未登记、目标服务未登记 / 非产品分组 / 归属不一致 / 已停用、重复项。"""
    products = ConcurrentStableList(PRODUCT_CATALOG)
    modules = _route_modules(
        _record("mdm_org", service_key="mdm-org", product_key="biz"),
        _record("sysx", service_key="sys-svc", product_key="biz", service_group=ServiceGroup.FOUNDATION),
        _record("cwx", service_key="cw-svc", product_key="cw"),
        _record("old", service_key="old-svc", product_key="biz", status=ModuleStatus.DISABLED),
    )
    joined = "；".join(
        validate_product_routes(
            ConcurrentStableList(
                [
                    _route(domain="Org"),
                    _route("bad-svc", service_key="_bad"),
                    _route("ghost-product", product_key="ghost"),
                    _route("missing-svc", service_key="ghost-svc"),
                    _route("foundation-svc", service_key="sys-svc"),
                    _route("cw-mismatch", service_key="cw-svc"),
                    _route("old-svc", service_key="old-svc"),
                ]
            ),
            modules,
            products,
        )
    )
    assert "域段非法（Org）" in joined
    assert "service_key 非法（_bad）" in joined
    assert "product_key 未登记（ghost）" in joined
    assert "目标服务未登记（ghost-svc）" in joined
    assert "目标服务非产品分组（foundation）" in joined
    assert "目标服务产品归属不一致（cw）" in joined
    assert "目标服务已停用（disabled）" in joined

    duplicated = validate_product_routes(
        ConcurrentStableList([_route("org"), _route("org")]),
        _route_modules(),
        products,
    )
    assert any("产品级路由 domain 重复：org" in error for error in duplicated)


@pytest.mark.kiwi_id(2250)
def test_module_registry_validates_product_routes_via_injection() -> None:
    """映射随 `ModuleRegistry.validate()` 一并校验（离线对清单 / 接库对库中行，同一实现）。"""
    products = ConcurrentStableList(PRODUCT_CATALOG)
    modules = _route_modules(_record("cwx", service_key="cw-svc", product_key="cw"))
    routes = ConcurrentStableList([_route("org", service_key="cw-svc")])
    assert ModuleRegistry(modules, products, routes).validate()  # product_key 不一致 → 检出
    assert any(
        "目标服务产品归属不一致（cw）" in error for error in ModuleRegistry(modules, products, routes).validate()
    )
    ok_routes = ConcurrentStableList([_route("org", service_key="cw-svc", product_key="cw")])
    assert ModuleRegistry(modules, products, ok_routes).validate() == []


@pytest.mark.kiwi_id(2250)
def test_validate_catalog_unaffected_by_route_validation() -> None:
    """接库校验入口（`validate_catalog`）在映射为空清单时不引入新失败（启动 / CI 口径不变）。"""
    catalog = ConcurrentStableList(SERVICE_CATALOG)
    assert validate_catalog(catalog, catalog) == []
