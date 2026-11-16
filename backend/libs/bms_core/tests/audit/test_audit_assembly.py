"""字段级审计装配护栏（06_02）：应用创建即挂载 ORM 捕获监听。

Kiwi 2515（与字段级审计用例共用同一编号）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bms_core.application import BaseServiceApplicationFactory
from bms_core.audit.field_capture import (
    install_field_audit,
    is_field_audit_installed,
    uninstall_field_audit,
)
from bms_core.core.plugin import default_plugin_registry

pytestmark = pytest.mark.kiwi_id(2515)


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    """每例前后解冻插件注册表（装配会 `build()`，并行下顺序敏感）。

    Yields:
        None: 用例运行期。
    """
    default_plugin_registry().reset()
    yield
    default_plugin_registry().reset()


class _Factory(BaseServiceApplicationFactory):
    """最小服务工厂（只为触发通用装配链）。"""

    key: str = "audit_capture_factory"
    service_name: str = "audit_capture_test"
    service_title: str = "字段级审计装配测试服务"
    version: str = "0.0.1"
    contract_version: str = "0.0.1"


def test_create_installs_field_audit_listener() -> None:
    """应用创建经基座装配链挂载捕获监听（幂等，重复创建不重复挂）。"""
    uninstall_field_audit()
    assert is_field_audit_installed() is False
    _Factory().create(None)
    assert is_field_audit_installed() is True
    assert install_field_audit() is True
    uninstall_field_audit()
