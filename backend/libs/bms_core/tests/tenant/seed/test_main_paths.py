"""下沉模块 main() 成功路径与内部分支补测（Kiwi 2343）。

补齐 `bms_core.tenant.{provisioning,seed.platform,seed.rbac,seed.sso,seed.user}` 的
CLI 成功分支与辅助函数分支（行 + 分支 100% 门禁）。
"""

import asyncio
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.models.base import Base
from bms_core.models.platform.menu_form import SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import SysRole, SysRolePermission, SysUserRole
from bms_core.models.platform.user import SysUser
from bms_core.tenant import provisioning
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import rbac as rbac_seed
from bms_core.tenant.seed import sso as sso_seed
from bms_core.tenant.seed import user as user_seed

_BUSINESSES = ("sys", "tenant", "menu", "business", "action", "permission", "user-extension")
_ACTIONS = ("query", "manage", "create", "update", "delete", "generate")


def _templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把平台 / 租户连接串模板指向临时目录。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()


async def _seed_platform_tables(tmp_path: Path) -> None:
    """建 platform 服务平台库 + 平台业务 / 动作 / 权限码 / 菜单 / 表单数据。

    Args:
        tmp_path: 临时目录。
    """
    url = f"sqlite+aiosqlite:///{tmp_path}/bms_platform.db"
    engine = create_async_engine(url)
    tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
        cast("Table", SysMenu.__table__),
        cast("Table", SysForm.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        business_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for code in _BUSINESSES:
            row = SysBusiness(code=code, name=code)
            session.add(row)
            await session.flush()
            business_ids.set(code, int(row.id))
        action_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for code in _ACTIONS:
            row = SysAction(code=code, name=code)
            session.add(row)
            await session.flush()
            action_ids.set(code, int(row.id))
        for business in _BUSINESSES:
            for action in _ACTIONS:
                session.add(SysPermission(business_id=business_ids[business], action_id=action_ids[action]))
        session.add(SysMenu(path="/platform", name="平台"))
        session.add(SysMenu(path="/platform/tenants", name="租户管理"))
        await session.flush()
        session.add(SysForm(business_id=business_ids["tenant"], component="tenant-form"))
        await session.commit()
    await engine.dispose()


async def _seed_tenant_tables(tmp_path: Path) -> None:
    """建 platform 服务租户库（角色域 + 账号表）。

    Args:
        tmp_path: 临时目录。
    """
    url = f"sqlite+aiosqlite:///{tmp_path}/bms_platform_platform.db"
    engine = create_async_engine(url)
    tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysUser.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    await engine.dispose()


@pytest.mark.kiwi_id(2343)
def test_seed_platform_main_success_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_platform.main` 正常路径：走种子并打印角色 / 授权 / 绑定计数。"""
    _templates(tmp_path, monkeypatch)

    async def _prepare() -> None:
        await _seed_platform_tables(tmp_path)
        await _seed_tenant_tables(tmp_path)

    asyncio.run(_prepare())
    assert platform_seed.main(ConcurrentStableList(["--code", "platform"])) == 0
    out = capsys.readouterr().out
    assert "[seed_platform] 角色新增 2" in out
    assert "授权新增" in out
    assert "绑定新增" in out
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
def test_rbac_safe_url_masks_password() -> None:
    """`_safe_url`：无口令原样返回；有口令只保留 scheme + 主机与库名。"""
    assert rbac_seed._safe_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"  # pyright: ignore[reportPrivateUsage]
    masked = rbac_seed._safe_url("mysql+aiomysql://root:secret@host:3306/db")  # pyright: ignore[reportPrivateUsage]
    assert masked == "mysql+aiomysql://***@host:3306/db"
    assert rbac_seed._safe_url("root:secret@host/db") == "***@host/db"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2343)
def test_rbac_resolve_platform_url_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """平台库解析：显式参数 > `BMS_MIGRATION_URL` > 按库键解析。"""
    assert rbac_seed._resolve_platform_url("sqlite+aiosqlite:///arg.db", service="platform") == (  # pyright: ignore[reportPrivateUsage]
        "sqlite+aiosqlite:///arg.db"
    )
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///env.db")
    assert rbac_seed._resolve_platform_url("", service="platform") == "sqlite+aiosqlite:///env.db"  # pyright: ignore[reportPrivateUsage]
    monkeypatch.delenv("BMS_MIGRATION_URL")
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    get_settings.cache_clear()
    resolved = rbac_seed._resolve_platform_url("", service="platform")  # pyright: ignore[reportPrivateUsage]
    assert resolved.endswith("bms_platform.db")
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
async def test_rbac_main_success_and_missing_codes_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_rbac.main` 正常路径：打印落库汇总，并在有缺码时打印缺码清单。"""
    await _seed_platform_tables(tmp_path)
    await _seed_tenant_tables(tmp_path)
    args = rbac_seed.build_parser().parse_args(
        [
            "--tenant",
            "platform",
            "--tenant-url",
            f"sqlite+aiosqlite:///{tmp_path}/bms_platform_platform.db",
            "--platform-url",
            f"sqlite+aiosqlite:///{tmp_path}/bms_platform.db",
        ]
    )
    await rbac_seed.main(args)
    out = capsys.readouterr().out
    assert "落库完成" in out
    assert "平台库未登记、已跳过的权限码" in out


@pytest.mark.kiwi_id(2343)
def test_sso_main_maps_user_when_both_args(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_sso.main` 正常路径带映射：写 IdP 行后继续写用户映射并打印计数（同步用例：main 内部自起事件循环）。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path}/identity.db"
    platform_url = f"sqlite+aiosqlite:///{tmp_path}/identity_platform.db"
    assert (
        sso_seed.main(
            ConcurrentStableList(
                [
                    "--url",
                    tenant_url,
                    "--platform-url",
                    platform_url,
                    "--map-user-id",
                    "11",
                    "--map-external-id",
                    "ext-11",
                ]
            )
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "用户映射新增 1 行" in out


@pytest.mark.kiwi_id(2343)
def test_user_main_prints_password_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_user.main` 建号后打印一次性口令（`outcome.password` 分支）。"""
    url = f"sqlite+aiosqlite:///{tmp_path}/platform.db"
    assert user_seed.main(ConcurrentStableList(["--url", url, "--username", "admin"])) == 0
    out = capsys.readouterr().out
    assert "口令（仅本次打印，请立即保存并在首登后修改）" in out
    assert "Bms1@" in out


@pytest.mark.kiwi_id(2343)
def test_provisioning_main_skips_password_line_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`provisioning.main` 成功但无初始口令时不打印口令行（`initial_password` 为空分支）。"""

    async def _fake(**_kwargs: object) -> provisioning.ProvisionOutcome:
        return provisioning.ProvisionOutcome(db_basis="demo", initial_password="")

    monkeypatch.setattr(provisioning, "provision_infrastructure", _fake)
    assert provisioning.main(ConcurrentStableList(["--code", "demo"])) == 0
    out = capsys.readouterr().out
    assert "[tenant_provisioning] 完成：服务" in out
    assert "口令" not in out
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
async def test_provisioning_create_database_returns_false_is_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`create_database` 返回 False（库已存在）时不计入 `created_databases`。"""
    _templates(tmp_path, monkeypatch)
    await _seed_platform_tables(tmp_path)
    await _seed_tenant_tables(tmp_path)

    async def _exists(_target: object) -> bool:
        return False

    monkeypatch.setattr(provisioning, "create_database", _exists)
    outcome = await provisioning.provision_infrastructure(db_basis="platform", platform=True)
    assert list(outcome.created_databases) == []
    get_settings.cache_clear()
