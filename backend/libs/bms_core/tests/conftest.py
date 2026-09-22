"""基座库 pytest 公共夹具：配置环境隔离 + 平台库租户种子 + 请求上下文复位。

本套件只覆盖 `bms_core`（不依赖平台服务应用），故不提供 `client` 夹具；
需要构造应用 / 打接口的用例归 `services/platform/tests`。
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from bms_core.core.config import Settings, get_settings
from bms_core.core.context import (
    current_client_ip,
    current_request_id,
    current_tenant,
    current_tenant_context_var,
    current_trace_id,
    current_user_id,
)
from ops.seed_tenant import seed_tenants


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """隔离配置：清除 `BMS_` 环境变量与 `.env` 读取，重置配置单例。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    for key in list(os.environ):
        if key.startswith("BMS_") and not key.startswith("BMS_TEST_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def platform_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """平台库隔离：临时 `sys_tenant` 种子库（供租户解析相关用例）。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'app.db'}"
    await seed_tenants(platform_url)
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", platform_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_request_context() -> Iterator[None]:
    """用例结束后复位请求上下文（链路 / 请求 / 来源 / 租户 / 用户），防跨用例污染。

    Yields:
        None: 用例运行期。
    """
    yield
    current_trace_id.set(None)
    current_request_id.set(None)
    current_client_ip.set(None)
    current_tenant.set(None)
    current_tenant_context_var.set(None)
    current_user_id.set(None)
