"""按「服务 × 租户」建库测试（Kiwi 2177）：服务集筛选 / 平台与租户库矩阵 / 幂等 / 干跑 / 租户来源。

覆盖 `ops/provision_tenant.py`：

- 服务维度取服务目录 `enabled` 服务（`--service` 可显式指定，未登记即拒）；
- 库矩阵：平台服务库 `bms_{service}`（键 `platform_{service}`）+ 服务租户库 `bms_{service}_{code}`
  （键 `tenant_{service}_{code}`），库名经 `url_template` 解析；
- 租户维度：`--code` 显式 / `--all-tenants` 读租户注册库（`platform_tenant`）；
- 幂等：重复执行全为「已存在（跳过）」；`--dry-run` 不建连不建库；
- `--skip-tenants` 只建平台服务库；缺租户维度即失败（退出码 1）。
"""

import asyncio
from pathlib import Path

import pytest

from bms_core.core.config import get_settings
from bms_core.services.module_registry import enabled_service_keys
from ops import provision_tenant
from ops.seed_tenant import seed_tenants


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


def test_dry_run_lists_full_service_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """干跑：按全部启用服务列出「平台服务库 + 服务租户库」矩阵，不建连不建库。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--code", "demo", "--dry-run"]) == 0
    out = capsys.readouterr().out
    services = enabled_service_keys()
    assert f"待建库 {len(services) * 2} 个目标" in out
    assert "platform_platform" in out
    assert "tenant_org_demo" in out
    assert "dry-run：不建连、不建库" in out
    assert not (tmp_path / "bms_org.db").exists()


def test_provision_creates_service_dbs_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """建库：平台服务库 + 服务租户库落盘；重复执行全为「已存在（跳过）」。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--code", "demo", "--service", "org"]) == 0
    assert (tmp_path / "bms_org.db").exists()
    assert (tmp_path / "bms_org_demo.db").exists()
    assert "新建 2" in capsys.readouterr().out

    assert provision_tenant.main(["--code", "demo", "--service", "org"]) == 0
    assert "已存在 2" in capsys.readouterr().out


def test_skip_tenants_builds_platform_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--skip-tenants`：只建平台服务库，无需租户维度。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--service", "org", "--skip-tenants"]) == 0
    assert (tmp_path / "bms_org.db").exists()
    assert not (tmp_path / "bms_org_demo.db").exists()
    assert "新建 1" in capsys.readouterr().out


def test_skip_platform_builds_tenant_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--skip-platform`：只建服务租户库。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--code", "demo", "--service", "org", "--skip-platform"]) == 0
    assert (tmp_path / "bms_org_demo.db").exists()
    assert not (tmp_path / "bms_org.db").exists()
    assert "新建 1" in capsys.readouterr().out


def test_requires_tenant_dimension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺租户维度（既无 `--code` 也无 `--all-tenants`）：失败退出并提示。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--service", "org"]) == 1
    assert "需 --code" in capsys.readouterr().out


def test_rejects_unregistered_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--service` 指定未登记服务标识：失败退出。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--code", "demo", "--service", "ghost"]) == 1
    assert "服务标识未登记" in capsys.readouterr().out


def test_all_tenants_reads_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--all-tenants`：从租户注册库（键 `platform_tenant`）读编码并逐租户建库。"""
    _use_templates(tmp_path, monkeypatch)
    asyncio.run(seed_tenants(f"sqlite+aiosqlite:///{tmp_path}/bms_tenant.db"))
    assert provision_tenant.main(["--all-tenants", "--service", "org"]) == 0
    assert (tmp_path / "bms_org.db").exists()
    assert (tmp_path / "bms_org_demo.db").exists()
    assert (tmp_path / "bms_org_acme.db").exists()
    assert "新建 3" in capsys.readouterr().out


def test_all_tenants_requires_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """租户注册库不可读：失败退出并提示先建库 + 迁移 + 种子。"""
    _use_templates(tmp_path, monkeypatch)
    assert provision_tenant.main(["--all-tenants", "--service", "org"]) == 1
    assert "租户注册库不可读" in capsys.readouterr().out
