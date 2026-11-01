"""SSO 端点测试夹具（Kiwi 2197）：替身装配 + 租户库 / 平台库播种 + 表结构兜底。"""

from __future__ import annotations

import functools
import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table, select

from bms_core.api.deps import (
    get_distributed_lock,
    get_idp_state_store,
    get_outbox_store,
    get_rate_limiter,
    get_realtime_publisher,
    get_service_client,
    get_session_store,
    get_user_token_issuer,
)
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_core.idp.state.base import build_idp_state_key
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_core.lock.memory import MemoryDistributedLock
from bms_core.models.identity.identity_provider import SysIdentityProvider
from bms_core.models.identity.user_identity import SysUserIdentity
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_core.testing.namespace import Namespace
from bms_core.ws.null import NullRealtimePublisher
from bms_identity.domains.identity_federation.api import sso as sso_api
from bms_identity.domains.identity_federation.services.provider_registry import ProviderRegistry

from .helpers import (
    CAS_SERVER,
    CLIENT_ID,
    CLIENT_SECRET,
    DINGTALK_CLIENT_ID,
    ISSUER,
    TENANT_HEADERS,
    TENANT_ID,
    WECOM_AGENT_ID,
    WECOM_CORP_ID,
    CasMock,
    DingtalkMock,
    FakeSsoPlatformClient,
    FakeUserTokenIssuer,
    IdpMock,
    RecordingOutboxStore,
    WecomMock,
)

SECRET_ENV = "SSO_TEST_IDP_SECRET"
WECOM_SECRET_ENV = "SSO_TEST_WECOM_SECRET"
DINGTALK_SECRET_ENV = "SSO_TEST_DINGTALK_SECRET"


def _user_id(ns: Namespace) -> int:
    """本用例的本地用户主键（会话行与身份映射都按它隔离）。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 用户主键。
    """
    return int(ns.prefix[2:], 16) * 100


