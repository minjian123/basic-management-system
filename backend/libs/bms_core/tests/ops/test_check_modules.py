"""CI 服务目录与声明校验脚本测试（Kiwi 28 / 2163 / 2249 / 2365）：离线 + 接库 + 跨仓三档 / 退出码 / 取源退役。"""

import asyncio
import runpy
import sys
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import bms_core.registry.products as products
import ops.check_modules as check_modules
import ops.seed_module as seed_module
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.models.platform.catalog import SysModule
from bms_core.registry.declarations import DeclarationPayload
from bms_core.services.module_registry import PRODUCT_CATALOG, SERVICE_CATALOG, ModuleRecord, ProductRecord

_PLATFORM_MANIFEST = """product_key = "platform"
"""

_DEMO_MANIFEST = """product_key = "demo"

[[products]]
product_key = "demo"
name = "演示产品"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "product"
product_key = "demo"
contract_version = "0.1.0"

[[collaborations]]
name = "demo.org.user-roles"
domain = "org"
kind = "read"
path = "/api/v1/demo/roles"
contract_version = "0.1.0"
product_key = "demo"
frontend_prefix = "demo"

# 第九类：业务域声明（07B `04_02` 重开——域布局由清单声明，不再读 domain_layout.json）
[[domains]]
domain_key = "org"
service_key = "demo"
status = "planned"
"""


def _workspace(root: Path, *, include_capability_path: bool = True) -> tuple[Path, Path]:
    """造一个最小工作区：本仓（平台清单）+ 一个产品仓（声明 / 契约 / 域布局）。

    Args:
        root: 临时工作区根。
        include_capability_path: 产品契约是否包含能力访问面（False 用于构造「访问面不在契约」）。

    Returns:
        tuple[Path, Path]: （后端工程根, 产品克隆容器目录）。
    """
    backend = root / "backend"
    backend.mkdir()
    registry = root / "deploy" / "registry"
    registry.mkdir(parents=True)
    (registry / "platform.toml").write_text(_PLATFORM_MANIFEST, encoding="utf-8")

    product_root = root / "product" / "demo"
    (product_root / "deploy" / "registry").mkdir(parents=True)
    (product_root / "deploy" / "contracts").mkdir(parents=True)
    (product_root / "deploy" / "boundaries").mkdir(parents=True)
    (product_root / "deploy" / "registry" / "demo.toml").write_text(_DEMO_MANIFEST, encoding="utf-8")
    contract_text = '{"paths": {"/api/v1/demo/roles": {}}}' if include_capability_path else '{"paths": {}}'
    (product_root / "deploy" / "contracts" / "demo.json").write_text(contract_text, encoding="utf-8")
    return backend, root / "product"


def _platform_payloads() -> ConcurrentStableList[DeclarationPayload]:
    """取本仓（平台）声明载荷（测试环境用真实 `deploy/registry/platform.toml`）。"""
    return check_modules.payloads_of(check_modules.manifest_paths())


@pytest.mark.kiwi_id(28)
def test_check_modules_passes() -> None:
    """服务目录清单 + 服务包声明：离线校验通过、退出码 0。"""
    assert check_modules.main(ConcurrentStableList(["--offline"])) == 0


@pytest.mark.kiwi_id(2163)
def test_check_modules_cli_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """`__main__` 入口：以模块名运行走 `main`、离线校验通过退出码 0（覆盖入口守卫）。"""
    monkeypatch.setattr(sys, "argv", ["ops.check_modules", "--offline"])
    with (
        pytest.warns(RuntimeWarning, match="found in sys.modules"),
        pytest.raises(SystemExit) as excinfo,
    ):
        runpy.run_module("ops.check_modules", run_name="__main__")
    assert excinfo.value.code == 0


