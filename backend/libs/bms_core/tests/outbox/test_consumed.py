"""消费幂等用例（Kiwi 2173）：首次标记 / 重复跳过 / 与副作用同事务 / 回滚一并撤销。

测试库：临时 SQLite（建发件箱三表）。每次数据库交互均显式事务。
"""

import pytest
from sqlalchemy import func, select

from bms_core.db.sync import DbSession
from bms_core.models.outbox import SysEventConsumed
from bms_core.outbox.consumed import ProcessedEventStore


async def _count(session: DbSession) -> int:
    """已处理事件计数（显式事务）。"""
    async with session.begin():
        return int((await session.execute(select(func.count()).select_from(SysEventConsumed))).scalar_one())


@pytest.mark.kiwi_id(2173)
async def test_mark_idempotent(session: DbSession) -> None:
    """首次 True、重复 False；重复不影响外层事务，可与副作用同事务提交。"""
    store = ProcessedEventStore(session)
    async with session.begin():
        assert await store.mark(consumer="indexer", event_id="evt-1", event_type="sys.user.updated") is True
        # 重复：命中唯一键返回 False，且不破坏外层事务
        assert await store.mark(consumer="indexer", event_id="evt-1") is False
        assert await store.mark(consumer="indexer", event_id="evt-2") is True

    assert await _count(session) == 2

    # 不同消费者对同一事件各自首次
    async with session.begin():
        assert await store.mark(consumer="notifier", event_id="evt-1") is True
    assert await _count(session) == 3


@pytest.mark.kiwi_id(2173)
async def test_mark_rolls_back_with_business(session: DbSession) -> None:
    """业务副作用回滚时，幂等登记随之回滚（下次可重处理）。"""
    store = ProcessedEventStore(session)
    with pytest.raises(RuntimeError):
        async with session.begin():
            assert await store.mark(consumer="indexer", event_id="evt-9") is True
            raise RuntimeError("副作用失败")

    assert await _count(session) == 0
    async with session.begin():
        assert await store.mark(consumer="indexer", event_id="evt-9") is True
