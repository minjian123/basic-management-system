"""会话级全系统装配护栏（13_10）：一轮恰好一次、服务身份与配置各归各。

与 `test_assembled_system.py` 的分工：那里用假应用验证容器契约（不计入装配次数），
这里验证**真实会话的装配**——会话开始时 autouse 夹具已完成装配，故直接断言进程状态。
"""

from __future__ import annotations

import pytest

from bms_core.core.config import current_service, get_settings, reset_current_service, set_current_service
from bms_core.services.module_registry import SERVICE_CATALOG
from bms_core.testing.system import assemble_count, assembled_at, get_assembled_system

pytestmark = pytest.mark.kiwi_id(2556)

_HOSTED = "workflow"
"""由 platform 进程承载、无独立进程的服务键（装配阶段不单独启动）。"""


def test_assembled_exactly_once_per_session() -> None:
    """一轮会话（一个 worker 进程）只装配一次，且装配发生在用例之前。"""
    assert assemble_count() == 1
    assert assembled_at() is not None


def test_every_service_assembled_with_own_identity() -> None:
    """服务目录里的全部后端服务都已装配，且每个应用的服务身份是自身。"""
    system = get_assembled_system()
    expected = {record.service_key for record in SERVICE_CATALOG if record.service_key} - {_HOSTED}
    assert set(system.apps) == expected
    for key, app in system.apps.items():
        assert app.state.service_identity.name == key


def test_current_service_reset_after_assembly() -> None:
    """装配完成后当前服务键为空：非装配路径读默认配置，而不是最后一个服务的配置。"""
    assert current_service() == ""


def test_settings_are_slotted_per_service() -> None:
    """配置按服务分槽：切到某服务即读该服务的配置，互不覆盖。"""
    token = set_current_service("report")
    try:
        assert get_settings().app.service == "report"
    finally:
        reset_current_service(token)
    token = set_current_service("platform")
    try:
        assert get_settings().app.service == "platform"
    finally:
        reset_current_service(token)
