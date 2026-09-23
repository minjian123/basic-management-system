"""服务目录清单与校验测试（Kiwi 28 / 2162 / 2163）：清单结构 / 分组 / 唯一性与格式校验 / 模型落库 / 接库校验。"""

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, UniqueConstraint, create_engine
from sqlalchemy.orm import Session

from bms_core.models.base import Base
from bms_core.services.module_registry import (
    PLATFORM_MODULES,
    SERVICE_CATALOG,
    ModuleRecord,
    ModuleRegistry,
    ModuleStatus,
    ServiceGroup,
    validate_catalog,
)
from bms_platform.models.catalog import SysModule, SysModuleI18n

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
    fields: dict[str, object] = {
        "module_key": module_key,
        "table_prefix": f"{module_key}_",
        "event_domain": module_key,
    }
    fields.update(overrides)
    return replace(_BASE_RECORD, **fields)  # pyright: ignore[reportCallIssue, reportArgumentType]


@pytest.mark.kiwi_id(2162)
def test_service_catalog_shape() -> None:
    """服务目录清单：16 行（平台服务 10 + 业务模块 6），分组 / 批次 / 版本齐备。"""
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
        assert module.contract_version == "0.1.0"


@pytest.mark.kiwi_id(28)
def test_validate_accepts_legal_registry() -> None:
    """合法清单：服务目录与业务模块均通过。"""
    assert ModuleRegistry().validate() == []
    assert ModuleRegistry([_record(), _record("sale", errcode_segment="12")]).validate() == []


@pytest.mark.kiwi_id(28)
def test_validate_detects_duplicates() -> None:
    """唯一性：module_key / table_prefix / event_domain 与可空列（service_key / 段位）重复均检出。"""
    registry = ModuleRegistry(
        [
            _record("pur"),
            _record("pur", name="采购2"),
            _record("sale", table_prefix="pur_", event_domain="pur"),
            _record("wh", service_key="biz", errcode_segment="11"),
            _record("sup", service_key="biz", errcode_segment="11"),
        ]
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
        [
            _record("Bad", table_prefix="Bad", event_domain="Bad-Domain", errcode_segment="0"),
            _record("pur", service_group="unknown", build_batch=9, service_version="1.0"),
            _record("pay", product_key=None),
            _record("wh", service_key="Bad Key"),
        ]
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


@pytest.mark.kiwi_id(2163)
def test_validate_catalog_roundtrip_and_conflicts() -> None:
    """接库校验：清单自身与主版本兼容通过；缺行 / 清单外 / 字段 / 主版本 / 运行服务逐项检出。"""
    catalog = SERVICE_CATALOG
    assert validate_catalog(catalog, list(catalog)) == []
    assert validate_catalog(catalog, list(catalog), service_key="platform", contract_version="0.1.0") == []

    records = list(catalog)
    records[1] = replace(records[1], contract_version="0.2.0")
    assert validate_catalog(catalog, records) == []

    records[1] = replace(records[1], contract_version="1.0.0")
    assert any("契约版本主版本不兼容" in error for error in validate_catalog(catalog, records))

    records = list(catalog)
    del records[1]
    assert any("库中缺登记行：identity" in error for error in validate_catalog(catalog, records))

    records = list(catalog)
    records.append(
        ModuleRecord(
            module_key="ghost",
            name="幽灵模块",
            table_prefix="ghost_",
            event_domain="ghost",
            service_group=ServiceGroup.CAPABILITY,
        )
    )
    assert any("库中登记行不在清单：ghost" in error for error in validate_catalog(catalog, records))

    records = list(catalog)
    records[1] = replace(records[1], name="改过的名字")
    assert any("name 与清单不一致" in error for error in validate_catalog(catalog, records))


@pytest.mark.kiwi_id(2163)
def test_validate_catalog_running_service_rules() -> None:
    """运行服务项：主版本兼容通过；未登记 / 自报非法 / 登记非法逐项检出。"""
    catalog = SERVICE_CATALOG

    records = list(catalog)
    records[1] = replace(records[1], service_key=None)
    errors = validate_catalog(catalog, records, service_key="identity", contract_version="0.1.0")
    assert any("运行服务未登记：identity" in error for error in errors)

    errors = validate_catalog(catalog, list(catalog), service_key="platform", contract_version="0.1")
    assert any("运行服务契约版本非法" in error for error in errors)

    records = list(catalog)
    records[0] = replace(records[0], contract_version="bad")
    errors = validate_catalog(catalog, records, service_key="platform", contract_version="0.1.0")
    assert any("登记契约版本非法" in error for error in errors)
