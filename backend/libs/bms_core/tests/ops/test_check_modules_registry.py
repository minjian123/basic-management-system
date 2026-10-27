"""注册表 ↔ 本仓声明对账用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

覆盖 `ops.check_modules.diff_platform_declarations()` 的四个分支：
一致 / 缺声明 / 指纹漂移 / 库多出声明；另验「别的产品行不参与」「退役行不算缺失」。
"""

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.registry.declarations import (
    DeclarationPayload,
    RegistrySnapshot,
    content_hash_of,
    declaration_key,
)
from bms_core.services.module_registry import CollaborationRecord
from ops.check_modules import diff_platform_declarations


def _capability(path: str = "/api/v1/platform/internal/users/query") -> CollaborationRecord:
    """构造平台能力记录。

    Args:
        path: 访问面路径。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name="platform.user.query",
        domain="user",
        kind="read",
        contract_version="0.3.0",
        path=path,
        product_key="platform",
        frontend_prefix="platform",
    )


def _payload(*records: CollaborationRecord) -> DeclarationPayload:
    """构造平台声明载荷。

    Args:
        *records: 能力记录。

    Returns:
        DeclarationPayload: 载荷。
    """
    return DeclarationPayload(
        product_key="platform",
        service_key="platform",
        collaborations=ConcurrentStableFrozenList(records),
    )


def _snapshot(
    records: ConcurrentStableList[CollaborationRecord],
    *,
    owners: ConcurrentStableDict[str, str] | None = None,
    retired: ConcurrentStableSet[str] | None = None,
) -> RegistrySnapshot:
    """构造注册表快照（只含能力类）。

    Args:
        records: 能力记录（库中行）。
        owners: 业务键 → 声明方（缺省 `platform`）。
        retired: 已退役业务键。

    Returns:
        RegistrySnapshot: 快照。
    """
    hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    owner_map: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for record in records:
        key = declaration_key("collaborations", record)
        hashes.set(key, content_hash_of("collaborations", record))
        owner_map.set(key, (owners or ConcurrentStableDict()).get(key, "platform"))
    return RegistrySnapshot(
        records=ConcurrentStableDict({"collaborations": ConcurrentStableList(records)}),
        hashes=ConcurrentStableDict({"collaborations": hashes}),
        owners=ConcurrentStableDict({"collaborations": owner_map}),
        retired=ConcurrentStableDict({"collaborations": retired or ConcurrentStableSet()}),
    )


def test_diff_reports_no_error_when_identical() -> None:
    """声明与注册表一致：无差异。"""
    record = _capability()

    errors = diff_platform_declarations(_snapshot(ConcurrentStableList([record])), _payload(record))

    assert list(errors) == []


def test_diff_reports_missing_declaration() -> None:
    """本仓有、注册表无：报缺声明。"""
    errors = diff_platform_declarations(_snapshot(ConcurrentStableList()), _payload(_capability()))

    assert any("注册表缺该声明" in item for item in errors)


def test_diff_reports_content_drift() -> None:
    """内容指纹不同：报声明与注册表不一致。"""
    errors = diff_platform_declarations(
        _snapshot(ConcurrentStableList([_capability("/api/v1/platform/internal/users/query-v2")])),
        _payload(_capability()),
    )

    assert any("声明与注册表不一致" in item for item in errors)


def test_diff_reports_extra_declaration() -> None:
    """注册表有、本仓无：报多出声明。"""
    errors = diff_platform_declarations(_snapshot(ConcurrentStableList([_capability()])), _payload())

    assert any("注册表多出声明" in item for item in errors)


def testplatform_payload_reads_local_manifest_and_services() -> None:
    """本仓平台载荷：读 `deploy/registry/platform.toml` 并并入 `SERVICE_CATALOG` 服务行。"""
    from ops.check_modules import platform_payload

    payload = platform_payload()

    assert payload.product_key == "platform"
    assert {"sys", "identity"} <= {record.module_key for record in payload.services}


def test_check_registry_db_skips_without_tables(tmp_path: object) -> None:
    """注册表未建表：跳过对账并输出提示（不把「没迁移」当「声明漂移」）。"""
    from pathlib import Path as _Path

    from ops.check_modules import check_registry_db

    url = f"sqlite+aiosqlite:///{_Path(str(tmp_path)) / 'empty.db'}"

    assert list(check_registry_db(url)) == []


def test_check_registry_db_reports_unreadable_db(tmp_path: object) -> None:
    """库不可读（非「未建表」）：报错而不是静默跳过。"""
    from ops.check_modules import check_registry_db

    errors = check_registry_db(f"sqlite+aiosqlite:///{tmp_path}/missing-dir/x.db")

    assert any("注册表库不可读" in item for item in errors)


def test_check_registry_db_reports_unreadable_db_with_manifest(tmp_path: object, monkeypatch: object) -> None:
    """本仓清单可读但库打不开（非「未建表」）：仍报「库不可读」。"""
    from bms_core.registry.declarations import DeclarationPayload
    from ops import check_modules

    monkeypatch.setattr(  # type: ignore[attr-defined]
        check_modules, "platform_payload", lambda: DeclarationPayload(product_key="platform", service_key="platform")
    )

    errors = check_modules.check_registry_db(f"sqlite+aiosqlite:///{tmp_path}/missing-dir/y.db")

    assert any("注册表库不可读" in item for item in errors)


def testplatform_payload_requires_manifest(monkeypatch: object) -> None:
    """本仓平台清单缺失：抛 `CatalogError`（由调用方转成明细）。"""
    import pytest as _pytest

    from bms_core.core.exceptions import CatalogError
    from ops import check_modules

    monkeypatch.setattr(check_modules, "local_manifest_paths", lambda: ConcurrentStableList())  # type: ignore[attr-defined]

    with _pytest.raises(CatalogError, match="本仓平台清单缺失"):
        check_modules.platform_payload()


def test_check_registry_db_reports_missing_manifest(monkeypatch: object) -> None:
    """本仓平台清单缺失：先于接库判定为「本仓声明不可读」。"""
    from ops import check_modules

    monkeypatch.setattr(check_modules, "local_manifest_paths", lambda: ConcurrentStableList())  # type: ignore[attr-defined]

    errors = check_modules.check_registry_db("sqlite+aiosqlite:///:memory:")

    assert any("本仓声明不可读" in item for item in errors)


def testplatform_payload_merges_manifest_services(monkeypatch: object) -> None:
    """平台载荷：清单里未在 `SERVICE_CATALOG` 的服务行被并入（去重后追加）；非平台清单行被跳过。"""
    from pathlib import Path

    from bms_core.registry.declarations import DeclarationPayload
    from bms_core.services.module_registry import ModuleRecord
    from ops import check_modules

    other_manifest = Path("other.toml")
    platform_manifest = Path("platform.toml")
    extra = ModuleRecord(
        module_key="extra",
        name="扩展服务",
        table_prefix="extra_",
        event_domain="extra",
        service_key="extra",
        service_group="product",
        product_key="platform",
    )
    duplicated = ModuleRecord(
        module_key="sys",
        name="平台地基服务",
        table_prefix="sys_",
        event_domain="sys",
        service_key="platform",
    )
    fake_payload = DeclarationPayload(
        product_key="platform",
        service_key="platform",
        services=ConcurrentStableFrozenList((extra, duplicated)),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        check_modules, "local_manifest_paths", lambda: ConcurrentStableList([other_manifest, platform_manifest])
    )
    monkeypatch.setattr(check_modules, "load_product_manifest", lambda path: path)  # type: ignore[attr-defined]
    monkeypatch.setattr(check_modules, "from_manifest", lambda manifest: fake_payload)  # type: ignore[attr-defined]

    payload = check_modules.platform_payload()

    module_keys = {record.module_key for record in payload.services}
    assert {"sys", "extra"} <= module_keys


def test_check_registry_db_diffs_when_tables_exist(tmp_path: object) -> None:
    """注册表已建表：走对账路径（本测试库为空 → 报缺声明）。"""
    import asyncio
    from pathlib import Path

    from sqlalchemy.ext.asyncio import create_async_engine

    from bms_core.models.base import BaseModel
    from ops.check_modules import check_registry_db

    url = f"sqlite+aiosqlite:///{Path(str(tmp_path)) / 'registry.db'}"

    async def _create() -> None:
        """建全部注册表（含服务行 / 产品档案）。"""
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())

    errors = check_registry_db(url)

    assert any("注册表缺该声明" in item for item in errors)


def test_diff_ignores_other_products_and_retired() -> None:
    """别的产品行不参与；已退役行不算缺失也不算多出。"""
    other = CollaborationRecord(
        name="demo.org.roles",
        domain="org",
        kind="read",
        contract_version="0.1.0",
        path="/api/v1/demo/roles",
        product_key="demo",
    )
    retired = _capability("/api/v1/platform/internal/old")
    snapshot = _snapshot(
        ConcurrentStableList([other, retired]),
        owners=ConcurrentStableDict(
            {"demo.org.roles": "demo", "platform.user.query": "platform"},
        ),
        retired=ConcurrentStableSet(("platform.user.query",)),
    )

    errors = diff_platform_declarations(snapshot, _payload())

    assert list(errors) == []
