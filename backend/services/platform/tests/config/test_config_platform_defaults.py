"""系统参数的**平台默认值语义**用例：重置回落默认 / 乐观锁冲突 / 依赖双向校验。

这些用例的断言绑定**平台默认值表**（`_PLATFORM_DEFAULTS`）与硬编码依赖对（`ai.auto_execute`
↔ `ai.auto_approve`），必须使用固定参数键、并要求「该键初始为未覆盖态」的起点；
共享租户库里这些键由 `seed_configs` 播种且被其他用例读写（SQLite 单写者，长事务叠加会互等）。

`own_db` 白名单（04-6-2 决策 D）：每用例独立临时库 + 平台默认参数播种，故独占、不叠加。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.config.seed import seed_configs
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConcurrentConflictError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.testing.schema import ensure_tables
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.platform_config.schemas.config import ConfigUpdateRequest
from bms_platform.domains.platform_config.services.config import ConfigAdminService

pytestmark = pytest.mark.own_db(
    "断言语义绑定平台默认值表与硬编码依赖对，前提是「该键初始为未覆盖态」；"
    "共享租户库的默认参数被其他用例读写，且 SQLite 单写者下长事务叠加会互等"
)

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList((SysConfig.__table__,))
"""本文件涉及的表（独占库建表集）。"""


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """独占临时租户库会话（建表 + 平台默认参数播种）。

    Args:
        tmp_path: 用例级临时目录。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'config_defaults.db'}")
    try:
        await ensure_tables(engine, list(_TABLES))
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            await seed_configs(db)
            await db.commit()
            yield db
    finally:
        await engine.dispose()


def _service(session: AsyncSession) -> ConfigAdminService:
    """构造管理服务（请求级会话 + 内存缓存域）。

    Args:
        session: 租户库会话。

    Returns:
        ConfigAdminService: 服务实例。
    """
    return ConfigAdminService(ConfigRepository(session), DbUnitOfWork(session), cache=MemoryConfigCacheRegion())


class _AlwaysConflictingRepository(ConfigRepository):
    """乐观锁恒失败的仓储替身（覆盖重置路径的并发冲突分支）。"""

    async def update_checked(self, item_id: int, *, expected_version: int, now: datetime, **values: object) -> bool:
        """恒返回失败。

        Args:
            item_id: 参数主键。
            expected_version: 期望版本。
            now: 当前时刻。
            **values: 待更新字段。

        Returns:
            bool: 恒 False。
        """
        return False


async def test_reset_restores_default_and_clears_flag(session: AsyncSession) -> None:
    """重置：值回落平台默认、覆盖标记清空、来源回到 platform。"""
    service = _service(session)
    detail = await service.detail("session.max_active")
    await service.update(detail.id, ConfigUpdateRequest(value="9", version=detail.version))

    overridden = await service.detail("session.max_active")
    assert overridden.source == "tenant"
    reset = await service.reset(overridden.id)
    assert reset.value == "5"
    assert reset.source == "platform"

    again = await service.reset(reset.id)
    assert again.value == "5"


async def test_reset_raises_conflict_when_version_stale(session: AsyncSession) -> None:
    """重置：乐观锁失败时抛并发冲突（`10004`）。"""
    service = _service(session)
    detail = await service.detail("account.inactive_lock_days")
    await service.update(detail.id, ConfigUpdateRequest(value="90", version=detail.version))
    overridden = await service.detail("account.inactive_lock_days")

    conflicting = ConfigAdminService(
        _AlwaysConflictingRepository(session),
        DbUnitOfWork(session),
        cache=MemoryConfigCacheRegion(),
    )
    with pytest.raises(ConcurrentConflictError):
        await conflicting.reset(overridden.id)


async def test_dependency_reverse_allows_close_when_dependent_off(session: AsyncSession) -> None:
    """依赖反向校验：被依赖项可关闭（依赖项存在但未开启）。"""
    service = _service(session)
    detail = await service.detail("ai.auto_execute")

    updated = await service.update(detail.id, ConfigUpdateRequest(value="false", version=detail.version))
    assert updated.value == "false"


async def test_dependency_reverse_passes_when_keeping_dependency_on(session: AsyncSession) -> None:
    """依赖反向校验：被依赖项保持开启值时不拦截（只有关闭才拦）。"""
    service = _service(session)
    execute = await service.detail("ai.auto_execute")
    if execute.value != "true":
        await service.update(execute.id, ConfigUpdateRequest(value="true", version=execute.version))
    approve = await service.detail("ai.auto_approve")
    await service.update(approve.id, ConfigUpdateRequest(value="true", version=approve.version))

    detail = await service.detail("ai.auto_execute")
    updated = await service.update(detail.id, ConfigUpdateRequest(value="true", version=detail.version))
    assert updated.value == "true"


async def test_dependency_reverse_when_dependent_missing(session: AsyncSession) -> None:
    """依赖反向校验：依赖项参数不存在时直接放行（不 phantom 拦截）。"""
    dependent = (
        (await session.execute(select(SysConfig).where(SysConfig.config_key == "ai.auto_approve"))).scalars().first()
    )
    assert dependent is not None
    dependent.soft_delete()
    await session.commit()

    service = _service(session)
    detail = await service.detail("ai.auto_execute")
    updated = await service.update(detail.id, ConfigUpdateRequest(value="false", version=detail.version))
    assert updated.value == "false"
