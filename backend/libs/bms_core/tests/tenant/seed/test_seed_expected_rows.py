"""种子 `expected_rows()` 契约与 CLI 分支用例（07B `02_03`；详设 §3.5 / §3.9）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：9 个平台种子 + mdm 种子的 `expected_rows()` 纯函数口径（不连库、字段齐全、键正确）；
各单步命令的 `--dry-run` 与 `main` 输出分支（覆盖率补齐）。
"""

from pathlib import Path
from typing import Any, Protocol

import pytest
from sqlalchemy import Table

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.tenant.seed import config as config_seed
from bms_core.tenant.seed import menu as menu_seed
from bms_core.tenant.seed import module as module_seed
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import rbac as rbac_seed
from bms_core.tenant.seed import tables as tables_seed
from bms_core.tenant.seed import tenant as tenant_seed
from bms_core.tenant.seed.contract import ExpectedRow

_MODULES = (
    module_seed,
    tables_seed,
    menu_seed,
    tenant_seed,
    config_seed,
    platform_seed,
    rbac_seed,
)


# ---- expected_rows 契约（9 个平台种子）----


class _HasExpectedRows(Protocol):
    """具备 `expected_rows()` 的种子实现模块（结构化契约）。"""

    def expected_rows(self) -> ConcurrentStableList[ExpectedRow]:
        """返回期望行清单。

        Returns:
            ConcurrentStableList[ExpectedRow]: 期望行。
        """
        ...


@pytest.mark.parametrize("module", _MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_expected_rows_returns_contract_records(module: _HasExpectedRows) -> None:
    """每个种子模块的 `expected_rows()` 返回 `ExpectedRow` 清单，且字段形态合法。"""
    rows = module.expected_rows()
    assert rows
    assert all(isinstance(row, ExpectedRow) for row in rows)
    for row in rows:
        assert row.table.startswith("sys_")
        assert row.key


@pytest.mark.parametrize("module", _MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_expected_rows_is_pure_function(module: _HasExpectedRows) -> None:
    """纯函数：连续两次调用结果一致（不连库、不写库、无副作用）。"""
    first = module.expected_rows()
    second = module.expected_rows()
    assert list(first) == list(second)


def test_module_expected_rows_covers_catalog_and_products() -> None:
    """`seed-module`：服务目录 + 产品档案两类期望行。"""
    tables = {row.table for row in module_seed.expected_rows()}
    assert tables == {"sys_module", "sys_product"}


def test_tables_expected_rows_covers_ownership() -> None:
    """`seed-tables`：表归属登记（每张表一条）。"""
    rows = tables_seed.expected_rows()
    assert {row.table for row in rows} == {"sys_table_ownership"}
    assert len(rows) == len(tables_seed.table_ownership_view())


def test_menu_expected_rows_covers_business_action_menu() -> None:
    """`seed-menu`：业务码 / 动作码 / 菜单三类（组合键依赖自增 id 的品类不列入）。"""
    rows = menu_seed.expected_rows()
    tables = {row.table for row in rows}
    assert tables == {"sys_business", "sys_action", "sys_menu"}
    business_codes = {row.key["code"] for row in rows if row.table == "sys_business"}
    assert "sys" in business_codes


def test_tenant_expected_rows_covers_seed_tenants() -> None:
    """`seed-tenant`：种子租户（按 `code` 自然键）。"""
    rows = tenant_seed.expected_rows()
    assert [row.key["code"] for row in rows] == [seed.code for seed in tenant_seed.TENANT_SEEDS]


def test_config_expected_rows_covers_defaults() -> None:
    """`seed-config`：每个默认参数一条（比对值为参数值）。"""
    rows = config_seed.expected_rows()
    assert len(rows) == len(config_seed.PLATFORM_CONFIG_DEFAULTS)
    assert {row.table for row in rows} == {"sys_config"}
    assert all("value" in row.values for row in rows)


def test_platform_expected_rows_covers_two_roles() -> None:
    """`seed-platform-role`：两个平台角色。"""
    rows = platform_seed.expected_rows()
    codes = {row.key["code"] for row in rows}
    assert codes == {platform_seed.PLATFORM_ADMIN_ROLE_CODE, platform_seed.PLATFORM_OPS_ROLE_CODE}


def test_rbac_expected_rows_covers_three_roles() -> None:
    """`seed-rbac-role`：三类内置管理员角色。"""
    rows = rbac_seed.expected_rows()
    codes = {row.key["code"] for row in rows}
    assert codes == {rbac_seed.ROLE_SYSTEM_ADMIN, rbac_seed.ROLE_SECURITY_ADMIN, rbac_seed.ROLE_AUDIT_ADMIN}


async def _prepare_rbac_tables(tenant_url: str, platform_url: str) -> None:
    """建 rbac 预演所需最小表集（租户库角色域 + 平台库权限码表）。

    Args:
        tenant_url: 租户库连接串。
        platform_url: 平台库连接串。
    """
    from typing import cast

    from sqlalchemy.ext.asyncio import create_async_engine

    from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
    from bms_core.models.platform.role import SysRole, SysRolePermission, SysUserRole
    from bms_core.models.platform.user import SysUser

    tenant_tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysUser.__table__),
    ]
    platform_tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
    ]
    for url, tables in ((tenant_url, tenant_tables), (platform_url, platform_tables)):
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await _create_tables(connection, ConcurrentStableList(tables))
        finally:
            await engine.dispose()


