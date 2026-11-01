"""锁定管理端点用例（Kiwi 2211，03_07）。

覆盖：`GET /api/v1/account-locks`、`GET /api/v1/account-locks/{id}`、`POST /api/v1/account-locks`、
`PUT /api/v1/account-locks/{id}/unlock`；有效登录态放行（permission Null）；无效票据 401；`lock_type` 非法 10001；
手动锁定 → 账号被拒 → 解锁恢复的端到端链路。

单库叠加口径（04-6-2）：平台库与租户库都用共享库（不再建临时库）；用户主键由命名空间派生，
列表断言按 `user_id` 精确过滤。
"""

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.api.deps import get_uow
from bms_core.core.config import get_settings
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import AccountLockNotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.user import SysUser
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_platform.domains.user.repositories.user import UserRepository
from tests_support.permission_admin import assign_system_admin

API = "/api/v1/account-locks"

_TENANT_TABLES: tuple[Table, ...] = (
    cast("Table", SysRole.__table__),
    cast("Table", SysUserRole.__table__),
    cast("Table", SysIcon.__table__),
    cast("Table", SysIconI18n.__table__),
)
"""权限引擎读的租户库表（共享租户库幂等补齐）。"""


@pytest_asyncio.fixture(autouse=True)
async def permission_engine(
    shared_tenant_engine: AsyncEngine, shared_tenant_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """共享租户库（权限引擎读表幂等补齐）+ 内置系统管理员主体。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        shared_tenant_db_url: 共享租户库连接串。
        monkeypatch: 环境变量覆盖夹具。
    """
    await ensure_tables(shared_tenant_engine, list(_TENANT_TABLES))
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    get_settings.cache_clear()
    await assign_system_admin()
    get_settings.cache_clear()


def test_lock_error_code_registered() -> None:
    """错误码 `30007` 与异常子段登记（业务失败 HTTP 200）。"""
    assert ErrorCode.ACCOUNT_LOCK_NOT_FOUND == 30007
    error = AccountLockNotFoundError()
    assert error.code == 30007 and error.http_status == 200


async def _shared_app(
    engine: AsyncEngine, service_app: FastAPI, ns: Namespace
) -> tuple[async_sessionmaker[AsyncSession], int]:
    """共享平台库 + 每请求新会话的 `get_uow` 覆盖；播种一个命名空间用户。

    单库叠加口径：不再建临时库，表由 `ensure_tables` 幂等补齐；用户名带命名空间前缀，
    列表断言一律按 `user_id` 精确过滤，不看全表总数。

    Args:
        engine: 共享平台库引擎。
        service_app: 应用实例。
        ns: 用例命名空间。

    Returns:
        tuple[async_sessionmaker[AsyncSession], int]: (会话工厂, 用户主键)。
    """
    await ensure_tables(engine, [cast("Table", SysUser.__table__)])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seed = factory()
    try:
        user = await UserRepository(seed).create(username=ns.code("u"), password_hash="x", name="U")
        await seed.commit()
        user_id = user.id
    finally:
        await seed.close()

    async def override_uow() -> AsyncIterator[DbUnitOfWork]:
        # 镜像生产 `get_write_db` 的会话生命周期：响应后关闭会话，避免只读事务连接滞留至 GC（连接池告警）
        async with factory() as session:
            yield DbUnitOfWork(session)

    service_app.dependency_overrides[get_uow] = override_uow
    return factory, user_id


@pytest.mark.kiwi_id(2211)
async def test_lock_endpoints_flow(
    client: AsyncClient, service_app: FastAPI, shared_platform_engine: AsyncEngine, ns: Namespace
) -> None:
    """手动锁定 → 被锁 → 解锁恢复；列表 / 详情；非法筛选 10001。"""
    factory, user_id = await _shared_app(shared_platform_engine, service_app, ns)

    created = await client.post(API, json={"user_id": user_id, "reason": "违规处置"})
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["lock_type"] == "manual" and data["locked_by"] == "1001" and data["unlock_at"] is None

    check = factory()
    locked_until = (await UserRepository(check).get_by_id(user_id)).locked_until  # type: ignore[union-attr]
    await check.close()
    assert locked_until is not None

    listed = await client.get(API, params={"active": True, "user_id": user_id})
    assert listed.status_code == 200 and listed.json()["data"]["total"] == 1

    detailed = await client.get(f"{API}/{data['id']}")
    assert detailed.status_code == 200 and detailed.json()["data"]["id"] == data["id"]

    bad = await client.get(API, params={"lock_type": "bogus"})
    assert bad.status_code == 200 and bad.json()["code"] == 10001

    unlocked = await client.put(f"{API}/{data['id']}/unlock")
    assert unlocked.status_code == 200
    unlocked_data = unlocked.json()["data"]
    assert unlocked_data["unlock_mode"] == "manual" and unlocked_data["unlock_by"] == "1001"

    check = factory()
    restored = (await UserRepository(check).get_by_id(user_id)).locked_until  # type: ignore[union-attr]
    await check.close()
    assert restored is None

    missing = await client.put(f"{API}/9999/unlock")
    assert missing.status_code == 200 and missing.json()["code"] == 30007


@pytest.mark.kiwi_id(2211)
async def test_lock_endpoints_reject_invalid_token(
    client: AsyncClient, service_app: FastAPI, shared_platform_engine: AsyncEngine, ns: Namespace
) -> None:
    """无有效登录票据 → 401。"""
    await _shared_app(shared_platform_engine, service_app, ns)

    denied = await client.get(API, headers={"Authorization": "Bearer bogus"})
    assert denied.status_code == 401


@pytest.mark.kiwi_id(2211)
async def test_list_locks_empty_skips_user_batch(
    client: AsyncClient, service_app: FastAPI, shared_platform_engine: AsyncEngine, ns: Namespace
) -> None:
    """空清单：无锁定记录时用户批量取数短路（空集合直接返回空映射，不查用户表）。

    单库叠加口径：按本用例新建用户（无任何锁定记录）精确过滤，断言「该用户的清单为空」。
    """
    _, user_id = await _shared_app(shared_platform_engine, service_app, ns)

    listed = await client.get(API, params={"user_id": user_id})
    assert listed.status_code == 200
    assert listed.json()["data"] == {"list": [], "total": 0, "page": 1, "size": 20}
