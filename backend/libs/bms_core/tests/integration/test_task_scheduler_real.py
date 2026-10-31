"""任务调度端到端集成用例：真 Redis + 真库，双 beat 并发只派发一次。

前置（未就绪自动跳过，CI 不受影响）：

```bash
export BMS_REDIS__URL=redis://192.168.0.107:6379/0
uv run pytest libs/bms_core/tests/integration/test_task_scheduler_real.py -v
```

覆盖《详细设计 · 任务调度》§4.3「关键点 1」的实证：

1. 两个 beat（各持**真分布式锁**）并发 `tick`，同一条到期任务只被派发一次——
   锁在真 Redis 上互斥、`next_run_at` 条件 UPDATE 在真库上做 CAS，两条防线同时生效；
2. 库里只有一条 `running` 执行记录、队列里只有一个载荷；
3. 串行第二次 `tick` 不再派发（`next_run_at` 已推进）。

库用临时 SQLite（真库引擎、真事务），Redis 用开发服务器实例（真锁、真队列）。
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import cast

import pytest
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import TaskSchedulerSettings
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.lock.redis import RedisDistributedLock
from bms_core.models.base import Base
from bms_core.models.platform.task import TASK_RUN_RUNNING, SysTask, SysTaskLog
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.scheduler import TaskScheduler

pytestmark = pytest.mark.kiwi_id(2371)

_REAL_REDIS_URL = os.environ.get("BMS_REDIS__URL", "")
"""真 Redis 连接串：**导入时**读取（autouse 的设置隔离夹具会清 `BMS_*` 环境变量）。"""


def _redis_url() -> str:
    """取真 Redis 连接串（未配置则跳过用例）。

    Returns:
        str: 连接串。
    """
    url = _REAL_REDIS_URL
    if not url:
        pytest.skip("未配置 BMS_REDIS__URL（真 Redis 集成用例跳过）")
    return url


async def _probe(url: str) -> AsyncRedis:
    """连接并探活。

    Args:
        url: 连接串。

    Returns:
        AsyncRedis: 可用客户端。

    Raises:
        pytest.skip: 连不上（本机无该 Redis）。
    """
    client = cast("AsyncRedis", AsyncRedis.from_url(url, decode_responses=False))
    try:
        await client.ping()
    except Exception as exc:  # 环境不可用时跳过，不让 CI 红
        await client.aclose()
        pytest.skip(f"真 Redis 不可达，跳过：{exc}")
    return client


async def test_two_beats_dispatch_once(tmp_path) -> None:
    """双 beat 并发：真锁互斥 + 条件 UPDATE CAS，只派发一次。"""
    url = _redis_url()
    client = await _probe(url)
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'task_real.db'}"
    engine = create_async_engine(db_url)
    task_tables: ConcurrentStableList[Table] = ConcurrentStableList(
        [cast("Table", SysTask.__table__), cast("Table", SysTaskLog.__table__)]
    )
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(task_tables)))
    await engine.dispose()

    os.environ["BMS_DATABASE__PLATFORM__URL"] = db_url
    from bms_core.core.config import get_settings

    get_settings.cache_clear()
    settings = TaskSchedulerSettings(poll_interval_seconds=1, lock_ttl_seconds=5, run_timeout_seconds=600)
    queue = TaskQueue(client=client, key="bms:global:task:queue:it-beat")
    await client.delete(queue.key)
    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO sys_task (id, form_key, code, name, handler, cron, status, enabled,"
                    " next_run_at, created_at, updated_at, version)"
                    " VALUES (1, 'task', 'it_task', 'it_task',"
                    " 'bms_core.tasks.builtin:run_cleanup_orphan_parts', '* * * * *', 'enabled', 1,"
                    " NULL, :now, :now, 1)"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None)},
            )
        schedulers = [
            TaskScheduler(
                settings=settings,
                registry=registry,
                queue=queue,
                lock=RedisDistributedLock(client=client),
                tenant_keys=_tenant_keys(),
                session_factory=SessionFactory(),
            )
            for _ in range(2)
        ]
        reports = await asyncio.gather(*(item.tick() for item in schedulers))
        async with engine.begin() as connection:
            logs = (await connection.execute(text("SELECT COUNT(*) FROM sys_task_log"))).scalar_one()
        assert logs == 1, f"双 beat 重复派发：{logs} 条记录；报告={reports}"
        depth = await client.llen(queue.key)
        assert depth == 1, f"队列深度 {depth}；报告={reports}"
        again = await schedulers[0].tick()
        assert again.dispatched == 0
        async with engine.begin() as connection:
            status = (await connection.execute(text("SELECT status FROM sys_task_log"))).scalar_one()
        assert status == TASK_RUN_RUNNING
    finally:
        await client.delete(queue.key)
        await client.aclose()
        await registry.aclose()
        get_settings.cache_clear()


def _tenant_keys():
    """固定单租户库键提供者（平台库即“租户库”）。

    Returns:
        object: 异步可调用对象。
    """

    async def _provider() -> ConcurrentStableList[str]:
        return ConcurrentStableList([PLATFORM_DB_KEY])

    return _provider


async def test_queue_round_trip_on_real_redis() -> None:
    """真 Redis 上入队 / 出队保真（载荷编解码不依赖替身）。"""
    client = await _probe(_redis_url())
    queue = TaskQueue(client=client, key="bms:global:task:queue:it-roundtrip")
    await client.delete(queue.key)
    try:
        from bms_core.tasks.spec import TaskRunSpec

        spec = TaskRunSpec(
            db_key=PLATFORM_DB_KEY,
            task_id=7,
            log_id=8,
            run_id="run-real",
            code="it_task",
            handler="bms_core.tasks.builtin:run_cleanup_orphan_parts",
        )
        await queue.push(spec)
        outcome = await queue.pop(timeout=2)
        assert outcome.spec == spec
    finally:
        await client.delete(queue.key)
        await client.aclose()