@dataclass
class SsoHarness:
    """SSO 用例装配套件：替身、流程状态存储与播种工具。

    单库叠加口径（04-6-2）：`idp_key` / `user_id` 按**用例命名空间**派生（见 `sso` 夹具），
    播种与断言只认本用例的标识；目录内不再整表清场。
    """

    app: FastAPI
    issuer: FakeUserTokenIssuer
    platform_client: FakeSsoPlatformClient
    store: MemorySessionStore
    limiter: MemoryRateLimiter
    states: MemoryIdpStateStore
    lock: MemoryDistributedLock
    outbox: RecordingOutboxStore
    idp: IdpMock
    cas: CasMock
    wecom: WecomMock
    dingtalk: DingtalkMock
    idp_key: str
    cas_key: str
    wecom_key: str
    dingtalk_key: str
    user_id: int

    @property
    def redirect_uri(self) -> str:
        """本用例 OIDC 提供方的回调地址（行配置与流程载荷同口径）。

        Returns:
            str: 回调地址。
        """
        return f"http://test/api/v1/auth/sso/{self.idp_key}/callback"

    @property
    def cas_redirect_uri(self) -> str:
        """本用例 CAS 提供方的回调地址。

        Returns:
            str: 回调地址。
        """
        return f"http://test/api/v1/auth/sso/{self.cas_key}/callback"

    @property
    def wecom_redirect_uri(self) -> str:
        """本用例企业微信提供方的回调地址。

        Returns:
            str: 回调地址。
        """
        return f"http://test/api/v1/auth/sso/{self.wecom_key}/callback"

    @property
    def dingtalk_redirect_uri(self) -> str:
        """本用例钉钉提供方的回调地址。

        Returns:
            str: 回调地址。
        """
        return f"http://test/api/v1/auth/sso/{self.dingtalk_key}/callback"

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

    def platform_scope(self) -> AbstractAsyncContextManager[DbSession]:
        """平台库会话上下文。

        Returns:
            AbstractAsyncContextManager[DbSession]: 会话上下文。
        """
        return session_scope(
            self.app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=self.app.state.session_factory,
        )

    def peek(self, state: str) -> ConcurrentStableDict[str, object]:
        """读取流程状态载荷（私有字典直读）。

        Args:
            state: 流程状态串。

        Returns:
            ConcurrentStableDict[str, object]: 流程载荷。
        """
        entry = self.states._items[build_idp_state_key(state)]  # pyright: ignore[reportPrivateUsage]
        return entry[0]

    def provider_config(self, **overrides: object) -> ConcurrentStableDict[str, object]:
        """构造 OIDC IdP 行配置（缺省指向 Mock IdP）。

        Args:
            **overrides: 覆盖字段。

        Returns:
            ConcurrentStableDict[str, object]: 配置对象。
        """
        config: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "issuer": ISSUER,
                "client_id": CLIENT_ID,
                "client_secret_ref": f"env:{SECRET_ENV}",
                "redirect_uri": self.redirect_uri,
                "scopes": ["openid", "profile", "email"],
            }
        )
        config.update(overrides.items())
        return config

    def cas_provider_config(self, **overrides: object) -> ConcurrentStableDict[str, object]:
        """构造 CAS IdP 行配置（缺省指向 Mock CAS）。

        Args:
            **overrides: 覆盖字段。

        Returns:
            ConcurrentStableDict[str, object]: 配置对象。
        """
        config: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "cas_server_url": CAS_SERVER,
                "redirect_uri": self.cas_redirect_uri,
            }
        )
        config.update(overrides.items())
        return config

    def wecom_provider_config(self, **overrides: object) -> ConcurrentStableDict[str, object]:
        """构造企业微信 IdP 行配置（缺省指向 Mock 企微）。

        Args:
            **overrides: 覆盖字段。

        Returns:
            ConcurrentStableDict[str, object]: 配置对象。
        """
        config: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "corp_id": WECOM_CORP_ID,
                "agent_id": WECOM_AGENT_ID,
                "secret_ref": f"env:{WECOM_SECRET_ENV}",
                "redirect_uri": self.wecom_redirect_uri,
            }
        )
        config.update(overrides.items())
        return config

    def dingtalk_provider_config(self, **overrides: object) -> ConcurrentStableDict[str, object]:
        """构造钉钉 IdP 行配置（缺省指向 Mock 钉钉）。

        Args:
            **overrides: 覆盖字段。

        Returns:
            ConcurrentStableDict[str, object]: 配置对象。
        """
        config: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "client_id": DINGTALK_CLIENT_ID,
                "client_secret_ref": f"env:{DINGTALK_SECRET_ENV}",
                "redirect_uri": self.dingtalk_redirect_uri,
            }
        )
        config.update(overrides.items())
        return config

    async def seed_provider(
        self,
        *,
        idp_key: str | None = None,
        type: str = "oidc",
        status: str = "enabled",
        sort: int = 0,
        config: ConcurrentStableDict[str, object] | None = None,
        name: str = "Keycloak",
    ) -> None:
        """播种一条 IdP 提供方行（标识缺省取本用例命名空间派生值）。

        Args:
            idp_key: 身份源标识（None 取 `self.idp_key`）。
            type: 协议类型（oidc / cas / wecom / dingtalk）。
            status: 状态（enabled/disabled）。
            sort: 排序值。
            config: 行配置（None 按类型取缺省 Mock 配置）。
            name: 展示名。
        """
        idp_key = self.idp_key if idp_key is None else idp_key
        if config is not None:
            payload = config
        elif type == "cas":
            payload = self.cas_provider_config()
        elif type == "wecom":
            payload = self.wecom_provider_config()
        elif type == "dingtalk":
            payload = self.dingtalk_provider_config()
        else:
            payload = self.provider_config()
        async with self.tenant_scope() as session:
            session.add(
                SysIdentityProvider(
                    name=name,
                    idp_key=idp_key,
                    type=type,
                    icon="",
                    config=json.dumps(dict(payload)),
                    status=status,
                    sort=sort,
                )
            )
            await session.commit()

    async def set_provider_status(self, status: str, *, idp_key: str | None = None) -> None:
        """变更提供方状态（覆盖回调期停用分支）。

        Args:
            status: 新状态。
            idp_key: 身份源标识（None 取 `self.idp_key`）。
        """
        key = self.idp_key if idp_key is None else idp_key
        async with self.tenant_scope() as session:
            row = (
                await session.execute(select(SysIdentityProvider).where(SysIdentityProvider.idp_key == key))
            ).scalar_one()
            row.status = status
            await session.commit()

    async def provider_row(self) -> SysIdentityProvider:
        """取本用例的提供方行（叠加下按 `idp_key` 精确定位，不整表取数）。

        Returns:
            SysIdentityProvider: 提供方行。
        """
        async with self.tenant_scope() as session:
            row = (
                await session.execute(
                    select(SysIdentityProvider).where(SysIdentityProvider.idp_key == self.idp_key)
                )
            ).scalar_one()
            return row

    async def seed_mapping(
        self,
        *,
        idp_key: str | None = None,
        external_id: str = "sub-1",
        tenant_id: str = TENANT_ID,
        user_id: int | None = None,
        duplicate: bool = False,
    ) -> None:
        """播种平台库身份映射行（duplicate=True 造冲突双行）。

        Args:
            idp_key: 身份源标识（None 取 `self.idp_key`）。
            external_id: 外部主体标识。
            tenant_id: 关联租户主键（雪花 id 字符串）。
            user_id: 本地用户主键（None 取 `self.user_id`）。
            duplicate: 是否追加相同映射（触发冲突分支）。
        """
        key = self.idp_key if idp_key is None else idp_key
        subject = self.user_id if user_id is None else user_id
        row = SysUserIdentity(
            idp_key=f"{tenant_id}:{key}",
            external_id=external_id,
            tenant_id=int(tenant_id),
            user_id=subject,
        )
        async with self.platform_scope() as session:
            session.add(row)
            if duplicate:
                session.add(
                    SysUserIdentity(
                        idp_key=f"{tenant_id}:{key}",
                        external_id=external_id,
                        tenant_id=int(tenant_id),
                        user_id=subject,
                    )
                )
            await session.commit()

    async def start_flow(
        self, client: AsyncClient, *, idp_key: str | None = None, tenant_header: bool = True
    ) -> tuple[str, str, ConcurrentStableDict[str, object]]:
        """发起授权跳转并返回 (state, Location, 流程载荷)。

        Args:
            client: 测试客户端。
            idp_key: 身份源标识（None 取 `self.idp_key`）。
            tenant_header: 是否带租户请求头。

        Returns:
            tuple[str, str, ConcurrentStableDict[str, object]]: (state, 跳转 URL, 流程载荷)。
        """
        idp_key = self.idp_key if idp_key is None else idp_key
        response = await client.get(
            f"/api/v1/auth/sso/{idp_key}/authorize",
            headers=TENANT_HEADERS if tenant_header else {},
        )
        assert response.status_code == 302
        location = response.headers["location"]
        state = parse_qs(urlparse(location).query)["state"][0]
        return state, location, self.peek(state)

    async def flow_payload(self, state: str) -> ConcurrentStableDict[str, object]:
        """读流程载荷（state 不存在返回空）。

        Args:
            state: 流程状态串。

        Returns:
            ConcurrentStableDict[str, object]: 流程载荷。
        """
        entry = self.states._items.get(build_idp_state_key(state))  # pyright: ignore[reportPrivateUsage]
        return entry[0] if entry is not None else ConcurrentStableDict()


