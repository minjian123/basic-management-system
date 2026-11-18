"""首页工作台种子：内置卡 + 平台默认模板 + 英文文案（幂等、只增不改，11_01）。

**口径**（概要 35 §6、架构 29 §3）：

- 内置卡（`card_type=builtin`）由平台种子登记，随租户开通写入租户库；平台升级新增内置卡时对存量租户
  重跑同一幂等种子即可补齐；
- **只增不改**：`code` 已存在的活行一律跳过——租户停用过的卡片不会被重新启用、改过的名称不会被覆盖；
- 平台默认模板（`scope=platform`）缺失才写入，初值 = 当前启用卡片按 `sort` 的行流式布局；
- 英文文案（`en-US`）缺失才补，已有同语言活行不覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.dashboard.layout import CardSize, layout_json, minimal_layout
from bms_core.db.session import DbSession
from bms_core.models.platform.dashboard import (
    CARD_TYPE_BUILTIN,
    SCOPE_PLATFORM,
    STATUS_ENABLED,
    SysDashboardCard,
    SysDashboardCardI18n,
    SysDashboardTemplate,
)

__all__ = [
    "BUILTIN_CARDS",
    "PLATFORM_TEMPLATE_NAME",
    "BuiltinCardSpec",
    "DashboardSeedOutcome",
    "seed_dashboard",
    "seed_dashboard_entry",
]

SEED_LOCALE_EN = "en-US"
"""种子英文文案语言标识。"""

PLATFORM_TEMPLATE_NAME = "平台默认布局"
"""平台默认模板名称。"""


@dataclass(frozen=True)
class BuiltinCardSpec(BaseValueObject):
    """内置卡声明（平台种子事实源）。"""

    code: str
    """卡片标识。"""
    name: str
    """中文名称（主表默认文案）。"""
    name_en: str
    """英文名称（`sys_dashboard_card_i18n`）。"""
    render_key: str
    """前端渲染器标识。"""
    data_endpoint: str
    """数据接口地址（空表示前端按渲染器自身逻辑取数或占位）。"""
    default_width: int
    """默认宽（列）。"""
    default_height: int
    """默认高（行）。"""
    mobile_supported: bool
    """是否参与移动端单列布局。"""
    sort: int
    """排序（升序，按 10 递增留插入空间）。"""


BUILTIN_CARDS: ConcurrentStableFrozenList[BuiltinCardSpec] = ConcurrentStableFrozenList(
    (
        BuiltinCardSpec(
            code="todo",
            name="待办 / 已办",
            name_en="To-do / Done",
            render_key="todo",
            data_endpoint="",
            default_width=4,
            default_height=2,
            mobile_supported=True,
            sort=10,
        ),
        BuiltinCardSpec(
            code="notification",
            name="通知",
            name_en="Notifications",
            render_key="notification",
            data_endpoint="/api/v1/notifications",
            default_width=4,
            default_height=2,
            mobile_supported=True,
            sort=20,
        ),
        BuiltinCardSpec(
            code="notice",
            name="公告",
            name_en="Announcements",
            render_key="notice",
            data_endpoint="/api/v1/notices/published",
            default_width=4,
            default_height=2,
            mobile_supported=True,
            sort=30,
        ),
        BuiltinCardSpec(
            code="quick_links",
            name="快捷入口",
            name_en="Quick links",
            render_key="quick_links",
            data_endpoint="/api/v1/menus/my",
            default_width=2,
            default_height=2,
            mobile_supported=True,
            sort=40,
        ),
        BuiltinCardSpec(
            code="help",
            name="帮助入口",
            name_en="Help",
            render_key="help",
            data_endpoint="/api/v1/help/context",
            default_width=2,
            default_height=2,
            mobile_supported=False,
            sort=50,
        ),
        BuiltinCardSpec(
            code="stats",
            name="数据统计",
            name_en="Statistics",
            render_key="stats",
            data_endpoint="",
            default_width=6,
            default_height=2,
            mobile_supported=False,
            sort=60,
        ),
    )
)
"""内置卡清单（6 张：待办 / 通知 / 公告 / 快捷入口 / 帮助入口 / 数据统计）。"""


@dataclass(frozen=True)
class DashboardSeedOutcome(BaseValueObject):
    """种子执行结果（逐项计数，供编排报告与用例断言）。"""

    created_cards: int = 0
    """新建卡片数。"""
    created_texts: int = 0
    """新增英文文案数。"""
    created_templates: int = 0
    """新建平台默认模板数。"""


async def _active_cards(session: DbSession) -> ConcurrentStableList[SysDashboardCard]:
    """取全部启用卡片（按 `sort` 升序、同序按 `code` 升序）。

    Args:
        session: 目标租户库会话。

    Returns:
        ConcurrentStableList[SysDashboardCard]: 启用卡片（插入序即排布序）。
    """
    statement = (
        select(SysDashboardCard)
        .where(SysDashboardCard.status == STATUS_ENABLED)
        .where(SysDashboardCard.deleted_at.is_(None))
        .order_by(SysDashboardCard.sort, SysDashboardCard.code)
    )
    return ConcurrentStableList((await session.execute(statement)).scalars().all())


async def _ensure_en_text(session: DbSession, card_id: int, text: str) -> bool:
    """确保某卡片的英文文案存在（已有活行则跳过）。

    Args:
        session: 目标租户库会话。
        card_id: 卡片主键。
        text: 英文名称。

    Returns:
        bool: 新增为 True。
    """
    statement = (
        select(SysDashboardCardI18n)
        .where(SysDashboardCardI18n.card_id == card_id)
        .where(SysDashboardCardI18n.locale == SEED_LOCALE_EN)
        .where(SysDashboardCardI18n.deleted_at.is_(None))
    )
    existing = (await session.execute(statement)).scalars().first()
    if existing is not None:
        return False
    session.add(SysDashboardCardI18n(card_id=card_id, locale=SEED_LOCALE_EN, name=text))
    await session.flush()
    return True


async def seed_dashboard(session: DbSession) -> DashboardSeedOutcome:
    """写入内置卡、英文文案与平台默认模板（幂等、只增不改）。

    Args:
        session: 目标租户库会话（编排层负责事务提交）。

    Returns:
        DashboardSeedOutcome: 逐项计数。
    """
    created_cards = 0
    created_texts = 0
    for spec in BUILTIN_CARDS:
        statement = (
            select(SysDashboardCard)
            .where(SysDashboardCard.code == spec.code)
            .where(SysDashboardCard.deleted_at.is_(None))
        )
        existing = (await session.execute(statement)).scalars().first()
        if existing is None:
            card = SysDashboardCard(
                code=spec.code,
                name=spec.name,
                card_type=CARD_TYPE_BUILTIN,
                render_key=spec.render_key,
                data_endpoint=spec.data_endpoint,
                default_width=spec.default_width,
                default_height=spec.default_height,
                mobile_supported=spec.mobile_supported,
                sort=spec.sort,
                status=STATUS_ENABLED,
            )
            session.add(card)
            await session.flush()
            created_cards += 1
            existing = card
        if await _ensure_en_text(session, int(existing.id), spec.name_en):
            created_texts += 1
    created_templates = 0
    template_statement = (
        select(SysDashboardTemplate)
        .where(SysDashboardTemplate.scope == SCOPE_PLATFORM)
        .where(SysDashboardTemplate.deleted_at.is_(None))
    )
    if (await session.execute(template_statement)).scalars().first() is None:
        cards = await _active_cards(session)
        sizes: ConcurrentStableList[CardSize] = ConcurrentStableList(
            CardSize(code=card.code, width=int(card.default_width), height=int(card.default_height))
            for card in cards
        )
        session.add(
            SysDashboardTemplate(
                scope=SCOPE_PLATFORM,
                role_id=0,
                name=PLATFORM_TEMPLATE_NAME,
                layout_config=layout_json(minimal_layout(ConcurrentStableFrozenList(sizes))),
                status=STATUS_ENABLED,
            )
        )
        await session.flush()
        created_templates = 1
    return DashboardSeedOutcome(
        created_cards=created_cards,
        created_texts=created_texts,
        created_templates=created_templates,
    )


async def seed_dashboard_entry(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
    """XA 分支入口（种子编排调用）：在分支会话内幂等写入工作台种子。

    Args:
        session: 已绑定 XA 分支连接的会话。
        args: 分支参数（本种子不消费）。
    """
    del args
    await seed_dashboard(session)
