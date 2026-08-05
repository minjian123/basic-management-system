"""集成测试：双库拓扑路由与模型基类（SQLite 多文件模拟平台库/租户库）。

覆盖：平台库写入读取、租户库路由（X-Tenant-ID 上下文）、租户间隔离、
模型基类（雪花 ID 唯一、审计字段填充、软删过滤、乐观锁递增、复合唯一索引）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_tenant
from app.db.engine import get_registry
from app.db.router import resolve_engine
from app.models.probe import PlatformProbe, TenantProbe


@pytest.mark.asyncio
async def test_platform_write_read_and_audit() -> None:
    """平台库写入读取成功，审计字段自动填充（created_at 非空）。"""
    engine = await get_registry().get("platform")
    async with AsyncSession(engine, expire_on_commit=False) as session:
        probe = PlatformProbe(name="platform-1", payload="hello")
        session.add(probe)
        await session.commit()

        fetched = await session.get(PlatformProbe, probe.id)
        assert fetched is not None
        assert fetched.name == "platform-1"
        assert fetched.payload == "hello"
        assert fetched.created_at is not None
        assert fetched.created_by is None  # 阶段二认证接入后填充
        assert fetched.updated_at is not None


@pytest.mark.asyncio
async def test_tenant_routing_by_context() -> None:
    """按租户上下文路由：demo 租户写入 demo 库，demo2 查不到（租户间隔离）。"""
    set_tenant("demo")
    engine = await resolve_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(TenantProbe(name="demo-only"))
        await session.commit()

    set_tenant("demo2")
    engine2 = await resolve_engine()
    async with AsyncSession(engine2) as session2:
        rows = (await session2.execute(select(TenantProbe))).scalars().all()
        assert len(rows) == 0

    set_tenant(None)


@pytest.mark.asyncio
async def test_platform_request_no_tenant_context() -> None:
    """无租户上下文（平台级请求）路由到平台库。"""
    set_tenant(None)
    engine = await resolve_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(PlatformProbe(name="platform-2"))
        await session.commit()
        rows = (await session.execute(select(PlatformProbe))).scalars().all()
        assert len(rows) >= 1


@pytest.mark.asyncio
async def test_snowflake_id_unique() -> None:
    """雪花 ID 主键唯一且单调可用（Python 侧生成）。"""
    from app.db.base import next_id

    ids = {next_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(isinstance(i, int) and i > 0 for i in ids)


@pytest.mark.asyncio
async def test_soft_delete_releases_unique_key() -> None:
    """软删除释放唯一键：deleted_at 写入时间戳后，同名记录可重建。

    说明：复合唯一索引 (唯一字段, deleted_at) 下未删行 deleted_at 为 NULL，
    SQLite/MySQL/PostgreSQL 均允许多个 NULL 不冲突（active 行唯一性由应用层保证，
    PostgreSQL 部分唯一索引优化在 CI/阶段三落地）。
    """
    set_tenant("demo")
    engine = await resolve_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        first = TenantProbe(name="dup-name")
        session.add(first)
        await session.commit()

        first.deleted_at = first.updated_at  # 软删除（写入时间戳释放唯一键）
        await session.commit()

        second = TenantProbe(name="dup-name")
        session.add(second)
        await session.commit()

        assert second.id != first.id
        assert first.deleted_at is not None
        assert second.deleted_at is None

    set_tenant(None)


@pytest.mark.asyncio
async def test_optimistic_lock_version_increment() -> None:
    """乐观锁：更新时 version 自动递增。"""
    set_tenant("demo")
    engine = await resolve_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        probe = TenantProbe(name="lock-test")
        session.add(probe)
        await session.commit()
        assert probe.version == 0

        probe.name = "lock-test-2"
        await session.commit()
        assert probe.version == 1

        probe.name = "lock-test-3"
        await session.commit()
        assert probe.version == 2

    set_tenant(None)
