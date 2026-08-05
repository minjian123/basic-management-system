"""pytest 全局配置与 fixtures。

- 强制 BMS_ENV=test（在导入 app 之前设置），测试库走 config.toml [env.test.database]
  （SQLite 多文件模拟平台库/租户库，含 demo/demo2 两个演练租户）
- session 级：清理测试库文件并用同步引擎建表（同步建表避免跨 event loop 复用引擎）
- autouse：每个测试结束后释放引擎（pytest-asyncio 每测试独立 event loop，async engine 不可跨 loop 复用）
- client fixture：TestClient（ASGITransport 免起服务器）
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["BMS_ENV"] = "test"

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_db() -> None:
    """清理测试库文件并用同步引擎建表（平台库 + dev_tenants 租户库）。"""
    for f in DATA_DIR.glob("test_*.db"):
        f.unlink(missing_ok=True)

    from sqlalchemy import create_engine

    from app import models  # noqa: F401  pyright: ignore[reportUnusedImport]
    from app.core.config import get_settings
    from app.db.base import Base

    settings = get_settings()
    urls = [
        settings.database.platform_url,
        *(settings.database.tenant_url_template.replace("{code}", code) for code in settings.database.dev_tenants),
    ]
    for url in urls:
        sync_url = url.replace("sqlite+aiosqlite", "sqlite+pysqlite")
        engine = create_engine(sync_url)
        Base.metadata.create_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test() -> AsyncIterator[None]:
    """每个测试结束后释放引擎，避免 async engine 跨 pytest-asyncio 的 event loop 复用。"""
    yield
    from app.db.engine import get_registry

    await get_registry().dispose()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """ASGI 测试客户端（lifespan 自动执行，触发日志配置与 SQLite 建表）。"""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
