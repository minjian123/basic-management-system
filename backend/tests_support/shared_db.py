"""共享测试库准备集（薄壳）：转发基座通用实现 `bms_core.testing.shared_db`。

口径与参数见 `bms_core.testing.shared_db`（2026-11-04 下沉：实现只依赖 `bms_core` 自身，
平台仓与产品仓共用一份，各仓只在此声明「额外模型模块 / 种子口径」）。

本仓（平台）额外声明：种服务目录与产品档案（`seed_catalog=True`）——服务目录种子取
「平台常量 + 已装载产品清单」合并视图，产品清单由种子内部按本仓清单重新装载，避免沿用
前序用例注册 / 复位后的进程态而让准备内容随执行顺序漂移。
"""

from __future__ import annotations

from bms_core.testing import shared_db as base_shared_db
from bms_core.testing.shared_db import (
    SEED_TENANT_IDS,
    align_seed_tenant_ids,
    default_model_modules,
    tenant_metadata,
)

__all__ = [
    "SEED_TENANT_IDS",
    "align_seed_tenant_ids",
    "default_model_modules",
    "prepare_platform",
    "prepare_platform_async",
    "prepare_tenant",
    "prepare_tenant_async",
    "tenant_metadata",
]


def prepare_platform(url: str) -> None:
    """准备平台库：建表 → 种子租户 → 主键对齐 → 服务目录与产品档案（幂等）。

    Args:
        url: 共享平台库连接串。
    """
    base_shared_db.prepare_platform(url, seed_catalog=True)


async def prepare_platform_async(url: str) -> None:
    """平台库准备集的异步入口（供异步夹具调用，避免在事件循环里 `asyncio.run`）。

    Args:
        url: 共享平台库连接串。
    """
    await base_shared_db.prepare_platform_async(url, seed_catalog=True)


def prepare_tenant(url: str) -> None:
    """准备租户库：租户侧建表集（各业务域并集 + 基础设施表）→ 系统参数种子。

    Args:
        url: 共享租户库连接串。
    """
    base_shared_db.prepare_tenant(url)


async def prepare_tenant_async(url: str) -> None:
    """租户库准备集的异步入口（供异步夹具调用）。

    Args:
        url: 共享租户库连接串。
    """
    await base_shared_db.prepare_tenant_async(url)
