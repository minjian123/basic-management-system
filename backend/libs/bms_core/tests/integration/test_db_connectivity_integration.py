"""四库连通集成用例（Kiwi 984；标记 integration）。

- 三库（MySQL / PostgreSQL / 达梦）需 `BMS_TEST_DB_URL`，未配置即跳过（不阻塞冒烟层）；
- 用例名含方言标识，保证 `.gitlab-ci.yml` 的 `pytest -k "$DB_DIALECT"` 有匹配用例；
- 真库建库 / 迁移 / 清理与 CI `verify/db` 档归阶段二 01-05。
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from bms_core.core.config import Settings
from bms_core.db.engine import EngineFactory

pytestmark = pytest.mark.integration


def _require(dialect: str) -> str:
    """取真库连接串并校验方言（未配置 / 不匹配即跳过）。

    Args:
        dialect: 期望方言名（`mysql` / `postgresql` / `dm`）。

    Returns:
        str: 真库连接串。
    """
    url = os.environ.get("BMS_TEST_DB_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_DB_URL，跳过四库连通集成用例")
    if make_url(url).get_backend_name() != dialect:
        pytest.skip(f"BMS_TEST_DB_URL 方言与 {dialect} 不匹配")
    return url


def _factory(url: str) -> EngineFactory:
    """按连接串构造引擎工厂。"""
    settings = Settings()
    settings.database.platform.url = url
    settings.database.platform.replicas = []
    return EngineFactory(settings)


@pytest.mark.kiwi_id(984)
@pytest.mark.dialect_mysql
async def test_mysql_connectivity() -> None:
    """MySQL 连通性（`SELECT 1`）。"""
    factory = _factory(_require("mysql"))
    async with factory.create("platform").connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar() == 1
    await factory.aclose()


@pytest.mark.kiwi_id(984)
@pytest.mark.dialect_postgres
async def test_postgres_connectivity() -> None:
    """PostgreSQL 连通性（`SELECT 1`）。"""
    factory = _factory(_require("postgresql"))
    async with factory.create("platform").connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar() == 1
    await factory.aclose()


@pytest.mark.kiwi_id(984)
@pytest.mark.dialect_dm8
async def test_dm8_connectivity() -> None:
    """达梦 DM8 连通性（同步引擎，`SELECT 1`）。"""
    factory = _factory(_require("dm"))
    with factory.create_sync("platform").connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
    await factory.aclose()


@pytest.mark.kiwi_id(984)
async def test_sqlite_connectivity() -> None:
    """SQLite 开发库连通性（`SELECT 1`）。"""
    factory = _factory("sqlite+aiosqlite:///:memory:")
    async with factory.create("platform").connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar() == 1
    await factory.aclose()
