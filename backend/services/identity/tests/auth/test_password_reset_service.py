"""找回密码服务层测试（Kiwi 2210）：分支与降级（免 IP / 可选验证码 / 存储与通知失败 / 载荷脏值 / 清理异常）。"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import PasswordResetSettings
from bms_core.core.exceptions import (
    PasswordPolicyViolationError,
    PasswordResetTokenError,
    PasswordReusedError,
    ServiceUnavailableError,
)
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.security.session import DefaultSessionSecurity
from bms_core.session.memory import MemorySessionStore
from bms_identity.models.session import SysSession
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.password_reset import PASSWORD_RESET_NAMESPACE, PasswordResetService
from bms_identity.services.session import SessionService

from .helpers import TENANT, TENANT_ID, FakeCaptcha, FakeOrgClient, RecordingNotifier, RecordingRealtimePublisher


class _FailingStore(BaseIdpStateStore):
    """测试替身：写入 / 读取一律失败（Redis 不可用分支）。"""

    plugin_name = "failing"

    async def save(self, state: str, payload: object, **kwargs: object) -> None:
        """写入即抛异常。

        Args:
            state: 流程状态。
            payload: 载荷。
            **kwargs: 其余参数（忽略）。

        Raises:
            RuntimeError: 固定失败。
        """
        raise RuntimeError("redis down")

    async def consume(self, state: str, **kwargs: object) -> None:
        """读取返回 None（未命中）。

        Args:
            state: 流程状态。
            **kwargs: 其余参数（忽略）。

        Returns:
            None: 固定未命中。
        """
        return None

    async def delete(self, state: str, **kwargs: object) -> None:
        """删除空操作。

        Args:
            state: 流程状态。
            **kwargs: 其余参数（忽略）。
        """


class _ExplodingStore(MemorySessionStore):
    """测试替身：黑名单写入抛异常（运行时清理失败分支）。"""

    async def blacklist(self, key: str, *, ttl: int) -> None:
        """写入黑名单即抛异常。

        Args:
            key: 黑名单键。
            ttl: 有效期。

        Raises:
            RuntimeError: 固定失败。
        """
        raise RuntimeError("store down")


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话（含 `sys_session` 表）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysSession.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


def _service(
    session: AsyncSession,
    *,
    org: FakeOrgClient | None = None,
    states: BaseIdpStateStore | None = None,
    notifier: RecordingNotifier | None = None,
    captcha: FakeCaptcha | None = None,
    store: MemorySessionStore | None = None,
    reset_url: str = "",
) -> PasswordResetService:
    """构造找回密码服务（替身注入）。

    Args:
        session: 临时租户库会话。
        org: org 客户端替身。
        states: 流程状态存储替身。
        notifier: 通知基座替身。
        captcha: 验证码替身。
        store: 会话标记存储替身。
        reset_url: 重置链接基址。

    Returns:
        PasswordResetService: 找回密码服务。
    """
    sessions = SessionService(
        session=session,
        uow=DbUnitOfWork(session),
        security=DefaultSessionSecurity(secret_key="test-secret"),
        store=store or MemorySessionStore(),
        publisher=RecordingRealtimePublisher(),
    )
    return PasswordResetService(
        org_client=OrgCredentialClient(org or FakeOrgClient()),
        captcha=captcha or FakeCaptcha(required=False),
        rate_limiter=MemoryRateLimiter(),
        state_store=states or MemoryIdpStateStore(),
        notifier=notifier or RecordingNotifier(),
        session_service=sessions,
        settings=PasswordResetSettings(reset_url=reset_url),
    )


@pytest.mark.kiwi_id(2210)
async def test_request_reset_optional_captcha_without_ip_uses_token_text() -> None:
    """可选验证码 + 无 IP：发起成功；无重置链接时通知内容回退令牌文案且载荷可消费。"""
    session, engine = await _session()
    org = FakeOrgClient()
    org.set_user("admin", password="secret", user_id=1001, email="admin@example.com")
    notifier = RecordingNotifier()
    states = MemoryIdpStateStore()
    service = _service(session, org=org, states=states, notifier=notifier)

    result = await service.request_reset("admin", None, tenant_id=TENANT_ID, tenant_code=TENANT, ip=None)
    assert result.sent is True
    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert message.channel.value == "email" and message.recipient == "admin@example.com"
    assert "使用以下重置令牌完成重置（单次有效）：" in message.content

    token = message.content.rsplit("：", 1)[-1].removesuffix("。")
    payload = await states.consume(token, tenant=TENANT_ID, namespace=PASSWORD_RESET_NAMESPACE)
    assert payload is not None and payload.get("user_id") == 1001 and payload.get("account") == "admin"
    await session.close()
    await engine.dispose()


@pytest.mark.kiwi_id(2210)
async def test_request_reset_fail_closed_on_store_and_notify() -> None:
    """存储写入失败 / 通知抛异常 / 未送达：一律 10007，不假报已发送。"""
    session, engine = await _session()
    org = FakeOrgClient()
    org.set_user("admin", password="secret", user_id=1001, email="admin@example.com")

    with pytest.raises(ServiceUnavailableError) as save_failed:
        await _service(session, org=org, states=_FailingStore()).request_reset(
            "admin", None, tenant_id=TENANT_ID, tenant_code=TENANT, ip=None
        )
    assert save_failed.value.code == 10007

    with pytest.raises(ServiceUnavailableError):
        await _service(session, org=org, notifier=RecordingNotifier(raises=True)).request_reset(
            "admin", None, tenant_id=TENANT_ID, tenant_code=TENANT, ip=None
        )

    with pytest.raises(ServiceUnavailableError):
        await _service(session, org=org, notifier=RecordingNotifier(delivered=False)).request_reset(
            "admin", None, tenant_id=TENANT_ID, tenant_code=TENANT, ip=None
        )
    await session.close()
    await engine.dispose()


@pytest.mark.kiwi_id(2210)
async def test_reset_password_token_payload_and_not_found() -> None:
    """载荷脏值 / 未命中 / 账号不存在：统一 20005（不泄露细节）。"""
    session, engine = await _session()
    org = FakeOrgClient()
    org.set_user("admin", password="secret", user_id=1001, email="admin@example.com")
    states = MemoryIdpStateStore()
    service = _service(session, org=org, states=states)

    with pytest.raises(PasswordResetTokenError) as missing:
        await service.reset_password("ghost-token", "NewSecret1!", tenant_id=TENANT_ID, tenant_code=TENANT)
    assert missing.value.code == 20005 and missing.value.http_status == 400

    await states.save("dirty", {"user_id": "x", "account": 1}, tenant=TENANT_ID, namespace=PASSWORD_RESET_NAMESPACE)
    with pytest.raises(PasswordResetTokenError):
        await service.reset_password("dirty", "NewSecret1!", tenant_id=TENANT_ID, tenant_code=TENANT)

    await states.save(
        "ghost",
        {"user_id": 999, "account": "nobody", "tenant": "demo"},
        tenant="demo",
        namespace=PASSWORD_RESET_NAMESPACE,
    )
    with pytest.raises(PasswordResetTokenError):
        await service.reset_password("ghost", "NewSecret1!", tenant_id=TENANT_ID, tenant_code=TENANT)
    await session.close()
    await engine.dispose()


@pytest.mark.kiwi_id(2210)
async def test_reset_password_policy_and_history_mapping() -> None:
    """改密策略闸门：复杂度违规 30005（带 violations）/ 历史重复 30006。"""
    session, engine = await _session()
    org = FakeOrgClient()
    org.set_user("admin", password="secret", user_id=1001, email="admin@example.com")
    states = MemoryIdpStateStore()
    service = _service(session, org=org, states=states)

    await states.save(
        "weak-token", {"user_id": 1001, "account": "admin"}, tenant=TENANT_ID, namespace=PASSWORD_RESET_NAMESPACE
    )
    with pytest.raises(PasswordPolicyViolationError) as weak:
        await service.reset_password("weak-token", "weak", tenant_id=TENANT_ID, tenant_code=TENANT)
    assert weak.value.code == 30005 and weak.value.data == {"violations": ["too_short"]}

    await states.save(
        "old-token", {"user_id": 1001, "account": "admin"}, tenant=TENANT_ID, namespace=PASSWORD_RESET_NAMESPACE
    )
    with pytest.raises(PasswordReusedError) as reused:
        await service.reset_password("old-token", "old-pass", tenant_id=TENANT_ID, tenant_code=TENANT)
    assert reused.value.code == 30006
    await session.close()
    await engine.dispose()


@pytest.mark.kiwi_id(2210)
async def test_revoke_user_sessions_continues_on_cleanup_failure() -> None:
    """运行时清理失败不阻断重置：DB 已撤销、方法返回清单、重置仍成功。"""
    session, engine = await _session()
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        SysSession(
            id=7001,
            session_id="7001",
            user_id=1001,
            refresh_token_hash="hash",
            login_at=now,
            expires_at=now + timedelta(days=14),
        )
    )
    await session.commit()

    org = FakeOrgClient()
    org.set_user("admin", password="secret", user_id=1001, email="admin@example.com")
    states = MemoryIdpStateStore()
    service = _service(session, org=org, states=states, store=_ExplodingStore())
    await states.save(
        "boom", {"user_id": 1001, "account": "admin"}, tenant=TENANT_ID, namespace=PASSWORD_RESET_NAMESPACE
    )

    result = await service.reset_password("boom", "NewSecret1!", tenant_id=TENANT_ID, tenant_code=TENANT)
    assert result.reset is True
    row = (await session.execute(select(SysSession).where(SysSession.session_id == "7001"))).scalar_one()
    assert row.revoked_at is not None
    await session.close()
    await engine.dispose()
