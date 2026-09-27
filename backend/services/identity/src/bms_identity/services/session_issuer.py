"""认证与身份服务 services 层：会话签发作构件（本地登录 / SSO 共用）。

- `issue`：`new_session_id` → `issue_pair`（access / refresh 同 `session_id`）→ `enforce_max_active`
  → `uow.begin` 内 `create_session`（含 `refresh_token_hash`）→ `session_store.save`，顺序与 01_03
  本地登录链路一致；SSO 回调复用同一构件，保证会话与本地登录**同构**（`/auth/refresh` 与后续
  `require_auth` 无缝消费）。
- `build_session_issuer`：请求级构造（装配 `SessionService`），供 `api/auth.py` 与 `api/sso.py` 共用。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bms_core.core.base import BaseObject
from bms_core.core.config import SessionSettings
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.oauth.base import TOKEN_TYPE_BEARER
from bms_core.oauth.user_token import BaseUserTokenIssuer, UserTokenSpec
from bms_core.security.base import BaseSessionSecurity
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher
from bms_identity.repositories.session import SessionRepository
from bms_identity.services.session import SessionService

__all__ = [
    "IssuedSession",
    "SessionIssuer",
    "build_session_issuer",
    "hash_refresh_token",
    "truncate_field",
]


def hash_refresh_token(token: str) -> str:
    """refresh token 哈希（SHA-256 hex；不落原始值）。

    Args:
        token: refresh token 紧凑串。

    Returns:
        str: 哈希（小写十六进制）。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def truncate_field(value: str | None, limit: int) -> str | None:
    """截断字符串到上限长度（None 原样）。

    Args:
        value: 原始值。
        limit: 最大长度。

    Returns:
        str | None: 截断后的值。
    """
    if value is None:
        return None
    return value[:limit]


@dataclass(frozen=True)
class IssuedSession(BaseObject):
    """会话签发结果（双 token + 会话 id，供下发 cookie 与响应体）。"""

    access_token: str
    """访问令牌（紧凑 JWT）。"""

    refresh_token: str
    """刷新令牌（紧凑 JWT）。"""

    access_expires_in: int
    """access 有效期（秒）。"""

    refresh_expires_in: int
    """refresh 有效期（秒）。"""

    session_id: str
    """会话 id（= 双 token `jti`）。"""

    token_type: str = TOKEN_TYPE_BEARER
    """令牌类型（响应口径）。"""


class SessionIssuer(BaseObject):
    """会话签发作构件（双 token + 会话落库 + Redis 标记 + 多端上限）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        user_token_issuer: BaseUserTokenIssuer,
        session_security: BaseSessionSecurity,
        session_store: BaseSessionStore,
        session_settings: SessionSettings,
        session_service: SessionService,
    ) -> None:
        """初始化。

        Args:
            session: 认证服务租户库会话。
            uow: 工作单元（写事务）。
            user_token_issuer: 用户双 token 签发者。
            session_security: 会话安全原语（会话 id）。
            session_store: 会话标记存储。
            session_settings: 会话治理配置（多端上限）。
            session_service: 会话管理服务（多端上限作废）。
        """
        self._uow = uow
        self._repo = SessionRepository(session)
        self._issuer = user_token_issuer
        self._security = session_security
        self._store = session_store
        self._settings = session_settings
        self._session_service = session_service

    async def issue(
        self,
        *,
        user_id: int,
        tenant: str,
        ip: str | None,
        user_agent: str | None,
    ) -> IssuedSession:
        """签发会话：双 token 同会话 id + 会话落库 + Redis 标记。

        Args:
            user_id: 用户 ID（org 库 `sys_user.id`）。
            tenant: 租户编码。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。

        Returns:
            IssuedSession: 会话签发结果（含 refresh 原始票据）。
        """
        session_id = self._security.new_session_id()
        pair = await self._issuer.issue_pair(
            UserTokenSpec(subject=str(user_id), session_id=session_id, tenant_id=tenant)
        )
        await self._session_service.enforce_max_active(user_id, tenant=tenant, max_active=self._settings.max_active)
        await self._persist(
            session_id=session_id,
            user_id=user_id,
            refresh_token=pair.refresh_token,
            refresh_expires_in=pair.refresh_expires_in,
            tenant=tenant,
            ip=ip,
            user_agent=user_agent,
        )
        return IssuedSession(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            access_expires_in=pair.expires_in,
            refresh_expires_in=pair.refresh_expires_in,
            session_id=session_id,
            token_type=pair.token_type,
        )

    async def _persist(
        self,
        *,
        session_id: str,
        user_id: int,
        refresh_token: str,
        refresh_expires_in: int,
        tenant: str,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        """写入会话记录与 Redis 标记（同会话 id）。

        Args:
            session_id: 会话 id。
            user_id: 用户 ID。
            refresh_token: refresh 原始票据（仅哈希落库）。
            refresh_expires_in: refresh 有效期（秒）。
            tenant: 租户编码。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        async with self._uow.begin():
            await self._repo.create_session(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                login_at=now,
                expires_at=now + timedelta(seconds=refresh_expires_in),
                device=truncate_field(user_agent, 255),
                ip=truncate_field(ip, 64),
            )
        await self._store.save(
            session_id,
            {"user_id": user_id, "tenant": tenant, "ip": ip, "ua": user_agent},
            tenant=tenant,
            ttl=refresh_expires_in,
        )


def build_session_issuer(
    *,
    session: DbSession,
    uow: UnitOfWork,
    user_token_issuer: BaseUserTokenIssuer,
    session_security: BaseSessionSecurity,
    session_store: BaseSessionStore,
    session_settings: SessionSettings,
    realtime_publisher: BaseRealtimePublisher,
) -> SessionIssuer:
    """构造会话签发作构件（装配 `SessionService`；请求级）。

    Args:
        session: 认证服务租户库会话。
        uow: 工作单元（写事务）。
        user_token_issuer: 用户双 token 签发者。
        session_security: 会话安全原语。
        session_store: 会话标记存储。
        session_settings: 会话治理配置。
        realtime_publisher: 实时推送器（`session.revoked` 广播占位）。

    Returns:
        SessionIssuer: 会话签发作构件。
    """
    session_service = SessionService(
        session=session,
        uow=uow,
        security=session_security,
        store=session_store,
        publisher=realtime_publisher,
    )
    return SessionIssuer(
        session=session,
        uow=uow,
        user_token_issuer=user_token_issuer,
        session_security=session_security,
        session_store=session_store,
        session_settings=session_settings,
        session_service=session_service,
    )
