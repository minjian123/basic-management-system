"""工作台种子：内置卡 / 英文文案 / 平台默认模板，幂等且只增不改（Kiwi 2528）。"""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.models.platform.dashboard import (
    SCOPE_PLATFORM,
    SysDashboardCard,
    SysDashboardCardI18n,
    SysDashboardTemplate,
)
from bms_core.tenant.seed.dashboard import (
    BUILTIN_CARDS,
    PLATFORM_TEMPLATE_NAME,
    DashboardSeedOutcome,
    seed_dashboard,
    seed_dashboard_entry,
)
from tests_support.dashboard import memory_dashboard_session

pytestmark = pytest.mark.kiwi_id(2528)


async def _cards(session: AsyncSession) -> list[SysDashboardCard]:
    """取全部卡片。

    Args:
        session: 会话。

    Returns:
        list[SysDashboardCard]: 卡片行。
    """
    rows = (await session.execute(select(SysDashboardCard).order_by(SysDashboardCard.sort))).scalars().all()
    return list(rows)


async def test_seed_inserts_builtin_cards_texts_and_template() -> None:
    """首跑：6 张内置卡 + 英文文案 + 平台默认模板（行流式布局）。"""
    async with memory_dashboard_session() as session:
        outcome = await seed_dashboard(session)
        await session.commit()
        assert outcome == DashboardSeedOutcome(
            created_cards=len(BUILTIN_CARDS), created_texts=len(BUILTIN_CARDS), created_templates=1
        )
        cards = await _cards(session)
        assert [card.code for card in cards] == [spec.code for spec in BUILTIN_CARDS]
        assert all(card.card_type == "builtin" for card in cards)
        texts = (await session.execute(select(SysDashboardCardI18n))).scalars().all()
        assert len(texts) == len(BUILTIN_CARDS)
        assert {row.locale for row in texts} == {"en-US"}
        template = (
            await session.execute(select(SysDashboardTemplate).where(SysDashboardTemplate.scope == SCOPE_PLATFORM))
        ).scalars().first()
        assert template is not None
        assert template.name == PLATFORM_TEMPLATE_NAME
        layout = json.loads(template.layout_config)
        assert [item["code"] for item in layout["cards"]] == [spec.code for spec in BUILTIN_CARDS]


async def test_seed_is_idempotent_and_keeps_tenant_changes() -> None:
    """重跑：不新增行；租户停用的卡片保持停用、模板不被覆盖。"""
    async with memory_dashboard_session() as session:
        await seed_dashboard(session)
        await session.commit()
        card = (
            await session.execute(select(SysDashboardCard).where(SysDashboardCard.code == "todo"))
        ).scalars().first()
        assert card is not None
        card.status = "disabled"
        template = (await session.execute(select(SysDashboardTemplate))).scalars().first()
        assert template is not None
        template.name = "租户改名"
        await session.commit()

        again = await seed_dashboard(session)
        await session.commit()
        assert again == DashboardSeedOutcome()
        reloaded = (
            await session.execute(select(SysDashboardCard).where(SysDashboardCard.code == "todo"))
        ).scalars().first()
        assert reloaded is not None and reloaded.status == "disabled"
        kept = (await session.execute(select(SysDashboardTemplate))).scalars().first()
        assert kept is not None and kept.name == "租户改名"


async def test_seed_entry_delegates() -> None:
    """XA 分支入口只转发（不消费参数、不自行提交）。"""
    async with memory_dashboard_session() as session:
        await seed_dashboard_entry(session, ConcurrentStableDict({"ignored": True}))
        cards = await _cards(session)
        assert len(cards) == len(BUILTIN_CARDS)