@pytest.fixture
def idp() -> IdpMock:
    """Mock IdP 夹具（每用例独立密钥与响应状态）。

    Returns:
        IdpMock: Mock IdP。
    """
    return IdpMock()


async def _ensure_schema(app: FastAPI) -> None:
    """兜底建表（平台库 sys_user_identity / 租户库 sys_identity_provider）。

    Args:
        app: 应用实例。
    """
    tenant_engine = await app.state.engine_registry.get(DEMO_TENANT.db_key)
    async with tenant_engine.begin() as conn:
        await conn.run_sync(cast("Table", SysIdentityProvider.__table__).create, checkfirst=True)
    platform_engine = await app.state.engine_registry.get(PLATFORM_DB_KEY)
    async with platform_engine.begin() as conn:
        await conn.run_sync(cast("Table", SysUserIdentity.__table__).create, checkfirst=True)


@pytest.fixture(autouse=True)
async def ensure_schema(tenant_db: None, service_app: FastAPI) -> AsyncIterator[None]:
    """兜底建表（`sys_identity_provider` / `sys_user_identity` 幂等），**不再整表清场**。

    单库叠加口径（04-6-2）：提供方标识与身份映射均按用例命名空间派生（见 `sso` 夹具），
    断言只查自己那几行；逐例整表删除会在并行下删掉他人用例正在断言的行。

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
def sso(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch, idp: IdpMock, ns: Namespace) -> SsoHarness:
    """装配 SSO 测试替身（依赖覆盖 + ProviderRegistry 传输注入）。

    单库叠加口径（04-6-2）：各协议提供方标识与本地用户主键按用例命名空间派生，
    用例之间互不相交（共享租户库 / 平台库上叠加执行）。

    Args:
        service_app: 应用实例。
        monkeypatch: pytest monkeypatch 夹具。
        idp: Mock IdP。
        ns: 用例命名空间（提供方标识与用户主键的派生源头）。

    Returns:
        SsoHarness: 装配套件。
    """
    issuer, platform_client, store, limiter, states = (
        FakeUserTokenIssuer(),
        FakeSsoPlatformClient(),
        MemorySessionStore(),
        MemoryRateLimiter(),
        MemoryIdpStateStore(),
    )
    lock, outbox = MemoryDistributedLock(), RecordingOutboxStore()
    cas = CasMock()
    wecom = WecomMock()
    dingtalk = DingtalkMock()
    service_app.dependency_overrides[get_user_token_issuer] = lambda: issuer
    service_app.dependency_overrides[get_service_client] = lambda: platform_client
    service_app.dependency_overrides[get_session_store] = lambda: store
    service_app.dependency_overrides[get_rate_limiter] = lambda: limiter
    service_app.dependency_overrides[get_idp_state_store] = lambda: states
    service_app.dependency_overrides[get_distributed_lock] = lambda: lock
    service_app.dependency_overrides[get_outbox_store] = lambda: outbox
    service_app.dependency_overrides[get_realtime_publisher] = lambda: NullRealtimePublisher()
    monkeypatch.setenv(SECRET_ENV, CLIENT_SECRET)
    monkeypatch.setenv(WECOM_SECRET_ENV, "wecom-secret")
    monkeypatch.setenv(DINGTALK_SECRET_ENV, "dingtalk-secret")

    def _dispatch(request: httpx.Request) -> httpx.Response:
        """按路径分派 Mock IdP（OIDC）、Mock CAS、Mock 企微与 Mock 钉钉。

        Args:
            request: 出站请求。

        Returns:
            httpx.Response: 模拟响应。
        """
        path = request.url.path
        if path.endswith("/p3/serviceValidate"):
            return cas.handle(request)
        if path.endswith("/cgi-bin/gettoken") or path.endswith("/cgi-bin/auth/getuserinfo"):
            return wecom.handle(request)
        if path.endswith("/v1.0/oauth2/userAccessToken") or path.endswith("/v1.0/contact/users/me"):
            return dingtalk.handle(request)
        return idp.handle(request)

    monkeypatch.setattr(
        sso_api,
        "ProviderRegistry",
        functools.partial(ProviderRegistry, transport=httpx.MockTransport(_dispatch)),
    )
    return SsoHarness(
        app=service_app,
        issuer=issuer,
        platform_client=platform_client,
        store=store,
        limiter=limiter,
        states=states,
        lock=lock,
        outbox=outbox,
        idp=idp,
        cas=cas,
        wecom=wecom,
        dingtalk=dingtalk,
        idp_key=ns.code("keycloak"),
        cas_key=ns.code("cas"),
        wecom_key=ns.code("wecom"),
        dingtalk_key=ns.code("dingtalk"),
        user_id=_user_id(ns),
    )