async def _create_tables(connection: Any, tables: ConcurrentStableList[Table]) -> None:
    """在当前连接上建表（拆出函数避免闭包捕获循环变量）。

    Args:
        connection: 异步连接。
        tables: 表清单。
    """
    from bms_core.models.base import Base

    def _create(conn: Any) -> None:
        """同步建表（`run_sync` 要求同步回调）。

        Args:
            conn: 同步连接。
        """
        Base.metadata.create_all(conn, tables=list(tables))

    await connection.run_sync(_create)


# ---- 单步命令 dry-run / main 分支（覆盖率补齐）----


def test_seed_module_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_module --dry-run`：打印目标库与种子清单，不建连。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    assert module_seed.main(ConcurrentStableList(["--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "[seed_module] 目标库：" in out
    assert "（dry-run）" in out


def test_seed_tables_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_tables --dry-run`：打印目标库与归属清单。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    assert tables_seed.main(ConcurrentStableList(["--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "[seed_tables] 目标库：" in out
    assert "（dry-run）" in out


def test_seed_tenant_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_tenant --dry-run`：打印目标库与种子租户。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    assert tenant_seed.main(ConcurrentStableList(["--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "[seed_tenant] 目标库：" in out
    assert "种子租户" in out


def test_seed_config_dry_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_config --dry-run`：打印目标库，不建连。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///p.db")
    assert config_seed.main(ConcurrentStableList(["--dry-run"])) == 0
    assert "[seed_config] 目标库：" in capsys.readouterr().out


def test_seed_menu_dry_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_menu --dry-run`：打印目标库与种子计数。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///p.db")
    assert menu_seed.main(ConcurrentStableList(["--dry-run"])) == 0
    assert "[seed_menu] 目标库：" in capsys.readouterr().out


async def test_seed_rbac_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_rbac --dry-run`：打印两库目标与预演完成（`main` 是协程，须 await）。

    dry-run 仍会读权限码，故平台库表须先就绪（与 `test_cli_shell` 同口径）。
    """
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _prepare_rbac_tables(tenant_url, platform_url)
    await rbac_seed.main(
        rbac_seed.build_parser().parse_args(
            [
                "--tenant",
                "demo",
                "--tenant-url",
                tenant_url,
                "--platform-url",
                platform_url,
                "--dry-run",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "[seed_rbac] 租户库（角色域）：" in out
    assert "[seed_rbac] 预演完成" in out


def test_seed_platform_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_platform --dry-run`：打印角色与业务码清单（不建连）。"""
    assert platform_seed.main(ConcurrentStableList(["--code", "platform", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert platform_seed.PLATFORM_ADMIN_ROLE_CODE in out
    assert "平台业务码" in out