@pytest.mark.kiwi_id(28)
def test_check_modules_default_reads_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """缺省（无 `--url`）读配置解析后接库校验；接库通过退出码 0。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cfg_catalog.db'}"
    asyncio.run(_create_table(url))
    asyncio.run(seed_module.seed_modules(url))

    def _fake_url(_url: str = "", *, service: str = "") -> str:
        """测试替身：固定返回临时库 URL。"""
        return url

    monkeypatch.setattr(check_modules, "resolve_url", _fake_url)
    assert check_modules.main(ConcurrentStableList([])) == 0


@pytest.mark.kiwi_id(28)
def test_check_modules_fails_on_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """冲突清单：打印明细、退出码 1。"""

    class BadRegistry:
        """返回冲突明细的测试替身。"""

        def validate(self) -> ConcurrentStableList[str]:
            """返回固定冲突明细。"""
            return ConcurrentStableList(["table_prefix 重复：pur_"])

    monkeypatch.setattr(check_modules, "ModuleRegistry", BadRegistry)
    assert check_modules.main(ConcurrentStableList([])) == 1


@pytest.mark.kiwi_id(2365)
def test_check_manifests_empty_warns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """本仓无声明且无 `--manifest`：不报错，但给出「无任何清单可校验」提示（不静默）。"""
    monkeypatch.setattr(products, "_MANIFEST_BASE", tmp_path / "backend")

    errors, warnings = check_modules.check_manifests()

    assert errors == []
    assert any("无任何清单可校验" in warning for warning in warnings)


@pytest.mark.kiwi_id(2365)
def test_check_manifests_covers_platform_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """取源＝本仓自动发现（平台 `platform.toml` 进校验）；非法清单逐条报错、CLI 退出码 1。"""
    backend, _ = _workspace(tmp_path)
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)

    errors, warnings = check_modules.check_manifests()

    assert errors == []
    assert warnings == []

    bad = tmp_path / "bad.toml"
    bad.write_text('product_key = "bad"\n\n[[collaborations]]\nname = "bad.org.x"\nkind = "read"\n', encoding="utf-8")
    errors, _ = check_modules.check_manifests([str(bad)])
    assert any("缺少必填字段" in error for error in errors)
    assert check_modules.main(ConcurrentStableList(["--offline", "--manifest", str(bad)])) == 1
    assert "缺少必填字段" in capsys.readouterr().out


def _write_service(root: Path, name: str, body: str) -> None:
    """写入测试服务工程声明文件（`services/<名>/src/bms_<名>/__init__.py`）。

    Args:
        root: 测试服务工程根。
        name: 服务名。
        body: `__init__.py` 内容。
    """
    init_path = root / name / "src" / f"bms_{name}" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    init_path.write_text(body, encoding="utf-8")


def _catalog(
    *, service_key: str | None = "alpha", contract_version: str = "0.1.0"
) -> ConcurrentStableList[ModuleRecord]:
    """构造单行测试清单。

    Args:
        service_key: 服务标识。
        contract_version: 清单契约版本。

    Returns:
        ConcurrentStableList[ModuleRecord]: 清单。
    """
    return ConcurrentStableList(
        [
            ModuleRecord(
                module_key="alpha",
                service_key=service_key,
                name="甲服务",
                table_prefix="alpha_",
                event_domain="alpha",
                contract_version=contract_version,
            ),
        ]
    )


@pytest.mark.kiwi_id(2163)
def test_resolve_service_contracts_and_declarations(tmp_path: Path) -> None:
    """服务工程扫描：提取 CONTRACT_VERSION（缺失 / 非字符串字面量为 None）并与清单双向核对。"""
    _write_service(tmp_path, "alpha", 'CONTRACT_VERSION = "0.1.0"\n')
    _write_service(tmp_path, "beta", '__version__ = "0.1.0"\n')
    _write_service(tmp_path, "gamma", "CONTRACT_VERSION = 1\n")
    (tmp_path / "not_a_service.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "delta" / "src").mkdir(parents=True)
    declarations = check_modules.resolve_service_contracts(tmp_path)
    assert declarations == {"alpha": "0.1.0", "beta": None, "gamma": None}

    catalog = _catalog()
    assert check_modules.check_service_declarations(catalog, ConcurrentStableDict({"alpha": "0.1.0"})) == []
    assert check_modules.check_service_declarations(catalog, ConcurrentStableDict({"alpha": "0.2.0"})) == []
    assert any(
        "主版本不符" in error
        for error in check_modules.check_service_declarations(catalog, ConcurrentStableDict({"alpha": "1.0.0"}))
    )
    assert any(
        "未声明 CONTRACT_VERSION" in error
        for error in check_modules.check_service_declarations(catalog, ConcurrentStableDict({"alpha": None}))
    )
    assert any(
        "非 semver" in error
        for error in check_modules.check_service_declarations(catalog, ConcurrentStableDict({"alpha": "1.0"}))
    )
    assert any(
        "服务工程未登记：beta" in error
        for error in check_modules.check_service_declarations(
            catalog, ConcurrentStableDict({"alpha": "0.1.0", "beta": "0.1.0"})
        )
    )


@pytest.mark.kiwi_id(2163)
def test_resolve_service_contracts_real_workspace() -> None:
    """真实工作区：已建 9 个平台服务工程均自报 CONTRACT_VERSION 且与清单主版本一致。"""
    declarations = check_modules.resolve_service_contracts()
    assert set(declarations) == {
        "ai",
        "file",
        "identity",
        "notification",
        "platform",
        "report",
        "search",
        "tenant",
        "txn",
    }
    assert all(version is not None for version in declarations.values())
    assert check_modules.check_service_declarations(ConcurrentStableList(SERVICE_CATALOG), declarations) == []


async def _create_table(url: str) -> None:
    """仅建 `sys_module` 表（空库场景）。

    Args:
        url: 平台库连接串。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(cast("Table", SysModule.__table__).create, checkfirst=True)
    finally:
        await engine.dispose()


