"""按服务连接预算离线核对测试（Kiwi 1078）：逐行输出、按服务筛选与超限退出码。"""

import pytest

from bms_core.core.config import DbPoolSettings, get_settings
from ops.check_budget import main


@pytest.mark.kiwi_id(2178)
def test_check_budget_pass_and_service_filter(capsys: pytest.CaptureFixture[str]) -> None:
    """默认口径通过；`--service` 只核算指定服务（行数 = 服务 × 库类别 + 归档）。"""
    settings = get_settings()
    settings.database.platform.max_connections = 0
    settings.database.tenants.max_connections = 0
    settings.database.archive.max_connections = 0

    assert main(["--service", "platform"]) == 0
    out = capsys.readouterr().out
    assert "platform.platform" in out and "platform.tenants" in out and "archive" in out
    assert "校验通过" in out


@pytest.mark.kiwi_id(2178)
def test_check_budget_exceeded(capsys: pytest.CaptureFixture[str]) -> None:
    """超限行 → 退出码 1 并输出超限明细（含算式与服务名）。"""
    settings = get_settings()
    settings.server.workers = 4
    settings.database.platform.max_connections = 10
    settings.database.platform.pool = DbPoolSettings(pool_size=5, max_overflow=10)

    assert main(["--service", "platform"]) == 1
    out = capsys.readouterr().out
    assert "超限" in out and "platform.platform" in out

    settings.database.platform.max_connections = 0
    settings.server.workers = 1


@pytest.mark.kiwi_id(2178)
def test_check_budget_active_tenants(capsys: pytest.CaptureFixture[str]) -> None:
    """`--active-tenants`：租户库按活跃租户数核算（超限即失败）。"""
    settings = get_settings()
    settings.server.workers = 1
    settings.server.workers_by_service = {}
    settings.database.tenants.max_connections = 30  # 预算上限 21：1 个活跃租户 15 通过、3 个 45 超限
    settings.database.tenants.pool = DbPoolSettings(pool_size=5, max_overflow=10)
    settings.database.tenants.services = {}

    assert main(["--service", "ai", "--active-tenants", "1"]) == 0
    capsys.readouterr()
    assert main(["--service", "ai", "--active-tenants", "3"]) == 1
    assert "3 活跃租户" in capsys.readouterr().out

    settings.database.tenants.max_connections = 0
