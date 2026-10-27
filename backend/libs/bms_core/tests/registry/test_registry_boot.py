"""注册表启动装配与投影用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

覆盖三块：
- `project_registry()`：整表重建（退役不投影、常量承载的行不重复登记、使用声明按声明方分组）；
- `remote`：上报 / 拉取的成败分支（非 2xx、响应非法、警示透传）；
- `boot.bootstrap_declarations()`：开关关闭跳过、平台跳过、清单缺失 / 未声明本服务拒启、成功路径。
"""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.collaboration.usage import CapabilityUsage, capability_usage_view, reset_capability_usages
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import CatalogError
from bms_core.registry import boot as boot_module
from bms_core.registry.declarations import RegistrySnapshot, content_hash_of, declaration_key, declaration_wire
from bms_core.registry.projection import project_registry
from bms_core.registry.remote import (
    DECLARATIONS_PATH,
    SNAPSHOT_PATH,
    apply_snapshot,
    fetch_declarations,
    report_declarations,
)
from bms_core.servicecall.base import ServiceRequest
from bms_core.services.module_registry import (
    PRODUCT_CATALOG,
    SERVICE_CATALOG,
    CollaborationRecord,
    ErrorCodeRecord,
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    SeedRecord,
    collaboration_catalog_view,
    error_code_view,
    product_catalog_view,
    product_routes_view,
    seed_catalog_view,
    service_catalog_view,
)


def _snapshot(
    *, owners: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] | None = None, **kwargs: object
) -> RegistrySnapshot:
    """按类别构造快照（自动补指纹 / 声明方）。

    Args:
        owners: 额外的声明方映射（覆盖自动推导）。
        **kwargs: `{类别: 记录列表}`。

    Returns:
        RegistrySnapshot: 快照。
    """
    records: ConcurrentStableDict[str, ConcurrentStableList[object]] = ConcurrentStableDict()
    hashes: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    owner_map: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for kind, items in kwargs.items():
        kind_records: ConcurrentStableList[object] = ConcurrentStableList(items)
        records.set(kind, kind_records)
        kind_hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        kind_owners: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for record in kind_records:
            key = declaration_key(kind, record)
            kind_hashes.set(key, content_hash_of(kind, record))
            kind_owners.set(key, str(getattr(record, "product_key", "") or ""))
        hashes.set(kind, kind_hashes)
        owner_map.set(kind, (owners or ConcurrentStableDict()).get(kind) or kind_owners)
    return RegistrySnapshot(records=records, hashes=hashes, owners=owner_map)


class _Client:
    """服务间客户端替身：按预设返回固定响应并记录请求。"""

    def __init__(self, status_code: int = 200, payload: object = None) -> None:
        """初始化。

        Args:
            status_code: 响应状态码。
            payload: 响应体。
        """
        self.status_code = status_code
        self.payload_body = payload if payload is not None else {"code": 0, "data": {}}
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> Any:
        """记录请求并返回预设响应。

        Args:
            request: 服务间请求。

        Returns:
            Any: 响应替身（`status_code` + `payload()`）。
        """
        self.requests.add(request)
        body = self.payload_body
        return SimpleNamespace(status_code=self.status_code, payload=lambda: body)


@pytest.fixture(autouse=True)
def _clean_views() -> Iterator[None]:
    """用例前后清空使用声明视图（其余视图由投影自身复位）。

    Yields:
        None: 用例运行期。
    """
    reset_capability_usages()
    yield
    reset_capability_usages()


def _app(*, service: str = "demo", enabled: bool = True) -> Any:
    """构造最小应用替身（boot 只读 `state`）。

    Args:
        service: 服务键。
        enabled: 启动注册开关。

    Returns:
        Any: 应用替身。
    """
    return SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(
                registry=SimpleNamespace(register_on_startup=enabled),
                app=SimpleNamespace(service=service),
            ),
            service_identity=SimpleNamespace(name=service),
            service_client=_Client(),
        )
    )


