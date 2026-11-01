"""系统参数的**平台默认值语义**用例：重置回落默认 / 乐观锁冲突 / 依赖双向校验。

这些用例的断言绑定**平台默认值表**（`PLATFORM_CONFIG_DEFAULTS`）与硬编码依赖对
（`ai.auto_execute` ↔ `ai.auto_approve`），必须使用固定参数键、并要求「该键初始为未覆盖态」的起点。

单库叠加口径（04-6-2）：**不再每用例建独立库**——跑在共享租户库上，改为
「用例前确保这些键处于平台默认态（未覆盖、未软删）→ 用例内读写 → 用例后复位」；
同文件用例用 `xdist_group` 固定到同一 worker 串行执行（共享库文件的既有口径），
避免同文件内不同 worker 互相覆盖平台默认键。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConcurrentConflictError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.testing.schema import ensure_tables
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.platform_config.schemas.config import ConfigUpdateRequest
from bms_platform.domains.platform_config.services.config import ConfigAdminService
from tests_support.locks import file_lock

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList((cast("Table", SysConfig.__table__),))
"""本文件涉及的表（幂等建表集）。"""

_KEYS = ("session.max_active", "account.inactive_lock_days", "ai.auto_execute", "ai.auto_approve")
"""本文件读写并需要复位的参数键（平台默认值见 `PLATFORM_CONFIG_DEFAULTS`）。"""

_DEFAULTS = {item.config_key: item.value for item in PLATFORM_CONFIG_DEFAULTS}
"""参数键 → 平台默认值。"""

_LOCK_NAME = "config-platform-defaults"
"""跨进程锁名（共享租户库上这些固定键是全局状态，必须整体串行）。"""


async def _restore(db: AsyncSession) -> None:
    """把本文件涉及的参数键复位到平台默认态（值 / 未覆盖 / 未软删）。

    Args:
        db: 租户库会话。
    """
    rows = (await db.execute(select(SysConfig).where(SysConfig.config_key.in_(list(_KEYS))))).scalars().all()
    for row in rows:
        row.deleted_at = None
        row.value = _DEFAULTS.get(row.config_key, row.value)
        row.is_overridden = False
        row.status = "enabled"
    await db.commit()


@pytest_asyncio.fixture
async def session(tenant_db: str, shared_tenant_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享租户库会话（幂等建表 + 用例前后复位平台默认键）。

    Args:
        tenant_db: 共享租户库连接串（套件夹具已注入 `BMS_DATABASE__TENANTS__URL`）。
        shared_tenant_engine: 共享租户库引擎（基座夹具，不在此自建引擎）。

    Yields:
        AsyncSession: 会话。
    """
    del tenant_db
    with file_lock(_LOCK_NAME):
        await ensure_tables(shared_tenant_engine, _TABLES)
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
        async with factory() as db:
            await _restore(db)
            yield db
            await _restore(db)


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
