"""账号锁定扫描端点用例（Kiwi 2209，03_05）：服务 JWT 白名单鉴权 + 扫描结果。

跑已装配系统 + 共享租户库（账号是租户数据，落在 `tenant_<code>` 库）：扫描是整表口径，库里
必有他人行，故断言取**相对增量**；服务令牌由测试助手用装配期注入的密钥签发、走真实校验，
不再替换鉴权实现，也不注入会话依赖。
"""

from datetime import datetime, timedelta
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.platform.user import SysUser
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_read, shared_write

API = "/api/v1/platform/internal/account-locks/scan-inactive"
_NOW = datetime(2026, 9, 27, 12, 0, 0)


async def _scan(
    client: AsyncClient, token: str, *, user_ids: ConcurrentStableList[int]
) -> ConcurrentStableDict[str, int]:
    """调用扫描端点并取 `data`（范围限定到本次造的账号，不触碰他人行）。

    Args:
        client: 装配态客户端。
        token: 服务 JWT。
        user_ids: 扫描范围（用户主键）。

    Returns:
        dict[str, int]: `{scanned, locked}`。
    """
    response = await client.post(API, json={"user_ids": list(user_ids)}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return ConcurrentStableDict(cast("dict[str, int]", response.json()["data"]))


@pytest.mark.kiwi_id(2209)
async def test_scan_endpoint_auth_and_result(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：白名单服务 JWT 放行并计入本次造的过期用户；网关 / 无票据 / 未知票据拒。"""
    identity = issue_service_token("identity")
    username = ns.code("never")
    async with shared_write(shared_tenant_engine) as session:
        user = await UserRepository(session).create(
            username=username, password_hash="x", name="never", last_login_at=None, status="enabled"
        )
        user_id = user.id
        await session.commit()
        # 扫描范围限定到本账号：端点默认全量，全量会锁住并行 worker 的过期账号
        scope = ConcurrentStableList([user_id])
        before = await _scan(client, identity, user_ids=scope)
        assert before["scanned"] == 0 and before["locked"] == 0
        # `created_at` 不在仓储可写白名单：显式 UPDATE 改成「长期未登录」
        await session.execute(
            update(SysUser).where(SysUser.id == user_id).values(created_at=_NOW - timedelta(days=200))
        )
        await session.commit()

    after = await _scan(client, identity, user_ids=scope)
    async with shared_read(shared_tenant_engine) as probe:
        own = (
            await probe.execute(select(func.count()).select_from(SysUser).where(SysUser.username == username))
        ).scalar_one()
    assert after["scanned"] == 1 and after["locked"] == 1, f"after={after} owner={own}"

    # 白名单只放行 identity / platform：gateway 是**合法签名的服务令牌**，仍须拒（覆盖白名单语义）
    gateway = issue_service_token("gateway")
    denied = await client.post(API, json={}, headers={"Authorization": f"Bearer {gateway}"})
    assert denied.status_code == 401

    for token in (None, "bogus"):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        assert (await client.post(API, json={}, headers=headers)).status_code == 401