def test_project_registry_rebuilds_views_without_constants_and_retired() -> None:
    """整表重建：常量承载的行不重复登记、退役项不投影、非退役项进入视图。"""
    constant_product = PRODUCT_CATALOG[0].product_key
    constant_service = SERVICE_CATALOG[0].module_key
    demo_capability = CollaborationRecord(
        name="demo.org.roles",
        domain="org",
        kind="read",
        contract_version="0.1.0",
        path="/api/v1/demo/roles",
        product_key="demo",
        frontend_prefix="demo",
    )
    retired_capability = CollaborationRecord(
        name="demo.org.old",
        domain="org",
        kind="read",
        contract_version="0.1.0",
        path="/api/v1/demo/old",
        product_key="demo",
        frontend_prefix="demo",
    )
    snapshot = _snapshot(
        products=[
            ProductRecord(product_key=constant_product, name="常量产品"),
            ProductRecord(product_key="demo", name="演示"),
        ],
        services=[
            ModuleRecord(module_key=constant_service, name="常量服务", table_prefix="sys_", event_domain="sys"),
            ModuleRecord(
                module_key="demo",
                name="演示服务",
                table_prefix="demo_",
                event_domain="demo",
                service_key="demo",
                service_group="product",
                product_key="demo",
            ),
        ],
        seeds=[SeedRecord(name="demo-seed", module="m", entry="e", service="demo", db_key="k")],
        product_routes=[ProductRouteRecord(product_key="demo", domain="demo", service_key="demo")],
        collaborations=[demo_capability, retired_capability],
        errcodes=[
            ErrorCodeRecord(
                code=880001,
                domain="demo",
                http_status=200,
                message_key="demo.error.bad",
                severity="warning",
                description="说明",
                product_key="demo",
                segment="88",
            )
        ],
        usages=[CapabilityUsage(name="demo.org.roles")],
        owners=ConcurrentStableDict(
            {"usages": ConcurrentStableDict({"demo.org.roles": "demo"})},
        ),
    )
    snapshot.retired.set("collaborations", ConcurrentStableSet(("demo.org.old",)))

    project_registry(snapshot)

    product_keys = [item.product_key for item in product_catalog_view()]
    assert "demo" in product_keys
    assert product_keys.count(constant_product) == 1, "常量承载的产品不得因投影重复登记"
    assert {"demo"} <= {item.module_key for item in service_catalog_view()}
    assert {item.name for item in seed_catalog_view()} >= {"demo-seed"}
    assert [item.domain for item in product_routes_view()] == ["demo"]
    assert [item.name for item in collaboration_catalog_view()] == ["demo.org.roles"]
    assert 880001 in error_code_view()
    assert [item.name for item in capability_usage_view().get("demo") or ()] == ["demo.org.roles"]


def test_project_registry_skips_usage_without_owner() -> None:
    """使用声明缺声明方：不登记（不猜消费方）。"""
    snapshot = _snapshot(usages=[CapabilityUsage(name="demo.org.roles")])

    project_registry(snapshot)

    assert capability_usage_view() == {}


def test_project_registry_skips_non_usage_items() -> None:
    """`usages` 段里混入非使用声明对象：跳过（防御脏数据）。"""
    snapshot = _snapshot(usages=[ProductRecord(product_key="demo", name="演示")])
    snapshot.owners.set("usages", ConcurrentStableDict({"demo": "demo"}))

    project_registry(snapshot)

    assert capability_usage_view() == {}


async def test_report_declarations_posts_manifest_text() -> None:
    """上报：携带清单文本，回执含逐类计数；警示逐条记日志。"""
    client = _Client(payload={"code": 0, "data": {"product_key": "demo", "warnings": ["单仓告警"]}})

    report = await report_declarations(
        cast("Any", client), product_key="demo", service_key="demo", manifest_text='product_key = "demo"'
    )

    assert report.get("product_key") == "demo"
    request = client.requests[0]
    assert request.method == "PUT"
    assert request.path == DECLARATIONS_PATH
    assert cast("Any", request.json_body).get("manifest_toml") == 'product_key = "demo"'


async def test_report_declarations_rejects_bad_response() -> None:
    """上报：非 2xx / 响应体非法 都拒。"""
    with pytest.raises(CatalogError, match="声明上报失败"):
        await report_declarations(
            cast("Any", _Client(status_code=500, payload={"code": 40003})),
            product_key="demo",
            service_key="demo",
            manifest_text="x",
        )
    with pytest.raises(CatalogError, match="声明上报响应非法"):
        await report_declarations(
            cast("Any", _Client(payload={"code": 0, "data": []})),
            product_key="demo",
            service_key="demo",
            manifest_text="x",
        )


