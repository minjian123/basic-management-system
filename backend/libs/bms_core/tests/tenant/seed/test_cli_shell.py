"""`ops` 五个 CLI 薄壳行为用例（Kiwi 2344）：命令 / 参数 / 退出码 / 关键输出不回退。

覆盖 `ops.{tenant_provisioning,seed_platform,seed_rbac,seed_sso,seed_user}`：薄壳只做入口转发，
实现与参数解析归 `bms_core.tenant.*`；同时断言薄壳不导入服务包（`14_03` 闭包断言的前置事实）。
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList

_REPO_ROOT = Path(__file__).resolve().parents[6]
"""仓库根（`backend/libs/bms_core/tests/tenant/seed/` 上溯 6 级）。"""

_SHELLS = (
    "ops.tenant_provisioning",
    "ops.seed_platform",
    "ops.seed_rbac",
    "ops.seed_sso",
    "ops.seed_user",
)


def _run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    """以子进程运行 `python -m <module>`（真实入口，非直接调用 main）。

    Args:
        module: 模块名（`ops.*`）。
        *args: 命令行参数。

    Returns:
        subprocess.CompletedProcess[str]: 执行结果。
    """
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=_REPO_ROOT / "backend",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.kiwi_id(2344)
def test_tenant_provisioning_shell_dry_run() -> None:
    """`python -m ops.tenant_provisioning --code demo --dry-run`：退出码 0 且打印待建库清单。"""
    result = _run_module("ops.tenant_provisioning", "--code", "demo", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "[tenant_provisioning] 租户 demo：待建库" in result.stdout
    assert "dry-run：不建连、不建库" in result.stdout


@pytest.mark.kiwi_id(2344)
def test_seed_platform_shell_dry_run() -> None:
    """`python -m ops.seed_platform --dry-run`：退出码 0 且打印角色与业务码。"""
    result = _run_module("ops.seed_platform", "--code", "platform", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "platform_admin" in result.stdout
    assert "平台业务码" in result.stdout


@pytest.mark.kiwi_id(2344)
def test_seed_rbac_shell_dry_run(tmp_path: Path) -> None:
    """`python -m ops.seed_rbac --dry-run`：退出码 0 且打印两库目标（预演不落库）。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    _prepare_rbac_dbs(tenant_url, platform_url)
    result = _run_module(
        "ops.seed_rbac",
        "--tenant",
        "demo",
        "--tenant-url",
        tenant_url,
        "--platform-url",
        platform_url,
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "[seed_rbac] 租户库（角色域）：" in result.stdout
    assert "[seed_rbac] 预演完成" in result.stdout


def _prepare_rbac_dbs(tenant_url: str, platform_url: str) -> None:
    """预建两库最小表集（dry-run 仍会读权限码，故平台库表须存在）。

    Args:
        tenant_url: 租户库连接串。
        platform_url: 平台库连接串。
    """
    import asyncio
    from typing import cast

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import create_async_engine

    from bms_core.models.base import Base
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

    async def _create() -> None:
        tenant_engine = create_async_engine(tenant_url)
        async with tenant_engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tenant_tables))
        await tenant_engine.dispose()
        platform_engine = create_async_engine(platform_url)
        async with platform_engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=platform_tables))
        await platform_engine.dispose()

    asyncio.run(_create())


@pytest.mark.kiwi_id(2344)
def test_seed_sso_shell_rejects_partial_mapping() -> None:
    """`python -m ops.seed_sso --map-user-id 5`（缺 external-id）：退出码 2 并提示。"""
    result = _run_module("ops.seed_sso", "--map-user-id", "5")
    assert result.returncode == 2
    assert "--map-user-id 需与 --map-external-id 同时提供" in result.stdout


@pytest.mark.kiwi_id(2344)
def test_seed_user_shell_rejects_short_password(tmp_path: Path) -> None:
    """`python -m ops.seed_user --password short`：退出码 2（口令过短）。"""
    result = _run_module(
        "ops.seed_user",
        "--url",
        f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}",
        "--password",
        "short",
    )
    assert result.returncode == 2
    assert "口令过短" in result.stdout


@pytest.mark.kiwi_id(2344)
def test_shells_are_thin_and_do_not_import_service_packages() -> None:
    """五个薄壳只导入基座（不导入 `ops` 兄弟实现、不导入任何服务包），且不含业务实现。"""
    ops_dir = _REPO_ROOT / "backend" / "ops"
    for module in _SHELLS:
        path = ops_dir / f"{module.split('.')[1]}.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: ConcurrentStableList[str] = ConcurrentStableList()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        tops = {name.split(".")[0] for name in imported}
        assert "bms_core" in tops, f"{path.name} 未从基座导入"
        assert not [name for name in tops if name.startswith("bms_") and name != "bms_core"], (
            f"{path.name} 导入了服务包：{sorted(tops)}"
        )
        assert "ops" not in tops - {"ops"}, f"{path.name} 导入了 ops 兄弟实现"
        # 薄壳不定义业务函数（只允许 `if __name__` 入口与 import）
        defined = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        assert defined == [], f"{path.name} 仍定义业务函数：{defined}"


@pytest.mark.kiwi_id(2344)
def test_release_py_does_not_invoke_sunk_scripts() -> None:
    """部署脚本 `release.py` 的 bootstrap 不含本次下沉的 5 个脚本（部署命令零改动口径）。"""
    release = (_REPO_ROOT / "scripts" / "tools" / "deploy" / "release.py").read_text(encoding="utf-8")
    for sunk in ("ops.seed_platform", "ops.seed_rbac", "ops.seed_sso", "ops.seed_user"):
        assert sunk not in release, f"release.py 仍调用已下沉脚本 {sunk}"
    assert "ops.tenant_provisioning" not in release