async def _set_contract_version(url: str, module_key: str, version: str) -> None:
    """改写指定行的契约版本（构造库侧冲突）。

    Args:
        url: 平台库连接串。
        module_key: 行登记标识。
        version: 契约版本。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysModule).where(SysModule.module_key == module_key)
            row = (await session.execute(statement)).scalar_one()
            row.contract_version = version
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2163)
def test_check_catalog_db_modes(tmp_path: Path) -> None:
    """接库模式：表缺失 / 空库 / 种子后通过 / 冲突失败；CLI 退出码随结果。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'ci_catalog.db'}"
    warnings = ConcurrentStableList[str]()
    payloads = _platform_payloads()
    assert any("服务目录库不可读" in error for error in check_modules.check_catalog_db(url, payloads, warnings))

    asyncio.run(_create_table(url))
    empty_errors = check_modules.check_catalog_db(url, payloads, ConcurrentStableList())
    assert any("库中无平台自身服务行（注册未执行？）" in error for error in empty_errors)

    asyncio.run(seed_module.seed_modules(url))
    assert check_modules.check_catalog_db(url, payloads, ConcurrentStableList()) == []
    assert check_modules.main(ConcurrentStableList(["--url", url])) == 0

    asyncio.run(_set_contract_version(url, "identity", "1.0.0"))
    errors = check_modules.check_catalog_db(url, payloads, ConcurrentStableList())
    assert any("契约版本主版本不兼容" in error for error in errors)
    assert check_modules.main(ConcurrentStableList(["--url", url])) == 1


@pytest.mark.kiwi_id(2365)
def test_platform_payload_excludes_product_rows() -> None:
    """平台载荷只并 `product_key` 为空的平台自身服务行（与 `declaration_bootstrap` 同口径）。"""
    payload = check_modules.platform_payload()

    assert payload.product_key == "platform"
    assert [record.module_key for record in payload.services if record.product_key] == []
    planned = {record.module_key for record in SERVICE_CATALOG if record.product_key}
    assert planned, "常量里应有计划产品行，否则本用例失去意义"
    assert planned - {record.module_key for record in payload.services} == planned


@pytest.mark.kiwi_id(2249)
def test_check_catalog_db_products_follow_declaration(tmp_path: Path) -> None:
    """产品档案以**声明**为基准：声明齐备即通过；未声明只警示；状态漂移 / 缺行 / 表缺失照常检出。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'ci_products.db'}"
    asyncio.run(seed_module.seed_modules(url))
    declared = DeclarationPayload(
        product_key="platform",
        service_key="platform",
        products=ConcurrentStableFrozenList(PRODUCT_CATALOG),
    )
    warnings = ConcurrentStableList[str]()
    assert check_modules.check_catalog_db(url, ConcurrentStableList((declared,)), warnings) == []
    assert not [warning for warning in warnings if "无任何清单声明" in warning]

    undeclared = DeclarationPayload(product_key="demo", service_key="demo")
    warnings = ConcurrentStableList[str]()
    assert check_modules.check_catalog_db(url, ConcurrentStableList((undeclared,)), warnings) == []
    assert any("常量登记的产品 biz 无任何清单声明" in warning for warning in warnings)
    assert any("本次无任何产品声明" in warning for warning in warnings)

    drifted = DeclarationPayload(
        product_key="platform",
        service_key="platform",
        products=ConcurrentStableFrozenList((ProductRecord(product_key="biz", name="企业运营", status="planned"),)),
    )
    errors = check_modules.check_catalog_db(url, ConcurrentStableList((drifted,)), ConcurrentStableList())
    assert any("产品档案 biz：status 与清单不一致" in error for error in errors)

    asyncio.run(_exec_sql(url, "DELETE FROM sys_product"))
    errors = check_modules.check_catalog_db(url, ConcurrentStableList((declared,)), ConcurrentStableList())
    assert any("产品档案库中缺登记行" in error for error in errors)

    asyncio.run(_exec_sql(url, "DROP TABLE sys_product"))
    errors = check_modules.check_catalog_db(url, ConcurrentStableList((declared,)), ConcurrentStableList())
    assert any("产品档案库不可读" in error for error in errors)


async def _exec_sql(url: str, statement: str) -> None:
    """在平台库执行一条 SQL（构造库侧产品档案异常场景）。

    Args:
        url: 平台库连接串。
        statement: 待执行 SQL。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2365)
