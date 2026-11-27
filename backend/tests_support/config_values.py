"""临时改业务参数（测试支持）：写共享租户库 `sys_config` → 递增参数缓存版本 → 退出恢复原值。

为什么必须走库（13_10 P5）：参数在真实运行里只从「配置源」取，缓存按**版本号**失效。
用例若替换参数源（`dependency_overrides[get_config_source]`），验的是一条生产上不存在的路径，
且会让「改参数后请求能否看到新值」这类缺陷漏检（批次 1 实测过：缓存版本没递增，替身路径全绿、
真实路径读旧值）。故统一按真实路径准备：

1. 写 `sys_config`（存在则改值，不存在则插入）；
2. 递增参数缓存版本（全局位 / 租户主键 / 租户编码三处，见 `SqlConfigSource` 的键口径）；
3. 用例结束恢复原值（原本不存在则删除），并再次递增版本。

写入的都是用例自造的临时键（导入 / 导出专用），不改动与其它用例共用的参数；共享库并行下
按「键」而不是「表」收敛，退出时逐一还原。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.config.base import ConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.core.plugin import resolve_plugin
from bms_core.testing.transaction import write_session
from tests_support.auth import TEST_TENANT_CODE, TEST_TENANT_ID

__all__ = ["temporary_config_values"]


def _config_cache() -> ConfigCacheRegion:
    """取已装配的参数缓存域（与业务读同一实现、同一实例）。

    Returns:
        ConfigCacheRegion: 参数缓存域。
    """
    settings = get_settings()
    return cast("ConfigCacheRegion", resolve_plugin("config_cache_region", settings.config_cache_region.provider))


async def _bump(cache: ConfigCacheRegion) -> None:
    """递增参数缓存版本（三处键位：全局 / 租户主键 / 租户编码）。

    Args:
        cache: 参数缓存域。
    """
    for tenant in (None, TEST_TENANT_ID, TEST_TENANT_CODE):
        await cache.aincrease_version(tenant)


@asynccontextmanager
async def temporary_config_values(engine: AsyncEngine, values: ConcurrentStableDict[str, str]) -> AsyncGenerator[None]:
    """临时改系统参数（写租户库 `sys_config`，退出恢复原值）。

    Args:
        engine: 共享租户库引擎（写门会话）。
        values: 参数键 → 本次值（插入序）。

    Yields:
        None: 临时值生效期。
    """
    cache = _config_cache()
    original: ConcurrentStableDict[str, str | None] = ConcurrentStableDict()
    original_overridden: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    async with write_session(engine) as session:
        for key, value in values.items():
            row = (
                await session.execute(
                    select(SysConfig).where(SysConfig.config_key == key, SysConfig.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            original[key] = None if row is None else row.value
            original_overridden[key] = False if row is None else row.is_overridden
            # 必须转覆盖态（`is_overridden=true`）：播种对「未覆盖」的已有行会按平台默认清单刷新
            # `value`（`bms_core.config.seed` 的升级语义）。不置位时，同进程/同期任一处在临时值
            # 生效期内触发播种，参数就被刷回默认值——实测 CI 全量：`export.max_rows` 设 2 后被
            # 刷回 50000，导出不再超限，`assert 200 == 400`（本地无并发播种，不复现）。
            if row is None:
                session.add(SysConfig(config_key=key, name=key, value=value, form_key="config", is_overridden=True))
            else:
                row.value = value
                row.is_overridden = True
        await session.commit()
    await _bump(cache)
    try:
        yield
    finally:
        async with write_session(engine) as session:
            for key, value in original.items():
                row = (
                    await session.execute(
                        select(SysConfig).where(SysConfig.config_key == key, SysConfig.deleted_at.is_(None))
                    )
                ).scalar_one_or_none()
                if row is None:
                    continue
                if value is None:
                    await session.delete(row)
                else:
                    row.value = value
                    row.is_overridden = original_overridden[key]
            await session.commit()
        await _bump(cache)
