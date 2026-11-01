"""OIDC Provider 端点测试夹具（Kiwi 2202）：替身装配 + 客户端播种 + 表结构兜底。

单库叠加口径（04-6-2）：`sys_client` 落共享租户库，客户端标识 / 本地用户主键按用例命名空间派生
（`OidcHarness.client_id` / `user_id`）；**不再逐例整表清空**（并行下会删掉他人用例的客户端行）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Table, select, update

from bms_core.api.deps import get_idp_state_store, get_service_client
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_core.models.identity.client import SysClient
from bms_core.testing.namespace import Namespace

from .helpers import CLIENT_SECRET, REDIRECT_URI, FakeOidcPlatformClient


@dataclass
class OidcHarness:
    """OIDC 用例装配套件：替身、流程状态存储与播种工具。"""

    app: FastAPI
    states: MemoryIdpStateStore
    platform_client: FakeOidcPlatformClient
    client_id: str
    namespace_prefix: str

    def extra_client_id(self, suffix: str) -> str:
        """本用例的附加客户端标识（同一用例内需要多个客户端时用）。

        Args:
            suffix: 业务后缀（如 `cc-only`）。

        Returns:
            str: 带命名空间前缀的客户端标识。
        """
        return f"{self.namespace_prefix}-{suffix}"

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

    async def seed_client(
        self,
        *,
        client_id: str | None = None,
        secret: str = CLIENT_SECRET,
        public: bool = False,
        redirect_uris: ConcurrentStableList[str] | None = None,
        grant_types: ConcurrentStableList[str] | None = None,
        scopes: ConcurrentStableList[str] | None = None,
        status: str = "enabled",
        name: str = "Demo Client",
    ) -> SysClient:
        """播种一条客户端行（secret 经应用装配哈希器哈希）。

        Args:
            client_id: 客户端标识（None 取本用例派生标识）。
            secret: 明文密钥（public=True 忽略）。
            public: 是否公共客户端（不存密钥哈希）。
            redirect_uris: 回调地址白名单。
            grant_types: 授权类型。
            scopes: scope 集合。
            status: 状态。
            name: 应用名称。

        Returns:
            SysClient: 新建客户端行。
        """
        hasher = self.app.state.password_hasher
        async with self.tenant_scope() as session:
            row = SysClient(
                client_id=self.client_id if client_id is None else client_id,
                client_secret_hash=None if public else hasher.hash(secret),
                name=name,
                redirect_uris=json.dumps(list(redirect_uris) if redirect_uris is not None else [REDIRECT_URI]),
                grant_types=json.dumps(list(grant_types) if grant_types is not None else ["authorization_code"]),
                scopes=json.dumps(list(scopes) if scopes is not None else ["openid", "profile"]),
                ip_whitelist="[]",
                status=status,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def set_client_status(self, client_id: str, status: str) -> None:
        """变更客户端状态（按标识）。

        Args:
            client_id: 客户端标识。
            status: 目标状态。
        """
        async with self.tenant_scope() as session:
            row = (await session.execute(select(SysClient).where(SysClient.client_id == client_id))).scalar_one()
            await session.execute(update(SysClient).where(SysClient.id == row.id).values(status=status))
            await session.commit()


async def _ensure_schema(app: FastAPI) -> None:
    """兜底建表（租户库 `sys_client`，幂等）。

    Args:
        app: 应用实例。
    """
    tenant_engine = await app.state.engine_registry.get(DEMO_TENANT.db_key)
    async with tenant_engine.begin() as conn:
        await conn.run_sync(cast("Table", SysClient.__table__).create, checkfirst=True)


@pytest.fixture(autouse=True)
async def ensure_schema(tenant_db: None, service_app: FastAPI) -> AsyncIterator[None]:
    """兜底建表（`sys_client` 幂等），**不再整表清场**。

    单库叠加口径（04-6-2）：客户端标识按用例命名空间派生，断言只查自己那一行；
    逐例整表删除会在并行下删掉他人用例正在断言的客户端。

    Args:
        tenant_db: 共享租户库接线（**显式依赖保证先于应用装配**：引擎工厂在 app 创建时
            固化连接串，接线晚了会照旧连到工作区 `database/bms/` 下的常驻库）。
        service_app: 应用实例。

    Yields:
        None: 用例运行期。
    """
    await _ensure_schema(service_app)
    yield


@pytest.fixture
def oidc(service_app: FastAPI, ns: Namespace) -> OidcHarness:
    """装配 OIDC 测试替身（流程状态存储 + platform 概要客户端）。

    客户端标识 / 本地用户主键按用例命名空间派生（单库叠加下互不相交）。

    Args:
        service_app: 应用实例。
        ns: 用例命名空间。

    Returns:
        OidcHarness: 装配套件。
    """
    states = MemoryIdpStateStore()
    platform_client = FakeOidcPlatformClient()
    service_app.dependency_overrides[get_idp_state_store] = lambda: states
    service_app.dependency_overrides[get_service_client] = lambda: platform_client
    return OidcHarness(
        app=service_app,
        states=states,
        platform_client=platform_client,
        client_id=ns.code("bms-demo-client"),
        namespace_prefix=ns.prefix,
    )
