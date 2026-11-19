"""菜单元数据测试替身（Kiwi 2242）：直插业务 / 动作码与表单、发件箱读取。

业务 / 动作权限码无写接口（平台只读口径），用例内直插以构造授权对象。

单库化（04-6-2）后菜单元数据落**共享平台库**、全 worker 叠加：业务码 / 表单 / 菜单一律由调用方
按用例命名空间派生；动作码是全局动词（`create` / `query` 等固定词），「查无 → 插入」必须跨进程
串行（`(code, deleted_at)` 唯一约束在 NULL 上不生效，见 `tests_support/locks.py`）。

**本模块不提供清场**（2026-11-18 修订）：原 `reset_menu_tables()` 逐例清空菜单元数据十二表，
在单库叠加下会删掉并行中他人用例正在断言的业务码 / 表单（与 `services/identity/tests/auth`
取消 `delete(SysSession)` 同一理由）。该函数自 04-6-2 收口后已无调用者，本次一并删除；
隔离一律靠调用方按 `ns` 派生业务码。
"""

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.menu_form import SysForm, SysMenuForm
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.testing.gates import PLATFORM_GATE, gate_scope


def platform_url() -> str:
    """当前用例的平台库连接串（由平台服务 conftest 的 `platform_db` 夹具注入）。

    Returns:
        str: 平台库连接串。
    """
    return os.environ["BMS_DATABASE__PLATFORM__URL"]


async def seed_business(code: str, name: str = "测试业务") -> int:
    """直插业务权限码。

    Args:
        code: 业务码。
        name: 名称。

    Returns:
        int: 业务码主键。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysBusiness(code=code, name=name, status="enabled")
            session.add(row)
            await session.flush()
            business_id = row.id
            await session.commit()
        return business_id
    finally:
        await engine.dispose()


async def set_business_status(business_id: int, status: str) -> None:
    """改业务码状态（构造挂接链断裂 / 停用场景）。

    Args:
        business_id: 业务码主键。
        status: 目标状态。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (await session.execute(select(SysBusiness).where(SysBusiness.id == business_id))).scalars().first()
            if row is not None:
                row.status = status
            await session.commit()
    finally:
        await engine.dispose()


async def seed_permission(business_id: int, action_code: str = "query", name: str = "查询") -> int:
    """直插权限码（业务码 × 动作码组合）：全局动作码缺则建，再建权限码。

    Args:
        business_id: 业务码主键。
        action_code: 动作码（全局动词）。
        name: 动作名（新建动作码时使用）。

    Returns:
        int: 权限码主键。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # 动作码是全局动词（`create` / `query` …），共享库上多个 worker 会同时走到「查无 → 插入」：
        # `(code, deleted_at)` 唯一约束在 NULL 上不生效，不串行就会各写一行同码动作。
        # 13_08 起用平台库写门（跨进程独占，取放 0.003ms、不留残锁）代替同名文件锁。
        async with gate_scope(PLATFORM_GATE, read_only=False), factory() as session:
            action = (
                (
                    await session.execute(
                        select(SysAction).where(SysAction.code == action_code, SysAction.deleted_at.is_(None))
                    )
                )
                .scalars()
                .first()
            )
            if action is None:
                action = SysAction(code=action_code, name=name, status="enabled")
                session.add(action)
                await session.flush()
            permission = SysPermission(business_id=business_id, action_id=action.id, status="enabled")
            session.add(permission)
            await session.flush()
            permission_id = permission.id
            await session.commit()
        return permission_id
    finally:
        await engine.dispose()


async def insert_form(menu_id: int, business_id: int, status: str = "enabled") -> int:
    """直插表单并关联菜单入口（绕过接口校验，用于构造断裂 / 停用场景）。

    Args:
        menu_id: 菜单主键。
        business_id: 业务码主键。
        status: 表单状态。

    Returns:
        int: 表单主键。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysForm(business_id=business_id, component=None, status=status)
            session.add(row)
            await session.flush()
            form_id = row.id
            session.add(SysMenuForm(menu_id=menu_id, form_id=form_id))
            await session.flush()
            await session.commit()
        return form_id
    finally:
        await engine.dispose()


async def outbox_types(aggregate_key: str) -> list[str]:
    """取指定聚合键的发件箱事件类型清单。

    Args:
        aggregate_key: 聚合 / 分区键。

    Returns:
        list[str]: 事件类型清单。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysOutbox.event_type).where(SysOutbox.aggregate_key == aggregate_key)
            rows = (await session.execute(statement)).scalars().all()
        return [str(item) for item in rows]
    finally:
        await engine.dispose()


async def outbox_payloads(event_type: str) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """取指定事件类型的发件箱负载清单（插入序）。

    Args:
        event_type: 事件类型（如 `sys.data.changed`）。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 事件负载（插入序）。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysOutbox.payload).where(SysOutbox.event_type == event_type)
            payloads = (await session.execute(statement)).scalars().all()
    finally:
        await engine.dispose()
    result: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for payload in payloads:
        result.add(ConcurrentStableDict(payload))
    return result
