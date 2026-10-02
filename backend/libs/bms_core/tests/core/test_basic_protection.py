"""基础防护与密钥管理落地测试（Kiwi 2226）：文档端点环境开关 + `.env.example` 键位门禁。

口径：`[app].docs_enabled` 控制 `/docs` / `/redoc` / `/openapi.json` 三端点（基线开、生产关），
关闭后契约仍经 `app.openapi()` 生成（CI swagger-snapshot 不受影响）；两份环境变量模板经
`check-env-example.py` 门禁（密钥键位齐备 / 无废弃键 / 无真实密钥）。
"""

import subprocess
import sys

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.application import BaseServiceApplicationFactory
from bms_core.core.config import get_settings
from bms_core.db.migration import BACKEND_ROOT

_REPO = BACKEND_ROOT.parent
_GUARD = _REPO / "scripts" / "tools" / "base-check" / "check-env-example.py"


class _Factory(BaseServiceApplicationFactory):
    """测试用服务应用工厂（无业务路由，装配内建插件）。"""

    key: str = "application_factory"
    service_name: str = "basic_protection_test"
    service_title: str = "BMS 基础防护测试服务"
    version: str = "0.1.0"
    contract_version: str = "0.1.0"


async def _status(app: FastAPI, path: str) -> int:
    """请求指定路径取状态码。

    Args:
        app: 应用实例。
        path: 请求路径。

    Returns:
        int: HTTP 状态码。
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return (await client.get(path)).status_code


@pytest.mark.kiwi_id(2226)
async def test_docs_endpoints_follow_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认开（三端点可达）；置 `docs_enabled=false` 后三端点 404，`app.openapi()` 仍可用。"""
    monkeypatch.setenv("BMS_APP__DOCS_ENABLED", "true")
    get_settings.cache_clear()
    enabled = _Factory().create(None)
    assert enabled.docs_url == "/docs"
    assert enabled.redoc_url == "/redoc"
    assert enabled.openapi_url == "/openapi.json"
    assert await _status(enabled, "/docs") == 200
    assert await _status(enabled, "/redoc") == 200
    assert await _status(enabled, "/openapi.json") == 200

    monkeypatch.setenv("BMS_APP__DOCS_ENABLED", "false")
    get_settings.cache_clear()
    disabled = _Factory().create(None)
    assert disabled.docs_url is None
    assert disabled.redoc_url is None
    assert disabled.openapi_url is None
    assert await _status(disabled, "/docs") == 404
    assert await _status(disabled, "/redoc") == 404
    assert await _status(disabled, "/openapi.json") == 404
    # 契约生成方法不依赖端点（CI swagger-snapshot 经 app.openapi() 取数）
    assert "openapi" in disabled.openapi()


@pytest.mark.kiwi_id(2226)
def test_env_example_keys_pass_guard() -> None:
    """真实仓库两份模板通过键位门禁；`--self-test` 覆盖反例（自检通过）。"""
    check = subprocess.run([sys.executable, str(_GUARD), str(_REPO)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    self_test = subprocess.run([sys.executable, str(_GUARD), "--self-test"], capture_output=True, text=True)
    assert self_test.returncode == 0, self_test.stdout + self_test.stderr
