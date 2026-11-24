"""共享测试库准备集（薄壳）：转发基座通用实现 `bms_core.testing.shared_db`。

口径与参数见 `bms_core.testing.shared_db`（2026-11-04 下沉：实现只依赖 `bms_core` 自身，
平台仓与产品仓共用一份，各仓只在此声明「额外模型模块 / 种子口径」）。

本仓（平台）额外声明：种服务目录与产品档案（`seed_catalog=True`）——服务目录种子取
「平台常量 + 已装载产品清单」合并视图，产品清单由种子内部按本仓清单重新装载，避免沿用
前序用例注册 / 复位后的进程态而让准备内容随执行顺序漂移。

2026-11-16：基座准备集补播种「表归属登记」（启动期接库对账的输入，缺失即拒启）；本薄壳
源码摘要即库版本戳，故在此同步 bump，确保旧共享库重建。

2026-11-17：08_03 帮助内容五表进入 platform 服务租户链（`bms_core.models.platform.help`），
再次 bump 版本戳，确保共享测试库补建 `sys_help_*` 表。

2026-11-18：12_01 新增 `sys_help_feedback` 模型（同模块），再次 bump 版本戳，确保共享测试库补建反馈表。
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
    "prepare_tenant_writable",
    "prepare_tenant_writable_async",
    "tenant_metadata",
]


def prepare_platform(url: str) -> None:
    """准备平台库：建表 → 种子租户 → 主键对齐 → 服务目录与产品档案（幂等）。

    额外内容：
    - 测试专用表（`widget` / 自建字段探针表 `biz_ext_probe`），生产不建；
    - **结构变更声明**（`tests_support.form_design_changes`）：初始化阶段生成补列脚本并执行，
      执行语句与生成脚本逐条比对、执行后回读校验（不一致直接失败）。

    Args:
        url: 共享平台库连接串。
    """
    base_shared_db.prepare_platform(url, seed_catalog=True)
    from tests_support.widget_model import ensure_widget_table

    ensure_widget_table(url)
    _ensure_ext_probe_table(url)


def _ensure_ext_probe_table(url: str) -> None:
    """建自建字段补列用例的探针表（只存在于测试库；生产不建）。

    Args:
        url: 共享平台库连接串。
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(url.replace("+aiosqlite", ""))
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE IF NOT EXISTS biz_ext_probe (id INTEGER PRIMARY KEY)"))
    finally:
        engine.dispose()


async def prepare_platform_async(url: str) -> None:
    """平台库准备集的异步入口（供异步夹具调用，避免在事件循环里 `asyncio.run`）。

    Args:
        url: 共享平台库连接串。
    """
    await base_shared_db.prepare_platform_async(url, seed_catalog=True)


def prepare_tenant(url: str) -> None:
    """准备租户库：租户侧建表集（各业务域并集 + 基础设施表）→ 系统参数种子。

    额外内容：
    - 测试专用探针表 `biz_ext_probe`（生产不建）；
    - **结构变更声明**（`tests_support.form_design_changes`）：初始化阶段生成补列脚本并执行，
      执行语句与生成脚本逐条比对、执行后回读校验（不一致直接失败），并把实际脚本落盘。

    Args:
        url: 共享租户库连接串。
    """
    base_shared_db.prepare_tenant(url)
    _ensure_ext_probe_table(url)
    import asyncio

    from tests_support.form_design_changes import apply_changes

    asyncio.run(apply_changes(url))


async def prepare_tenant_async(url: str) -> None:
    """租户库准备集的异步入口（供异步夹具调用）。

    Args:
        url: 共享租户库连接串。
    """
    await base_shared_db.prepare_tenant_async(url)


def prepare_tenant_writable(url: str) -> None:
    """准备**破坏性操作用例专用**租户库（每轮一份；建表集与主测试租户库同源）。

    为什么要单独一份：按租户批量撤销会话这类操作会撤销本租户库全部在线会话，
    在主测试租户库上会波及其他用例。生产上一个租户一个库，这里按同一生产拓扑派生
    第二个租户库，只归破坏性用例使用。

    Args:
        url: 专用租户库连接串。
    """
    base_shared_db.prepare_tenant(url)


async def prepare_tenant_writable_async(url: str) -> None:
    """专用租户库准备集的异步入口（供异步夹具调用）。

    Args:
        url: 专用租户库连接串。
    """
    await base_shared_db.prepare_tenant_async(url)
