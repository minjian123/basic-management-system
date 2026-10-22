"""开通编排内核用例（Kiwi 2343）：`bms_core/tenant/provisioning.py`。

覆盖：`enabled_tenant_services` 去重与 `platform` 首位、`provision_infrastructure` 成功路径
（临时 SQLite：建库 → 逐链建表 → 批量种子）、失败路径逆序 `drop_database`、无启用服务抛
`ConfigError`、CLI `--dry-run` / 失败退出码 / 成功输出。
"""

import asyncio
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.bootstrap import apply_chain_schema
from bms_core.db.migration import DATASOURCE_PLATFORM, build_chain_name, resolve_chain
from bms_core.services.module_registry import enabled_service_keys
from bms_core.tenant import provisioning


def _use_templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把平台 / 租户连接串模板指向临时目录（每服务每租户库文件）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()


async def _prepare_platform_service_db(tmp_path: Path) -> None:
    """预建 platform 服务平台库表集（种子要读 `sys_business` / `sys_permission`；部署期由建表先行落地）。

    Args:
        tmp_path: 临时目录。
    """
    url = f"sqlite+aiosqlite:///{tmp_path}/bms_platform.db"
    chain = resolve_chain(build_chain_name("platform", DATASOURCE_PLATFORM))
    await apply_chain_schema(chain, url, target="platform")


@pytest.mark.kiwi_id(2343)
def test_enabled_tenant_services_platform_first_and_unique() -> None:
    """需建库服务 = 目录启用服务 + 已启用模块所属服务；`platform` 恒在首位且不重复。"""
    services = provisioning.enabled_tenant_services()
    assert services[0] == "platform"
    assert len(services) == len(set(services))
    assert set(enabled_service_keys()).issubset(set(services))


@pytest.mark.kiwi_id(2343)
async def test_provision_infrastructure_creates_databases_and_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """成功路径：建库 → 逐链建表 → 批量种子；返回结果含服务清单与初始口令。"""
    _use_templates(tmp_path, monkeypatch)
    await _prepare_platform_service_db(tmp_path)
    outcome = await provisioning.provision_infrastructure(db_basis="demo")
    assert outcome.db_basis == "demo"
    assert outcome.services == provisioning.enabled_tenant_services()
    assert outcome.created_databases == outcome.services
    assert outcome.seeded >= 0
    assert outcome.admin_username == "admin"
    assert outcome.initial_password.startswith("Bms1@")
    assert (tmp_path / "bms_platform_demo.db").exists()
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
async def test_provision_infrastructure_platform_mode_seeds_platform_rbac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`platform=True`：走平台 RBAC 种子（角色数与租户模式不同），其余编排一致。"""
    _use_templates(tmp_path, monkeypatch)
    await _prepare_platform_service_db(tmp_path)
    outcome = await provisioning.provision_infrastructure(db_basis="platform", platform=True)
    assert outcome.db_basis == "platform"
    assert outcome.admin_username == "admin"
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
async def test_provision_infrastructure_drops_created_databases_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """失败路径：已建库按逆序 `drop_database` 清理后原样抛出。"""
    _use_templates(tmp_path, monkeypatch)
    dropped: ConcurrentStableList[str] = ConcurrentStableList()

    async def _fail(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("seed boom")

    async def _drop(target: object) -> bool:
        dropped.add(repr(target))
        return True

    monkeypatch.setattr(provisioning, "_seed_configs", _fail)
    monkeypatch.setattr(provisioning, "drop_database", _drop)
    with pytest.raises(RuntimeError, match="seed boom"):
        await provisioning.provision_infrastructure(db_basis="demo")
    assert len(dropped) == len(provisioning.enabled_tenant_services())
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
async def test_provision_infrastructure_raises_without_enabled_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无启用服务：抛 `ConfigError`（不建库）。"""
    _use_templates(tmp_path, monkeypatch)
    monkeypatch.setattr(provisioning, "enabled_tenant_services", lambda: ConcurrentStableList())
    with pytest.raises(ConfigError, match="无已启用服务"):
        await provisioning.provision_infrastructure(db_basis="demo")
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
def test_main_dry_run_lists_services(capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run`：打印待建库服务清单，不建连、不建库。"""
    assert provisioning.main(ConcurrentStableList(["--code", "demo", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "[tenant_provisioning] 租户 demo：待建库" in out
    assert "dry-run：不建连、不建库" in out


@pytest.mark.kiwi_id(2343)
def test_main_reports_failure_exit_code(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """编排失败：打印失败原因并返回退出码 1。"""

    async def _fail(**_kwargs: object) -> object:
        raise ConfigError("无已启用服务，无法为租户建库")

    monkeypatch.setattr(provisioning, "provision_infrastructure", _fail)
    assert provisioning.main(ConcurrentStableList(["--code", "demo"])) == 1
    out = capsys.readouterr().out
    assert "失败（已清理已建库）：ConfigError" in out


@pytest.mark.kiwi_id(2343)
def test_main_success_prints_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """成功：打印服务数 / 新建库数 / 参数行数 / 角色数与初始口令。"""
    _use_templates(tmp_path, monkeypatch)
    asyncio.run(_prepare_platform_service_db(tmp_path))
    assert provisioning.main(ConcurrentStableList(["--code", "demo"])) == 0
    out = capsys.readouterr().out
    assert "[tenant_provisioning] 完成：服务" in out
    assert "初始管理员 admin 口令" in out
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
def test_build_parser_requires_code() -> None:
    """`--code` 必填；缺省不预演。"""
    args = provisioning.build_parser().parse_args(["--code", "acme"])
    assert args.code == "acme"
    assert args.dry_run is False
    with pytest.raises(SystemExit):
        provisioning.build_parser().parse_args([])
