"""会话记录仓储测试（Kiwi 2194）：创建 / 取数 / 轮换哈希 / 撤销（含未命中分支）。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_identity.models.session import SysSession
from bms_identity.repositories.session import SessionRepository


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话（含 `sys_session` 表）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysSession.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


@pytest.mark.kiwi_id(2194)
async def test_session_repository_roundtrip() -> None:
    """仓储：创建（id = 会话 id）/ 按会话 id 取数 / 轮换哈希 / 撤销（含未命中）。"""
    session, engine = await _session()
    repo = SessionRepository(session)
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC).replace(tzinfo=None)
    created = await repo.create_session(
        session_id="1000000000000000001",
        user_id=1,
        refresh_token_hash="h1",
        login_at=now,
        expires_at=now + timedelta(days=14),
        device="ua",
        ip="127.0.0.1",
    )
    await session.commit()
    assert created.id == 1000000000000000001 and created.session_id == "1000000000000000001"

    fetched = await repo.get_by_session_id("1000000000000000001")
    assert fetched is not None and fetched.user_id == 1

    rotated = await repo.update_refresh_hash("1000000000000000001", "h2")
    assert rotated is not None and rotated.refresh_token_hash == "h2"
    assert await repo.update_refresh_hash("missing", "h3") is None

    assert await repo.revoke("1000000000000000001", revoked_at=now) is True
    assert await repo.revoke("1000000000000000001", revoked_at=now) is True  # 已撤销：幂等跳过更新
    assert await repo.revoke("missing", revoked_at=now) is False
    await session.rollback()
    await engine.dispose()
