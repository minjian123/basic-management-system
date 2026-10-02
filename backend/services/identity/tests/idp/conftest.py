"""外部 IdP 配置管理面测试夹具（Kiwi 2203）：表结构兜底 + 探测替身 + 限流内存实现。"""

from __future__ import annotations

import functools
import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Table, delete

from bms_core.api.deps import get_rate_limiter
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_identity.api import identity_providers as idp_api
from bms_identity.models.identity_provider import SysIdentityProvider
from bms_identity.services.provider_registry import ProviderRegistry

TENANT_HEADERS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"X-Tenant-ID": "demo"})
TENANT_ID = "1001"
ISSUER = "https://idp.example.com/realms/bms"
CAS_SERVER = "https://cas.example.com/cas"


class ProbeMock:
    """可控 IdP 探测替身（按路径分派四协议响应）。"""

    def __init__(self) -> None:
        """初始化（默认四协议均可达）。"""
        self.oidc_status = 200
        self.oidc_document: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
            }
        )
        self.cas_status = 200
        self.wecom_errcode = 0
        self.dingtalk_status = 400

    def handle(self, request: httpx.Request) -> httpx.Response:
        """MockTransport 处理函数。

        Args:
            request: 出站请求。

        Returns:
            httpx.Response: 模拟响应。
        """
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(self.oidc_status, json=dict(self.oidc_document))
        if path.endswith("/p3/serviceValidate"):
            return httpx.Response(self.cas_status, content=b"<xml/>")
        if path.endswith("/cgi-bin/gettoken"):
            return httpx.Response(200, json={"errcode": self.wecom_errcode, "access_token": "t"})
        if path.endswith("/v1.0/oauth2/userAccessToken"):
            return httpx.Response(self.dingtalk_status, json={"code": "x"})
        return httpx.Response(404, json={})


@dataclass
class ManageHarness:
    """管理面装配套件。"""

    app: FastAPI
    probe: ProbeMock = field(default_factory=ProbeMock)
    limiter: MemoryRateLimiter = field(default_factory=MemoryRateLimiter)

    def tenant_scope(self) -> AbstractAsyncContextManager[DbSession]:
        """演示租户库会话上下文。

        Returns:
            AbstractAsyncContextManager[DbSession]: 会话上下文。
        """
        return session_scope(
            self.app.state.engine_registry,
            db_key=DEMO_TENANT.db_key,
            factory=self.app.state.session_factory,
        )

    async def seed_provider(
        self,
        *,
        idp_key: str = "keycloak",
        type: str = "oidc",
        status: str = "enabled",
        sort: int = 0,
        config: ConcurrentStableDict[str, object] | None = None,
        raw_config: str | None = None,
        name: str = "Keycloak",
    ) -> None:
        """播种一条 IdP 行（可传非法原文以覆盖存量脏配置分支）。

        Args:
            idp_key: 标识。
            type: 协议类型。
            status: 状态。
            sort: 排序。
            config: 行配置对象。
            raw_config: 行配置原文（优先于 config）。
            name: 显示名。
        """
        payload = self._oidc_config() if config is None else config
        raw = raw_config if raw_config is not None else json.dumps(dict(payload), ensure_ascii=False)
        async with self.tenant_scope() as session:
            session.add(
                SysIdentityProvider(
                    name=name, idp_key=idp_key, type=type, icon="", config=raw, status=status, sort=sort
                )
            )
            await session.commit()

    def _oidc_config(self) -> ConcurrentStableDict[str, object]:
        """OIDC 行配置（指向探测替身）。"""
        return ConcurrentStableDict(
            {
                "issuer": ISSUER,
                "client_id": "bms-backend",
                "client_secret_ref": "env:MANAGE_TEST_SECRET",
                "redirect_uri": "https://app.example.com/api/v1/auth/sso/keycloak/callback",
            }
        )


async def _ensure_schema(app: FastAPI) -> None:
    """兜底建表（租户库 `sys_identity_provider`）。

    Args:
        app: 应用实例。
    """
    tenant_engine = await app.state.engine_registry.get(DEMO_TENANT.db_key)
    async with tenant_engine.begin() as conn:
        await conn.run_sync(cast("Table", SysIdentityProvider.__table__).create, checkfirst=True)


async def _clean_rows(app: FastAPI) -> None:
    """清空 IdP 配置行。

    Args:
        app: 应用实例。
    """
    async with session_scope(
        app.state.engine_registry, db_key=DEMO_TENANT.db_key, factory=app.state.session_factory
    ) as session:
        await session.execute(delete(SysIdentityProvider))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_manage(service_app: FastAPI) -> AsyncIterator[None]:
    """用例前后清空 IdP 配置表并兜底建表。

    Args:
        service_app: 应用实例。

    Yields:
        None: 用例运行期。
    """
    await _ensure_schema(service_app)
    await _clean_rows(service_app)
    yield
    await _clean_rows(service_app)


@pytest.fixture
def manage(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> ManageHarness:
    """装配管理面替身（限流内存实现 + 探测 MockTransport + 密钥环境变量）。

    Args:
        service_app: 应用实例。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        ManageHarness: 装配套件。
    """
    limiter = MemoryRateLimiter()
    probe = ProbeMock()
    service_app.dependency_overrides[get_rate_limiter] = lambda: limiter
    monkeypatch.setenv("MANAGE_TEST_SECRET", "s3cr3t")
    monkeypatch.setattr(
        idp_api,
        "ProviderRegistry",
        functools.partial(ProviderRegistry, transport=httpx.MockTransport(probe.handle)),
    )
    return ManageHarness(app=service_app, probe=probe, limiter=limiter)


__all__ = ["CAS_SERVER", "ISSUER", "TENANT_HEADERS", "ManageHarness", "ProbeMock"]
