"""产品服务装配测试（Kiwi 2251）：服务目录注入 / 产品维度校验 / 接库对账 / 事件域 / 平台服务不变。

覆盖 `bms_core/application.py` 的应用级清单视图与 `bms_core/services/module_registry.py` 的
注入校验（需求 12-3）：

- 应用工厂经 `service_records()` 注入本产品服务清单 → 应用级视图「平台清单 + 注入记录」；
- 声明 `product_key` 时的产品维度 fail-closed 校验（注入记录非空 / 均为产品分组 / 产品归属一致 /
  含运行服务登记行）；
- 合并清单唯一性冲突拒启、接库对账按合并清单执行、事件契约域按合并清单判定；
- 平台服务（不覆写钩子 / 不声明产品维度）视图与校验口径不变。
"""

from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import bms_core.application as application
from bms_core.application import BaseServiceApplicationFactory, service_lifespan
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import CatalogError
from bms_core.services.module_registry import (
    SERVICE_CATALOG,
    ModuleRecord,
    ModuleRegistry,
    ModuleStatus,
    ServiceGroup,
    known_event_domains,
    validate_product_service_records,
)

_PRODUCT_KEY = "mdm"
"""测试用产品标识（已在 `PRODUCT_CATALOG` 预登记——先注册后建表）。"""

_SERVICE_KEY = "mdm-org"
"""测试用产品服务标识。"""

_PRODUCT_RECORDS: tuple[ModuleRecord, ...] = (
    ModuleRecord(
        module_key="mdorg",
        service_key=_SERVICE_KEY,
        name="mdm 组织主数据服务",
        table_prefix="mdorg_",
        errcode_segment="33",
        event_domain="mdorg",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key=_PRODUCT_KEY,
        status=ModuleStatus.PLANNED,
    ),
)
"""产品服务自报清单（与 `bms_core` 同口径；产品服务在自身仓库维护并经钩子注入）。"""


class _ProductFactory(BaseServiceApplicationFactory):
    """测试用产品服务工厂：声明产品维度并注入本产品服务清单。"""

    key: str = "application_factory"
    service_name: str = _SERVICE_KEY
    service_title: str = "mdm 组织主数据服务（产品服务装配测试）"
    version: str = "0.1.0"
    contract_version: str = "0.1.0"
    product_key: str | None = _PRODUCT_KEY

    def prepare_settings(self, settings: Settings) -> None:
        """测试环境无 Redis：就绪探针回退 null 注册表（空检查项、恒定通过）。

        Args:
            settings: 应用配置（可变）。
        """
        settings.health_check_registry.provider = ""

    def service_records(self) -> tuple[ModuleRecord, ...]:
        """本产品服务清单（注入记录）。

        Returns:
            tuple[ModuleRecord, ...]: 产品服务自报记录。
        """
        return _PRODUCT_RECORDS


class _PlatformishFactory(BaseServiceApplicationFactory):
    """测试用平台侧服务工厂：不声明产品维度、不覆写注入钩子。"""

    key: str = "application_factory"
    service_name: str = "assembly_test"
    service_title: str = "BMS 装配基座测试服务"
    version: str = "0.1.0"
    contract_version: str = "0.1.0"


def _registry(app: FastAPI) -> ModuleRegistry:
    """取应用级服务目录视图。

    Args:
        app: 应用实例。

    Returns:
        ModuleRegistry: 服务目录注册表。
    """
    return cast("ModuleRegistry", app.state.module_registry)


def _empty_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """以桩替换接库快照取数（空目录：仅告警放行，聚焦离线清单口径）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """

    async def _load(app: object) -> ConcurrentStableList[ModuleRecord]:  # pragma: no cover - 桩内联
        del app
        return ConcurrentStableList()

    monkeypatch.setattr("bms_core.application.load_catalog_snapshot", _load)


def _snapshot(monkeypatch: pytest.MonkeyPatch, records: tuple[ModuleRecord, ...]) -> None:
    """以桩替换接库快照取数（模拟经契约取到的库中登记行）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        records: 桩返回的库中登记行。
    """

    async def _load(app: object) -> ConcurrentStableList[ModuleRecord]:  # pragma: no cover - 桩内联
        del app
        return ConcurrentStableList(records)

    monkeypatch.setattr("bms_core.application.load_catalog_snapshot", _load)


