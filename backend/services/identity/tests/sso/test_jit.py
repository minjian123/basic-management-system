"""JIT 建号与身份映射测试（Kiwi 2198）：编排分支 + 端点 E2E + 事件登记。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    ConfigError,
    SsoIdentityConflictError,
    SsoIdentityUnmatchedError,
    SsoProviderUnavailableError,
)
from bms_core.events.contracts import resolve_event_contract
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.lock.base import build_lock_key
from bms_core.lock.memory import MemoryDistributedLock
from bms_core.models.outbox import SysEventDeadLetter, SysOutbox
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.null import NullOutboxStore
from bms_core.outbox.store import SqlOutboxStore
from bms_identity.models.user_identity import SysUserIdentity
from bms_identity.repositories.user_identity import UserIdentityRepository
from bms_identity.services.jit import (
    JIT_EVENT_TYPE,
    ExternalIdentity,
    JitService,
    allowed_email_domains,
    clean_username,
    derive_username,
    jit_enabled_for,
)
from bms_identity.services.org_client import OrgCredentialClient

from .conftest import SsoHarness
from .helpers import IDP_KEY, TENANT, TENANT_HEADERS, TENANT_ID, FakeSsoOrgClient

CALLBACK = f"/api/v1/auth/sso/{IDP_KEY}/callback"
IDENTITY = ExternalIdentity(
    subject="sub-1",
    username="Alice.Admin",
    name="爱丽丝",
    email="alice@corp.com",
    locale="zh-cn",
    timezone="Asia/Shanghai",
)


async def _platform_session() -> tuple[AsyncSession, object]:
    """建临时平台库会话（含身份映射与发件箱表）。

    Returns:
        tuple[AsyncSession, object]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUserIdentity.metadata.create_all)
        await conn.run_sync(SysOutbox.metadata.create_all)
        await conn.run_sync(SysEventDeadLetter.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


def _service(
    org: FakeSsoOrgClient,
    *,
    lock: MemoryDistributedLock | None = None,
    outbox: BaseOutboxStore | None = None,
    settings: Settings | None = None,
) -> JitService:
    """构造 JIT 服务（真实锁 + 替身 org + 可控发件箱）。

    Args:
        org: org 内部接口替身。
        lock: 分布式锁（缺省新建）。
        outbox: 发件箱存储（缺省 Null）。
        settings: 配置（缺省默认）。

    Returns:
        JitService: JIT 服务。
    """
    return JitService(
        lock=lock if lock is not None else MemoryDistributedLock(),
        org_client=OrgCredentialClient(org),
        outbox_store=outbox if outbox is not None else NullOutboxStore(),
        sso_settings=(settings or Settings()).sso,
    )


@pytest.mark.kiwi_id(2198)
def test_helpers_username_and_config() -> None:
    """helper：用户名清洗与派生、白名单解析、开关行优先回落全局。"""
    assert clean_username("  Alice.ADMIN ") == "alice.admin"
    assert clean_username("a b@c") == "abc"
    assert clean_username("!!!") == ""
    assert clean_username(None) == ""
    assert derive_username(ExternalIdentity(subject="s1", username="", email="bob@corp.com")) == "bob"
    assert derive_username(ExternalIdentity(subject="s1", username="", email=None)) == "s1"
    assert derive_username(ExternalIdentity(subject="!!!")) == "user"

    assert jit_enabled_for('{"jit_enabled": true}', Settings().sso) is True
    assert jit_enabled_for("{}", Settings().sso) is False
    assert allowed_email_domains('{"allowed_email_domains": ["Corp.com"]}', "k") == frozenset({"corp.com"})
    assert allowed_email_domains("{}", "k") == frozenset()
    with pytest.raises(ConfigError):
        allowed_email_domains('{"allowed_email_domains": "corp.com"}', "k")
    with pytest.raises(ConfigError):
        jit_enabled_for("{not-json", Settings().sso)
    with pytest.raises(ConfigError):
        allowed_email_domains("[1,2]", "k")


@pytest.mark.kiwi_id(2198)
@pytest.mark.kiwi_id(2217)
async def test_provision_creates_user_mapping_and_event() -> None:
    """首登：建号 + 写映射 + 同事务入发件箱（事件契约校验通过）。"""
    register_platform_event_contracts()
    session, engine = await _platform_session()
    org = FakeSsoOrgClient()
    outbox = SqlOutboxStore(contract_mode="enforce")
    service = _service(org, outbox=outbox)

    result = await service.provision(
        tenant_id=TENANT_ID,
        tenant_code=TENANT,
        idp_key=IDP_KEY,
        config='{"jit_enabled": true}',
        identity=IDENTITY,
        platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
    )
    assert result.created is True
    assert org.users[result.user_id]["username"] == "alice.admin"

    rows = (await session.execute(select(SysUserIdentity))).scalars().all()
    assert len(rows) == 1
    assert rows[0].idp_key == f"{TENANT_ID}:{IDP_KEY}"
    assert rows[0].external_id == "sub-1"
    assert rows[0].user_id == result.user_id

    events = (await session.execute(select(SysOutbox))).scalars().all()
    assert len(events) == 1
    event = events[0]
    assert event.event_type == JIT_EVENT_TYPE
    assert event.event_version == "1.0.0"
    assert event.payload == {"user_id": str(result.user_id), "idp_key": f"{TENANT_ID}:{IDP_KEY}"}
    assert resolve_event_contract(JIT_EVENT_TYPE) is not None
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.kiwi_id(2198)
async def test_provision_reuses_existing_mapping() -> None:
    """二次登录：锁内二次查命中映射直接复用，不再建号 / 不发事件。"""
    session, engine = await _platform_session()
    session.add(
        SysUserIdentity(idp_key=f"{TENANT_ID}:{IDP_KEY}", external_id="sub-1", tenant_id=int(TENANT_ID), user_id=88)
    )
    await session.commit()
    org = FakeSsoOrgClient()
    service = _service(org)

    result = await service.provision(
        tenant_id=TENANT_ID,
        tenant_code=TENANT,
        idp_key=IDP_KEY,
        config='{"jit_enabled": true}',
        identity=IDENTITY,
        platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
    )
    assert result.user_id == 88 and result.created is False
    assert org.calls == []
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.kiwi_id(2198)
async def test_provision_disabled_and_whitelist() -> None:
    """开关关闭 20054；租户 / 域名白名单外 20054。"""
    session, engine = await _platform_session()
    org = FakeSsoOrgClient()
    serviceless = _service(org)
    with pytest.raises(SsoIdentityUnmatchedError):
        await serviceless.provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config="{}",
            identity=IDENTITY,
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )

    tenant_settings = Settings()
    tenant_settings.sso.jit_allowed_tenants = ["other"]
    with pytest.raises(SsoIdentityUnmatchedError):
        await _service(org, settings=tenant_settings).provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true}',
            identity=IDENTITY,
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )

    with pytest.raises(SsoIdentityUnmatchedError):
        await _service(org).provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true, "allowed_email_domains": ["corp.com"]}',
            identity=ExternalIdentity(subject="sub-2", username="bob", email="bob@other.com"),
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )
    with pytest.raises(SsoIdentityUnmatchedError):
        await _service(org).provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true, "allowed_email_domains": ["corp.com"]}',
            identity=ExternalIdentity(subject="sub-3", username="nobody"),
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.kiwi_id(2198)
async def test_provision_username_suffix_and_exhaustion() -> None:
    """撞名换后缀 `_2.._5`；用尽仍冲突 → 20054。"""
    session, engine = await _platform_session()
    org = FakeSsoOrgClient()
    org.users[1] = {"username": "alice", "name": "a", "status": "enabled", "locale": None, "timezone": None}
    org.users[2] = {"username": "alice_2", "name": "a", "status": "enabled", "locale": None, "timezone": None}
    service = _service(org)
    result = await service.provision(
        tenant_id=TENANT_ID,
        tenant_code=TENANT,
        idp_key=IDP_KEY,
        config='{"jit_enabled": true}',
        identity=ExternalIdentity(subject="sub-9", username="alice"),
        platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
    )
    assert result.created is True
    assert org.users[result.user_id]["username"] == "alice_3"

    for index in range(1, 6):
        name = "bob" if index == 1 else f"bob_{index}"
        org.users[100 + index] = {"username": name, "name": "b", "status": "enabled", "locale": None, "timezone": None}
    with pytest.raises(SsoIdentityUnmatchedError):
        await service.provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true}',
            identity=ExternalIdentity(subject="sub-10", username="bob"),
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.kiwi_id(2198)
async def test_provision_lock_conflict_and_org_unavailable() -> None:
    """锁未取到 → 20055；org 建号不可达 → 20053。"""
    session, engine = await _platform_session()
    lock = MemoryDistributedLock()
    settings = Settings()
    settings.sso.jit_lock_wait_seconds = 0
    await lock.acquire(build_lock_key(tenant=TENANT_ID, resource=f"jit:{IDP_KEY}:sub-1"))
    with pytest.raises(SsoIdentityConflictError):
        await _service(FakeSsoOrgClient(), lock=lock, settings=settings).provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true}',
            identity=IDENTITY,
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )

    org = FakeSsoOrgClient()
    org.fail_create = True
    with pytest.raises(SsoProviderUnavailableError):
        await _service(org).provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true}',
            identity=IDENTITY,
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.kiwi_id(2198)
async def test_provision_mapping_integrity_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """映射唯一冲突：回读命中复用（不再建号）；回读未命中 → 20055。"""
    session, engine = await _platform_session()
    state = {"reads": 0}

    async def fake_get(self: UserIdentityRepository, idp_key: str, external_id: str) -> object:
        state["reads"] += 1
        return None if state["reads"] == 1 else SimpleNamespace(user_id=777, tenant_id=TENANT)

    async def fake_create(self: UserIdentityRepository, **values: object) -> object:
        raise IntegrityError("stmt", {}, Exception("duplicate"))

    monkeypatch.setattr(UserIdentityRepository, "get_by_key_external", fake_get)
    monkeypatch.setattr(UserIdentityRepository, "create", fake_create)

    result = await _service(FakeSsoOrgClient()).provision(
        tenant_id=TENANT_ID,
        tenant_code=TENANT,
        idp_key=IDP_KEY,
        config='{"jit_enabled": true}',
        identity=IDENTITY,
        platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
    )
    assert result.user_id == 777 and result.created is False

    state["reads"] = 0

    async def always_none(self: UserIdentityRepository, idp_key: str, external_id: str) -> object:
        return None

    monkeypatch.setattr(UserIdentityRepository, "get_by_key_external", always_none)
    with pytest.raises(SsoIdentityConflictError):
        await _service(FakeSsoOrgClient()).provision(
            tenant_id=TENANT_ID,
            tenant_code=TENANT,
            idp_key=IDP_KEY,
            config='{"jit_enabled": true}',
            identity=IDENTITY,
            platform_session=cast("AsyncSession", session),  # type: ignore[arg-type]
        )
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.kiwi_id(2198)
async def test_jit_endpoint_end_to_end(client: AsyncClient, sso: SsoHarness) -> None:
    """端点 E2E：首登自动建号 + 写映射 + 发事件；二次登录复用不重复建号。"""
    await sso.seed_provider(config=sso.provider_config(jit_enabled=True))

    first = await _flow_callback(client, sso)
    assert first.status_code == 200 and first.json()["data"] == {"tenant": TENANT}
    async with sso.platform_scope() as session:
        rows = (await session.execute(select(SysUserIdentity))).scalars().all()
    assert len(rows) == 1 and rows[0].idp_key == f"{TENANT_ID}:{IDP_KEY}" and rows[0].external_id == "sub-1"
    assert len(sso.outbox.events) == 1
    assert sso.outbox.events[0].event_type == JIT_EVENT_TYPE

    second = await _flow_callback(client, sso)
    assert second.status_code == 200
    async with sso.platform_scope() as session:
        again = (await session.execute(select(SysUserIdentity))).scalars().all()
    assert len(again) == 1
    assert len(sso.outbox.events) == 1


async def _flow_callback(client: AsyncClient, sso: SsoHarness):
    """发起授权后回调（ID Token nonce 取流程载荷）。

    Args:
        client: 测试客户端。
        sso: 装配套件。

    Returns:
        httpx.Response: 回调响应。
    """
    state, _, payload = await sso.start_flow(client)
    sso.idp.make_id_token(nonce=cast("str", payload["nonce"]))
    return await client.get(f"{CALLBACK}?state={state}&code=code-1", headers=TENANT_HEADERS)
