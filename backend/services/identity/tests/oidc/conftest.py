"""OIDC Provider 端点测试夹具（Kiwi 2202）：替身装配 + 客户端播种 + 表结构兜底。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Table, delete, select, update

from bms_core.api.deps import get_idp_state_store, get_service_client
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_identity.models.client import SysClient

from .helpers import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FakeOidcOrgClient


@dataclass
class OidcHarness:
    """OIDC 用例装配套件：替身、流程状态存储与播种工具。"""

    app: FastAPI
    states: MemoryIdpStateStore
    org: FakeOidcOrgClient

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
        client_id: str = CLIENT_ID,
        secret: str = CLIENT_SECRET,
        public: bool = False,
        redirect_uris: list[str] | None = None,
        grant_types: list[str] | None = None,
        scopes: list[str] | None = None,
        status: str = "enabled",
        name: str = "Demo Client",
    ) -> SysClient:
        """播种一条客户端行（secret 经应用装配哈希器哈希）。

        Args:
            client_id: 客户端标识。
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
                client_id=client_id,
                client_secret_hash=None if public else hasher.hash(secret),
                name=name,
                redirect_uris=json.dumps(redirect_uris if redirect_uris is not None else [REDIRECT_URI]),
                grant_types=json.dumps(grant_types if grant_types is not None else ["authorization_code"]),
                scopes=json.dumps(scopes if scopes is not None else ["openid", "profile"]),
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
    """兜底建表（租户库 `sys_client`）。

    Args:
        app: 应用实例。
    """
    tenant_engine = await app.state.engine_registry.get(DEMO_TENANT.db_key)
    async with tenant_engine.begin() as conn:
        await conn.run_sync(cast("Table", SysClient.__table__).create, checkfirst=True)


async def _clean_rows(app: FastAPI) -> None:
    """清空用例涉及的数据行（`sys_client`）。

    Args:
        app: 应用实例。
    """
    async with session_scope(
        app.state.engine_registry, db_key=DEMO_TENANT.db_key, factory=app.state.session_factory
    ) as session:
        await session.execute(delete(SysClient))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_oidc(service_app: FastAPI) -> AsyncIterator[None]:
    """用例前后清空 `sys_client` 并兜底建表。

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
def oidc(service_app: FastAPI) -> OidcHarness:
    """装配 OIDC 测试替身（流程状态存储 + org 概要客户端）。

    Args:
        service_app: 应用实例。

    Returns:
        OidcHarness: 装配套件。
    """
    states = MemoryIdpStateStore()
    org = FakeOidcOrgClient()
    service_app.dependency_overrides[get_idp_state_store] = lambda: states
    service_app.dependency_overrides[get_service_client] = lambda: org
    return OidcHarness(app=service_app, states=states, org=org)
