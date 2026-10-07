"""账号锁定扫描端点用例（Kiwi 2209，03_05）：服务 JWT 白名单鉴权 + 扫描结果。

覆盖：`sub=identity` / `sub=platform` 放行；无票据 / 网关票据 / 未知票据 401；命中返回 `{scanned, locked}`。
"""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository

API = "/api/v1/platform/internal/account-locks/scan-inactive"
_NOW = datetime(2026, 9, 27, 12, 0, 0)


class _StubVerifier:
    """测试替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001/401）。
        """
        if token in {"identity", "platform"}:
            return VerifiedToken(subject=token, service=token, token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        raise AuthError("invalid")


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话（含 `sys_user` + `sys_account_lock`）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


@pytest.mark.kiwi_id(2209)
async def test_scan_endpoint_auth_and_result(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：白名单服务 JWT 放行并返回扫描结果；网关 / 无票据 / 未知票据拒。"""
    session, engine = await _session()
    user = await UserRepository(session).create(
        username="never", password_hash="x", name="never", last_login_at=None, status="enabled"
    )
    user.created_at = _NOW - timedelta(days=200)
    await session.commit()

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_uow] = lambda: DbUnitOfWork(session)

    first = await client.post(API, json={}, headers={"Authorization": "Bearer identity"})
    assert first.status_code == 200 and first.json()["data"] == {"scanned": 1, "locked": 1}

    second = await client.post(API, json={}, headers={"Authorization": "Bearer platform"})
    assert second.status_code == 200 and second.json()["data"] == {"scanned": 0, "locked": 0}

    for token in (None, "gateway", "bogus"):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        denied = await client.post(API, json={}, headers=headers)
        assert denied.status_code == 401

    await session.close()
    await engine.dispose()