def test_cross_repo_requires_product_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """取不到产品仓：缺省失败（退出码 1）；`--allow-missing` 显式跳过并警示（退出码 0）。"""
    backend, _ = _workspace(tmp_path)
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)

    empty = tmp_path / "no-products"
    empty.mkdir()
    errors, warnings, _ = check_modules.run_cross_repo(
        product_roots=[str(empty)], manifests=(), allow_missing=False, keep_tmp=False
    )
    assert any("未取到任何产品仓声明" in error for error in errors)
    assert check_modules.main(ConcurrentStableList(["--cross-repo", "--product-root", str(empty)])) == 1

    errors, warnings, _ = check_modules.run_cross_repo(
        product_roots=[str(empty)], manifests=(), allow_missing=True, keep_tmp=False
    )
    assert errors == []
    assert any("已显式跳过" in warning for warning in warnings)
    missing_ok = ["--cross-repo", "--product-root", str(empty), "--allow-missing"]
    assert check_modules.main(ConcurrentStableList(missing_ok)) == 0
    assert "已显式跳过" in capsys.readouterr().out


@pytest.mark.kiwi_id(2365)
def test_cross_repo_e2e_registers_and_reconciles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """跨仓档端到端：L1（契约定位通过）+ L2（平台 → 产品注册、声明↔注册表 0 差异）→ 退出码 0。"""
    backend, product_base = _workspace(tmp_path)
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)

    errors, warnings, lines = check_modules.run_cross_repo(
        product_roots=[str(product_base)], manifests=(), allow_missing=False, keep_tmp=False
    )

    assert errors == []
    assert any("L1 装载校验：2 份清单" in line for line in lines)
    assert any("L2 注册表：2 个声明方 → 0 差异" in line for line in lines)
    assert any("常量登记的产品 cw 无任何清单声明" in warning for warning in warnings) or warnings == []
    assert check_modules.main(ConcurrentStableList(["--cross-repo", "--product-root", str(product_base)])) == 0


@pytest.mark.kiwi_id(2365)
def test_cross_repo_l1_contract_missing_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """L1：能力访问面不在产品契约 → 失败并定位能力名与路径（L2 不再执行）。"""
    backend, product_base = _workspace(tmp_path, include_capability_path=False)
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)

    errors, _, lines = check_modules.run_cross_repo(
        product_roots=[str(product_base)], manifests=(), allow_missing=False, keep_tmp=False
    )

    assert any("访问面不在对端契约" in error and "demo.org.user-roles" in error for error in errors)
    assert not any("L2 注册表" in line for line in lines)


@pytest.mark.kiwi_id(2365)
def test_cross_repo_conflicting_arguments(tmp_path: Path) -> None:
    """参数冲突：`--ephemeral` 与 `--url` 互斥；跨仓档拒绝 `--url` / `--offline`（退出码 2）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'x.db'}"
    assert check_modules.main(ConcurrentStableList(["--ephemeral", "--url", url])) == 2
    assert check_modules.main(ConcurrentStableList(["--cross-repo", "--url", url])) == 2
    assert check_modules.main(ConcurrentStableList(["--cross-repo", "--offline"])) == 2


@pytest.mark.kiwi_id(2365)
def test_ephemeral_runs_local_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """一次性库档（无产品仓）：本仓平台声明 → 注册 → 对账，退出码 0。"""
    backend, _ = _workspace(tmp_path)
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)

    assert check_modules.main(ConcurrentStableList(["--ephemeral"])) == 0


@pytest.mark.kiwi_id(2365)
def test_product_roots_expand_shapes(tmp_path: Path) -> None:
    """产品仓根三种形态：仓根 / 声明目录 / 克隆容器目录；空目录返回空清单。"""
    _, product_base = _workspace(tmp_path)
    repo = product_base / "demo"
    registry = repo / "deploy" / "registry"
    empty = tmp_path / "empty"
    empty.mkdir()

    for raw in (str(repo), str(registry), str(product_base)):
        roots = check_modules.resolve_product_roots([raw])
        assert [root.name for root in roots] == ["demo"]
        assert [path.name for path in check_modules.product_manifest_paths(roots)] == ["demo.toml"]

    assert check_modules.resolve_product_roots([str(empty)]) == []
    assert check_modules.product_manifest_paths([empty]) == []