async def test_fetch_declarations_loads_snapshot() -> None:
    """拉取：GET 快照并还原为可投影的注册表视图。"""
    wire = {
        "snapshot_version": "3",
        "declarations": {
            "collaborations": [
                dict(
                    declaration_wire(
                        "collaborations",
                        CollaborationRecord(
                            name="demo.org.roles",
                            domain="org",
                            kind="read",
                            contract_version="0.1.0",
                            path="/api/v1/demo/roles",
                            product_key="demo",
                        ),
                    )
                )
            ]
        },
    }
    client = _Client(payload={"code": 0, "data": wire})

    snapshot = await fetch_declarations(cast("Any", client))

    assert client.requests[0].path == SNAPSHOT_PATH
    assert len(snapshot.of("collaborations")) == 1


async def test_fetch_declarations_rejects_non_2xx() -> None:
    """拉取：非 2xx 即拒（调用方转拒启）。"""
    with pytest.raises(CatalogError, match="注册表快照拉取失败"):
        await fetch_declarations(cast("Any", _Client(status_code=503)))


async def test_fetch_declarations_rejects_non_object_body() -> None:
    """拉取：响应体非对象即拒。"""
    with pytest.raises(CatalogError, match="data 非对象"):
        await fetch_declarations(cast("Any", _Client(payload=[1, 2])))


def test_apply_snapshot_projects() -> None:
    """`apply_snapshot()` 等价于投影一次快照。"""
    snapshot = _snapshot(
        collaborations=[
            CollaborationRecord(
                name="demo.org.roles",
                domain="org",
                kind="read",
                contract_version="0.1.0",
                path="/api/v1/demo/roles",
                product_key="demo",
            )
        ]
    )

    apply_snapshot(snapshot)

    assert [item.name for item in collaboration_catalog_view()] == ["demo.org.roles"]


async def test_bootstrap_skips_when_disabled() -> None:
    """开关关闭：直接返回（单测 / 单仓自检）。"""
    app = _app(enabled=False)

    await boot_module.bootstrap_declarations(app)

    assert cast("Any", app.state.service_client).requests == []


async def test_bootstrap_skips_platform() -> None:
    """平台进程：跳过远端交互（本库即权威）。"""
    app = _app(service="platform")

    await boot_module.bootstrap_declarations(app)

    assert cast("Any", app.state.service_client).requests == []


async def test_bootstrap_requires_local_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    """本仓清单缺失：拒启（不带着空视图启动）。"""
    monkeypatch.setattr(boot_module, "local_manifest_paths", lambda: ConcurrentStableList())

    with pytest.raises(CatalogError, match="本仓清单缺失"):
        await boot_module.bootstrap_declarations(_app())


async def test_bootstrap_requires_service_declared(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """清单存在但未声明本服务：拒启。"""
    manifest = tmp_path / "demo.toml"
    manifest.write_text('product_key = "demo"\n', encoding="utf-8")
    monkeypatch.setattr(boot_module, "local_manifest_paths", lambda: ConcurrentStableList([manifest]))

    with pytest.raises(CatalogError, match="未声明服务 demo"):
        await boot_module.bootstrap_declarations(_app())


async def test_bootstrap_reports_and_projects(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """成功路径：上报本仓清单 → 拉取快照 → 投影。"""
    manifest = tmp_path / "demo.toml"
    manifest.write_text(
        """
product_key = "demo"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "product"
product_key = "demo"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(boot_module, "local_manifest_paths", lambda: ConcurrentStableList([manifest]))
    reported: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    projected: ConcurrentStableList[object] = ConcurrentStableList()

    async def _report(client: object, **kwargs: object) -> ConcurrentStableDict[str, object]:
        """上报替身。

        Args:
            client: 客户端（未使用）。
            **kwargs: 上报参数。

        Returns:
            ConcurrentStableDict[str, object]: 回执。
        """
        del client
        reported.add(dict(kwargs))
        return ConcurrentStableDict({"product_key": "demo"})

    async def _fetch(client: object) -> RegistrySnapshot:
        """拉取替身。

        Args:
            client: 客户端（未使用）。

        Returns:
            RegistrySnapshot: 空快照。
        """
        del client
        return _snapshot()

    monkeypatch.setattr(boot_module, "report_declarations", _report)
    monkeypatch.setattr(boot_module, "fetch_declarations", _fetch)
    monkeypatch.setattr(boot_module, "project_registry", lambda snapshot: projected.add(snapshot))

    await boot_module.bootstrap_declarations(_app())

    assert reported[0].get("product_key") == "demo"
    assert reported[0].get("service_key") == "demo"
    assert len(projected) == 1
