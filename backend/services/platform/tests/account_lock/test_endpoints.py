"""锁定管理端点用例（Kiwi 2211，03_07）。

覆盖：`GET /api/v1/account-locks`、`GET /api/v1/account-locks/{id}`、`POST /api/v1/account-locks`、
`PUT /api/v1/account-locks/{id}/unlock`；有效登录态放行（permission Null）；无效票据 401；`lock_type` 非法 10001；
手动锁定 → 账号被拒 → 解锁恢复的端到端链路。
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import AccountLockNotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository

API = "/api/v1/account-locks"


def test_lock_error_code_registered() -> None:
    """错误码 `30007` 与异常子段登记（业务失败 HTTP 200）。"""
    assert ErrorCode.ACCOUNT_LOCK_NOT_FOUND == 30007
    error = AccountLockNotFoundError()
    assert error.code == 30007 and error.http_status == 200


async def _file_app(tmp_path: Path, service_app: FastAPI) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession], int]:
    """建文件级 SQLite 库 + 每请求新会话的 `get_uow` 覆盖；播种一个用户。

    Args:
        tmp_path: pytest 临时目录。
        service_app: 应用实例。

    Returns:
        tuple[AsyncEngine, async_sessionmaker[AsyncSession], int]: (引擎, 会话工厂, 用户主键)。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'locks.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seed = factory()
    try:
        user = await UserRepository(seed).create(username="u", password_hash="x", name="U")
        await seed.commit()
        user_id = user.id
    finally:
        await seed.close()
    service_app.dependency_overrides[get_uow] = lambda: DbUnitOfWork(factory())
    return engine, factory, user_id


@pytest.mark.kiwi_id(2211)
async def test_lock_endpoints_flow(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """手动锁定 → 被锁 → 解锁恢复；列表 / 详情；非法筛选 10001。"""
    engine, factory, user_id = await _file_app(tmp_path, service_app)

    created = await client.post(API, json={"user_id": user_id, "reason": "违规处置"})
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["lock_type"] == "manual" and data["locked_by"] == 1001 and data["unlock_at"] is None

    check = factory()
    locked_until = (await UserRepository(check).get_by_id(user_id)).locked_until  # type: ignore[union-attr]
    await check.close()
    assert locked_until is not None

    listed = await client.get(API, params={"active": True})
    assert listed.status_code == 200 and listed.json()["data"]["total"] == 1

    detailed = await client.get(f"{API}/{data['id']}")
    assert detailed.status_code == 200 and detailed.json()["data"]["id"] == data["id"]

    bad = await client.get(API, params={"lock_type": "bogus"})
    assert bad.status_code == 200 and bad.json()["code"] == 10001

    unlocked = await client.put(f"{API}/{data['id']}/unlock")
    assert unlocked.status_code == 200
    unlocked_data = unlocked.json()["data"]
    assert unlocked_data["unlock_mode"] == "manual" and unlocked_data["unlock_by"] == 1001

    check = factory()
    restored = (await UserRepository(check).get_by_id(user_id)).locked_until  # type: ignore[union-attr]
    await check.close()
    assert restored is None

    missing = await client.put(f"{API}/9999/unlock")
    assert missing.status_code == 200 and missing.json()["code"] == 30007

    await engine.dispose()


@pytest.mark.kiwi_id(2211)
async def test_lock_endpoints_reject_invalid_token(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """无有效登录票据 → 401。"""
    engine, _, _ = await _file_app(tmp_path, service_app)

    denied = await client.get(API, headers={"Authorization": "Bearer bogus"})
    assert denied.status_code == 401

    await engine.dispose()