@pytest.mark.kiwi_id(2251)
def test_factory_merges_injected_records_into_catalog_view() -> None:
    """注入钩子：产品服务视图 = 平台清单 + 注入记录、产品维度落 `app.state`；平台服务视图不变。"""
    product_app = _ProductFactory().create(None)
    product_records = _registry(product_app).catalog_records()
    assert [record.module_key for record in product_records] == [
        *[record.module_key for record in SERVICE_CATALOG],
        "mdorg",
    ]
    assert product_app.state.service_product_key == _PRODUCT_KEY
    assert product_app.state.service_injected_records == ConcurrentStableList(_PRODUCT_RECORDS)

    platform_app = _PlatformishFactory().create(None)
    assert _registry(platform_app).catalog_records() == ConcurrentStableList(SERVICE_CATALOG)
    assert platform_app.state.service_product_key is None
    assert platform_app.state.service_injected_records == ConcurrentStableList()


@pytest.mark.kiwi_id(2251)
def test_catalog_view_accessors_and_filters_unchanged() -> None:
    """视图入口：清单 / 事件域与合并清单一致；`list_modules()` 筛选语义不变。"""
    merged = ConcurrentStableList([*SERVICE_CATALOG, *_PRODUCT_RECORDS])
    registry = ModuleRegistry(merged)

    assert registry.catalog_records() == merged
    domains = registry.event_domains()
    assert domains == ConcurrentStableSet(record.event_domain for record in merged)
    assert "mdorg" in domains
    assert "mdorg" not in known_event_domains()
    assert [record.module_key for record in registry.list_modules(group=ServiceGroup.PRODUCT)] == [
        "pur",
        "pay",
        "sale",
        "wh",
        "sup",
        "cw",
        "mdorg",
    ]
    assert registry.validate() == []


@pytest.mark.kiwi_id(2251)
async def test_product_service_assembles_and_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """产品服务经共享基座装配并启动：探针 200、探针响应产品服务身份、根路由回显身份。"""
    _empty_snapshot(monkeypatch)
    app = _ProductFactory().create(None)
    async with service_lifespan(app):
        assert app.state.startup_complete is True
        assert app.state.catalog_degraded is False
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/healthz")
            ready = await client.get("/readyz")
            root = await client.get("/")
    assert health.status_code == 200
    assert health.json()["service"] == _SERVICE_KEY
    assert ready.status_code == 200
    assert ready.json()["service"] == _SERVICE_KEY
    assert root.json()["data"] == {"name": "mdm 组织主数据服务（产品服务装配测试）", "version": "0.1.0"}


@pytest.mark.kiwi_id(2251)
def test_product_dimension_validation_rules() -> None:
    """产品维度四项断言逐项检出：空注入 / 非产品分组 / 产品归属不一致 / 未含运行服务登记行。"""
    records = ConcurrentStableList(_PRODUCT_RECORDS)
    assert validate_product_service_records(records, service_key=_SERVICE_KEY, product_key=_PRODUCT_KEY) == []

    empty: ConcurrentStableList[ModuleRecord] = ConcurrentStableList()
    joined = "；".join(validate_product_service_records(empty, service_key=_SERVICE_KEY, product_key=_PRODUCT_KEY))
    assert "产品服务装配未声明服务目录记录" in joined

    non_product = ConcurrentStableList(
        [
            ModuleRecord(
                module_key="mdorgbase",
                service_key=_SERVICE_KEY,
                name="mdm 基座模块",
                table_prefix="mdorgbase_",
                event_domain="mdorgbase",
                service_group=ServiceGroup.FOUNDATION,
            )
        ]
    )
    joined = "；".join(
        validate_product_service_records(non_product, service_key=_SERVICE_KEY, product_key=_PRODUCT_KEY)
    )
    assert "产品服务注入记录须为产品分组（现 foundation）" in joined
    assert "注入记录产品归属与声明不一致（记录 None，声明 mdm）" in joined

    foreign_product = ConcurrentStableList(
        [
            ModuleRecord(
                module_key="cwmodule",
                service_key="cw-svc",
                name="cw 模块",
                table_prefix="cwmodule_",
                event_domain="cwmodule",
                service_group=ServiceGroup.PRODUCT,
                product_key="cw",
            )
        ]
    )
    joined = "；".join(
        validate_product_service_records(foreign_product, service_key=_SERVICE_KEY, product_key=_PRODUCT_KEY)
    )
    assert "注入记录产品归属与声明不一致（记录 cw，声明 mdm）" in joined
    assert "运行服务未在注入清单登记：mdm-org" in joined


