"""平台默认种子刷新用例（Kiwi 2373）：首次全量写入 / 二次幂等 / 未覆盖行随清单刷新 / 覆盖行不动。

种子是「平台默认」的构建期权威：租户开通与 `ops.seed_config` 共用；本段把「存在即跳过」改为
「未覆盖则按清单刷新」，因此需要用例锁住三种状态：新增、刷新、跳过覆盖行。
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.models import SysConfig
from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS, seed_configs
from bms_core.core.config import get_settings
from bms_core.db.bootstrap import apply_unit_schema

pytestmark = pytest.mark.kiwi_id(2373)


@pytest.fixture
def config_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """临时租户库（`platform:tenant` 链表集）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        str: 测试库 URL。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'config_seed.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    asyncio.run(apply_unit_schema("platform", "tenant", url, target="config_seed"))
    yield url
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncIterator[None]:
    """用例结束清理（保持与其他 config 用例同构）。

    Yields:
        None: 用例运行期。
    """
    yield


async def _run_seed(url: str) -> int:
    """对目标库执行一次种子。

    Args:
        url: 测试库 URL。

    Returns:
        int: 新增行数。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await seed_configs(session)
    finally:
        await engine.dispose()


async def _row(url: str, config_key: str) -> SysConfig | None:
    """取单行参数。

    Args:
        url: 测试库 URL。
        config_key: 参数键。

    Returns:
        SysConfig | None: 参数行。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysConfig).where(SysConfig.config_key == config_key)
            return (await session.execute(statement)).scalars().first()
    finally:
        await engine.dispose()


async def _set(url: str, config_key: str, *, value: str, is_overridden: bool) -> None:
    """直接改一行的值与覆盖标记（模拟租户覆盖 / 平台默认变更）。

    Args:
        url: 测试库 URL。
        config_key: 参数键。
        value: 参数值。
        is_overridden: 覆盖标记。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysConfig).where(SysConfig.config_key == config_key)
            row = (await session.execute(statement)).scalars().one()
            row.value = value
            row.is_overridden = is_overridden
            await session.commit()
    finally:
        await engine.dispose()


def test_seed_writes_all_defaults_once(config_db_url: str) -> None:
    """首次种子：写入清单全量，全部为未覆盖态（平台默认）。"""
    created = asyncio.run(_run_seed(config_db_url))
    assert created == len(PLATFORM_CONFIG_DEFAULTS)

    again = asyncio.run(_run_seed(config_db_url))
    assert again == 0


@pytest.mark.parametrize(
    ("config_key", "default_value"),
    (
        ("menu.tree_cache_ttl", "300"),
        ("role.code_pattern", "^[a-z][a-z0-9_-]{1,31}$"),
        ("session.max_active", "5"),
        ("file.upload.max_size", "20971520"),
        ("file.upload.max_file_size", "2147483648"),
        ("ai.auto_execute", "false"),
        ("ai.auto_approve", "false"),
    ),
)
def test_seed_covers_consumed_keys(config_db_url: str, config_key: str, default_value: str) -> None:
    """清单覆盖消费方已读取但此前未登记的键。

    Args:
        config_db_url: 测试库 URL。
        config_key: 参数键。
        default_value: 期望默认值。
    """
    asyncio.run(_run_seed(config_db_url))
    row = asyncio.run(_row(config_db_url, config_key))
    assert row is not None
    assert row.value == default_value
    assert row.is_overridden is False


def test_seed_refreshes_uncovered_but_keeps_overridden(config_db_url: str) -> None:
    """未覆盖行按清单刷新（平台默认升级下发），已覆盖行保持租户值。"""
    asyncio.run(_run_seed(config_db_url))
    asyncio.run(_set(config_db_url, "password.max_age_days", value="30", is_overridden=False))
    asyncio.run(_set(config_db_url, "password.min_length", value="12", is_overridden=True))

    created = asyncio.run(_run_seed(config_db_url))
    assert created == 0

    refreshed = asyncio.run(_row(config_db_url, "password.max_age_days"))
    assert refreshed is not None
    assert refreshed.value == "90"

    kept = asyncio.run(_row(config_db_url, "password.min_length"))
    assert kept is not None
    assert kept.value == "12"
    assert kept.is_overridden is True
