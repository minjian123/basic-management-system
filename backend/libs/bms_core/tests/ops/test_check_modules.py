"""CI 服务目录校验脚本测试（Kiwi 28 / 2163）：离线清单 + 服务包声明 + 接库查重与对账 / 退出码。"""

import asyncio
import runpy
import sys
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.check_modules as check_modules
import ops.seed_module as seed_module
from bms_core.models.platform import SysModule
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord


@pytest.mark.kiwi_id(28)
def test_check_modules_passes() -> None:
    """服务目录清单 + 服务包声明：校验通过、退出码 0。"""
    assert check_modules.main([]) == 0


@pytest.mark.kiwi_id(2163)
def test_check_modules_cli_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """`__main__` 入口：以模块名运行走 `main`、离线校验通过退出码 0（覆盖入口守卫）。"""
    monkeypatch.setattr(sys, "argv", ["ops.check_modules"])
    with (
        pytest.warns(RuntimeWarning, match="found in sys.modules"),
        pytest.raises(SystemExit) as excinfo,
    ):
        runpy.run_module("ops.check_modules", run_name="__main__")
    assert excinfo.value.code == 0


@pytest.mark.kiwi_id(28)
def test_check_modules_fails_on_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """冲突清单：打印明细、退出码 1。"""

    class BadRegistry:
        """返回冲突明细的测试替身。"""

        def validate(self) -> list[str]:
            """返回固定冲突明细。"""
            return ["table_prefix 重复：pur_"]

    monkeypatch.setattr(check_modules, "ModuleRegistry", BadRegistry)
    assert check_modules.main([]) == 1


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


def _catalog(*, service_key: str | None = "alpha", contract_version: str = "0.1.0") -> tuple[ModuleRecord, ...]:
    """构造单行测试清单。

    Args:
        service_key: 服务标识。
        contract_version: 清单契约版本。

    Returns:
        tuple[ModuleRecord, ...]: 清单。
    """
    return (
        ModuleRecord(
            module_key="alpha",
            service_key=service_key,
            name="甲服务",
            table_prefix="alpha_",
            event_domain="alpha",
            contract_version=contract_version,
        ),
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
    assert check_modules.check_service_declarations(catalog, {"alpha": "0.1.0"}) == []
    assert check_modules.check_service_declarations(catalog, {"alpha": "0.2.0"}) == []
    assert any("主版本不符" in error for error in check_modules.check_service_declarations(catalog, {"alpha": "1.0.0"}))
    assert any(
        "未声明 CONTRACT_VERSION" in error
        for error in check_modules.check_service_declarations(catalog, {"alpha": None})
    )
    assert any("非 semver" in error for error in check_modules.check_service_declarations(catalog, {"alpha": "1.0"}))
    assert any(
        "服务工程未登记：beta" in error
        for error in check_modules.check_service_declarations(catalog, {"alpha": "0.1.0", "beta": "0.1.0"})
    )


@pytest.mark.kiwi_id(2163)
def test_resolve_service_contracts_real_workspace() -> None:
    """真实工作区：已建 9 个服务工程均自报 CONTRACT_VERSION 且与清单主版本一致。"""
    declarations = check_modules.resolve_service_contracts()
    assert set(declarations) == {
        "ai",
        "file",
        "identity",
        "notification",
        "org",
        "platform",
        "report",
        "search",
        "tenant",
    }
    assert all(version is not None for version in declarations.values())
    assert check_modules.check_service_declarations(SERVICE_CATALOG, declarations) == []


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
    assert any("服务目录库不可读" in error for error in check_modules.check_catalog_db(url))

    asyncio.run(_create_table(url))
    assert check_modules.check_catalog_db(url) == ["库中无登记行（种子未执行？）"]

    asyncio.run(seed_module.seed_modules(url))
    assert check_modules.check_catalog_db(url) == []
    assert check_modules.main(["--url", url]) == 0

    asyncio.run(_set_contract_version(url, "identity", "1.0.0"))
    errors = check_modules.check_catalog_db(url)
    assert any("契约版本主版本不兼容" in error for error in errors)
    assert check_modules.main(["--url", url]) == 1
