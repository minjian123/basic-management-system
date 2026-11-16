"""审计合规装配与种子护栏（06_02）：捕获实现选择 / 权限与菜单种子。"""

from __future__ import annotations

import pytest

from bms_core.audit.db_capturer import DbAuditCapturer
from bms_core.core.config import get_settings
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.tenant.seed.menu import BUTTON_SEEDS, MENU_SEEDS
from bms_core.tenant.seed.rbac import AUDIT_ADMIN_CODES

pytestmark = pytest.mark.kiwi_id(2515)


def test_platform_defaults_to_db_capturer() -> None:
    """平台服务在未显式配置时选真实捕获实现 `db`，且插件已登记可解析。"""
    from bms_platform.main import ApplicationFactory

    settings = get_settings()
    original = settings.audit.provider
    settings.audit.provider = ""
    try:
        ApplicationFactory().prepare_settings(settings)
        assert settings.audit.provider == DbAuditCapturer.plugin_name == "db"
        build_plugin_registry()
        assert isinstance(resolve_plugin("audit", "db"), DbAuditCapturer)
    finally:
        settings.audit.provider = original


def test_audit_admin_holds_manage_code() -> None:
    """审计管理员同时持有查询与链校验权限码（只读白名单）。"""
    assert "log:query" in AUDIT_ADMIN_CODES
    assert "log:manage" in AUDIT_ADMIN_CODES


def test_data_change_menu_and_buttons_seeded() -> None:
    """数据变更审计菜单与「查询 / 链校验」按钮已进种子（业务码 `log`）。"""
    menu = next(seed for seed in MENU_SEEDS if seed[1] == "/monitor/data-changes")
    assert menu[8] == "log"
    buttons = {(seed[0], seed[2]) for seed in BUTTON_SEEDS if seed[0] == "/monitor/data-changes"}
    assert buttons == {("/monitor/data-changes", "query"), ("/monitor/data-changes", "manage")}
