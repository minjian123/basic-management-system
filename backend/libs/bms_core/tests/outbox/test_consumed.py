"""消费幂等用例（Kiwi 2173）：首次标记 / 重复跳过 / 与副作用同事务 / 落库口径（测试库 autocommit）。

测试库：临时 SQLite（建发件箱三表）。登记写入即落库；「业务失败随事务回滚」由三库集成层验证。
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
async def test_mark_persists_under_test_autocommit(session: DbSession) -> None:
    """业务异常后登记**仍已落库**：SQLite 测试库是操作级 autocommit，回滚不再撤销写入。

    为什么不再断言「回滚撤销」：2026-11-22 业主口径确定测试库写入即落库（DBAPI
    `isolation_level=None` + 操作级写门），这是并行下唯一能压住 `database is locked` 的口径。
    「业务失败 → 幂等登记随事务回滚」是**正式数据库**（MySQL / PostgreSQL / 达梦）的语义，
    由三库集成层验证；本地只锁住「登记已生效、重复处理被挡住」这一面。
    """
    store = ProcessedEventStore(session)
    with pytest.raises(RuntimeError):
        async with session.begin():
            assert await store.mark(consumer="indexer", event_id="evt-9") is True
            raise RuntimeError("副作用失败")

    assert await _count(session) == 1
    async with session.begin():
        # 登记已生效：同一事件不再被重复处理（幂等面在测试口径下依然成立）
        assert await store.mark(consumer="indexer", event_id="evt-9") is False