@pytest.mark.kiwi_id(2251)
async def test_product_dimension_rejected_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """产品服务未声明服务目录记录：离线阶段拒启（CatalogError 40003 + 明细）。"""
    _empty_snapshot(monkeypatch)

    class _EmptyRecordsFactory(_ProductFactory):
        """声明产品维度但不注入任何记录（配置级错误）。"""

        def service_records(self) -> tuple[ModuleRecord, ...]:
            """空注入记录。

            Returns:
                tuple[ModuleRecord, ...]: 空元组。
            """
            return ()

    app = _EmptyRecordsFactory().create(None)
    with pytest.raises(CatalogError, match="产品服务装配未声明服务目录记录") as excinfo:
        async with service_lifespan(app):
            pass
    assert excinfo.value.code == ErrorCode.CATALOG


@pytest.mark.kiwi_id(2251)
async def test_merged_catalog_conflict_rejected_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入记录与平台记录冲突（module_key / table_prefix / event_domain / service_key 重复）即拒启。"""
    _empty_snapshot(monkeypatch)

    class _ConflictFactory(_ProductFactory):
        """注入与平台服务目录冲突的记录（`org` 行重复）。"""

        def service_records(self) -> tuple[ModuleRecord, ...]:
            """冲突注入记录（module_key / table_prefix / event_domain / service_key 与平台 `org` 行重复）。

            Returns:
                tuple[ModuleRecord, ...]: 冲突记录。
            """
            return (
                ModuleRecord(
                    module_key="org",
                    service_key="org",
                    name="组织主数据服务（冲突样例）",
                    table_prefix="org_",
                    event_domain="org",
                    service_group=ServiceGroup.PRODUCT,
                    product_key=_PRODUCT_KEY,
                ),
            )

    app = _ConflictFactory().create(None)
    with pytest.raises(CatalogError, match="module_key 重复：org") as excinfo:
        async with service_lifespan(app):
            pass
    assert excinfo.value.code == ErrorCode.CATALOG


@pytest.mark.kiwi_id(2251)
async def test_catalog_reconciliation_uses_merged_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """接库对账走合并清单：库中「平台 + 产品」行通过；产品行缺失 / 字段不符即拒启（先注册后建表守门）。"""
    merged = (*SERVICE_CATALOG, *_PRODUCT_RECORDS)
    _snapshot(monkeypatch, merged)
    app = _ProductFactory().create(None)
    async with service_lifespan(app):
        assert app.state.startup_complete is True

    _snapshot(monkeypatch, SERVICE_CATALOG)
    with pytest.raises(CatalogError, match="库中缺登记行：mdorg") as missing:
        async with service_lifespan(_ProductFactory().create(None)):
            pass
    assert missing.value.code == ErrorCode.CATALOG

    drifted = tuple(
        ModuleRecord(
            module_key="mdorg",
            service_key=_SERVICE_KEY,
            name="改过的名字",
            table_prefix="mdorg_",
            errcode_segment="33",
            event_domain="mdorg",
            service_group=ServiceGroup.PRODUCT,
            build_batch=3,
            product_key=_PRODUCT_KEY,
            status=ModuleStatus.PLANNED,
        )
        if record.module_key == "mdorg"
        else record
        for record in merged
    )
    _snapshot(monkeypatch, drifted)
    with pytest.raises(CatalogError, match="name 与清单不一致") as mismatch:
        async with service_lifespan(_ProductFactory().create(None)):
            pass
    assert mismatch.value.code == ErrorCode.CATALOG


@pytest.mark.kiwi_id(2251)
def test_event_contract_domains_follow_merged_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件契约域取应用级视图：产品服务自有事件域进入校验域集合（平台视图不含）。"""
    captured: ConcurrentStableSet[str] = ConcurrentStableSet()

    def _fake_validate(registry: object, *, domains: ConcurrentStableSet[str]) -> tuple[str, ...]:
        del registry
        captured.update(domains)
        return ()

    monkeypatch.setattr(application, "validate_event_registry", _fake_validate)
    application._validate_event_contracts(_ProductFactory().create(None))  # pyright: ignore[reportPrivateUsage]
    assert "mdorg" in captured
    assert "mdorg" not in known_event_domains()
