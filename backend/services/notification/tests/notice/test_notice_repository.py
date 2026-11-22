"""公告仓储（Kiwi 2518）：分页 / 筛选 / 置顶排序 / 回执 / 统计 / 过期扫描。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.models.notice import SysNotice, SysNoticeRead
from bms_notification.domains.notification.notice_constants import (
    NOTICE_STATUS_DRAFT,
    NOTICE_STATUS_OFFLINE,
)
from bms_notification.domains.notification.repositories.notice import NoticeRepository
from notice._support import add_notice, add_receipt, set_updated_at, utc_now

pytestmark = pytest.mark.kiwi_id(2518)


def _own(ns: Namespace) -> str:
    """本用例的标题前缀（造数、查询与断言都以此为准）。

    Args:
        ns: 用例命名空间。

    Returns:
        str: `{prefix}-`。
    """
    return f"{ns.prefix}-"


async def test_page_published_visibility_and_sort(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """公开列表只含发布中且未过期；置顶按更新时间、非置顶按发布时间（只认本用例前缀的行）。"""
    own = _own(ns)
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        pinned_old = add_notice(session, title=f"{own}置顶旧", is_top=True)
        pinned_new = add_notice(session, title=f"{own}置顶新", is_top=True)
        normal_old = add_notice(session, title=f"{own}普通旧", publish_at=now - timedelta(days=2))
        normal_new = add_notice(session, title=f"{own}普通新", publish_at=now - timedelta(hours=2))
        add_notice(session, title=f"{own}草稿", status=NOTICE_STATUS_DRAFT)
        add_notice(session, title=f"{own}已过期", expire_at=now - timedelta(minutes=1))
        await session.flush()
        await set_updated_at(session, int(pinned_old.id), now - timedelta(hours=5))
        await set_updated_at(session, int(pinned_new.id), now - timedelta(hours=1))
        repo = NoticeRepository(session)
        rows, total = await repo.page_published(page=1, size=1000, now=now)
        assert total >= 4
        assert [row.title for row in rows if row.title.startswith(own)] == [
            f"{own}置顶新",
            f"{own}置顶旧",
            f"{own}普通新",
            f"{own}普通旧",
        ]
        assert normal_old.id and normal_new.id


async def test_page_manage_filters(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """管理列表：状态 / 类型 / 关键字 / 普通用户可见性（按本用例前缀收口）。"""
    own = _own(ns)
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        add_notice(session, title=f"{own}Alpha 公告", notice_type="policy")
        add_notice(session, title=f"{own}Beta 公告", status=NOTICE_STATUS_DRAFT)
        add_notice(session, title=f"{own}Gamma 公告", expire_at=now - timedelta(minutes=1))
        await session.flush()
        repo = NoticeRepository(session)
        rows, total = await repo.page_manage(page=1, size=100, now=now, keyword=own)
        assert total == 3
        rows, total = await repo.page_manage(page=1, size=100, now=now, keyword=own, status=NOTICE_STATUS_DRAFT)
        assert total == 1 and rows[0].title == f"{own}Beta 公告"
        rows, total = await repo.page_manage(page=1, size=100, now=now, keyword=own, notice_type="policy")
        assert total == 1 and rows[0].title == f"{own}Alpha 公告"
        rows, total = await repo.page_manage(page=1, size=100, now=now, keyword=f"{own}Gamma")
        assert total == 1
        rows, total = await repo.page_manage(page=1, size=100, now=now, keyword=own, visible_only=True)
        assert total == 1 and rows[0].title == f"{own}Alpha 公告"
        rows, total = await repo.page_manage(page=2, size=10, now=now, keyword=own)
        assert total == 3 and rows == ConcurrentStableList()


async def test_receipts_and_read_count(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """回执按公告 + 用户取；已读人数去重。"""
    async with write_session(shared_tenant_engine) as session:
        notice = add_notice(session, title=f"{_own(ns)}回执")
        await session.flush()
        repo = NoticeRepository(session)
        assert await repo.get_receipt(int(notice.id), 1) is None
        assert await repo.read_ids(1, ConcurrentStableList()) == set()
        add_receipt(session, notice_id=int(notice.id), user_id=1)
        add_receipt(session, notice_id=int(notice.id), user_id=2)
        await session.flush()
        assert await repo.get_receipt(int(notice.id), 1) is not None
        assert await repo.read_count(int(notice.id)) == 2
        assert await repo.read_ids(1, ConcurrentStableList([int(notice.id)])) == {int(notice.id)}
        assert await repo.read_ids(3, ConcurrentStableList([int(notice.id)])) == set()


@pytest.mark.xdist_group("notice-expire")
async def test_expired_and_mark_offline(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """过期扫描只取发布中到期行；乐观锁冲突返回 False（只认本用例前缀的行）。"""
    own = _own(ns)
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        expired = add_notice(session, title=f"{own}到期", expire_at=now - timedelta(seconds=1))
        add_notice(session, title=f"{own}未到期", expire_at=now + timedelta(hours=1))
        add_notice(session, title=f"{own}无过期")
        await session.flush()
        repo = NoticeRepository(session)
        rows = await repo.expired(now=now, limit=1000)
        assert [row.title for row in rows if row.title.startswith(own)] == [f"{own}到期"]
        assert await repo.mark_offline(expired) is True
        assert expired.status == NOTICE_STATUS_OFFLINE
        await session.flush()
        rows = await repo.expired(now=now, limit=1000)
        assert [row.title for row in rows if row.title.startswith(own)] == []

        stale = add_notice(session, title=f"{own}并发", expire_at=now - timedelta(seconds=1))
        await session.flush()
        await session.execute(
            update(SysNotice)
            .where(SysNotice.id == stale.id)
            .values(version=999)
            .execution_options(synchronize_session=False)
        )
        assert await repo.mark_offline(stale) is False


async def test_get_any_and_receipt_ordering(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """按主键取（含草稿）；多回执取最新活行；总数口径。"""
    async with write_session(shared_tenant_engine) as session:
        draft = add_notice(session, title=f"{_own(ns)}草稿", status=NOTICE_STATUS_DRAFT)
        await session.flush()
        repo = NoticeRepository(session)
        assert await repo.get_any(int(draft.id)) is not None
        assert await repo.get_any(999999) is None

        old = add_receipt(session, notice_id=int(draft.id), user_id=7, read_at=utc_now() - timedelta(days=1))
        await session.flush()
        old.soft_delete()
        new = add_receipt(session, notice_id=int(draft.id), user_id=7, read_at=utc_now())
        await session.flush()
        # 软删旧行后同人可重建；取活行最新 id
        receipt = await repo.get_receipt(int(draft.id), 7)
        assert receipt is not None
        assert receipt.id == new.id
        assert old.id != new.id

        total = (
            await session.execute(
                select(func.count()).select_from(SysNoticeRead).where(SysNoticeRead.notice_id == int(draft.id))
            )
        ).scalar_one()
        assert total == 2
