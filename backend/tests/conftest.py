"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离。"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """隔离配置：清除 `BMS_` 环境变量与 `.env` 读取，重置配置单例。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    for key in list(os.environ):
        if key.startswith("BMS_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端夹具（每个用例独立应用实例）。"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
