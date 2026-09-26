"""认证与身份服务 services 层：会话管理（列表 / 详情 / 强制踢出 / 多端上限）。

- 统一撤销原语 `revoke`：黑名单 + `revoked_at` 落库 + 删 Redis 标记 +（可选）广播占位；
  登出与踢出共用，保证三路径清理一致（先落库再清理，Redis 异常时标记 TTL 自然失效）。
- 多端上限 `enforce_max_active`：登录成功后按用户统计未撤销未过期会话，超限作废最旧。
- 管理编排 `list_sessions` / `detail` / `kick`：返回会话行 / 抛会话错误码（20011 / 20012 / 20013）。
- 事务边界：读 + 写在同一工作单元内（避免读后写触发会话重复开启事务），Redis 清理与广播在提交后执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import SessionExpiredError, SessionNotFoundError, SessionRevokedError
from bms_core.core.logging import get_logger
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_core.security.base import BaseSessionSecurity
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher, RealtimeEvent
from bms_identity.models.session import SysSession
from bms_identity.repositories.session import SessionRepository
from bms_identity.schemas.session import SESSION_REVOKED_EVENT, KickResult

REASON_KICK = "kick"
"""撤销原因：管理员强制踢出。"""

REASON_MAX_ACTIVE = "max_active"
"""撤销原因：多端上限自动作废最旧会话。"""

REASON_LOGOUT = "logout"
"""撤销原因：用户登出。"""

_LOGGER = get_logger("bms")


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _remaining_ttl(expires_at: datetime, now: datetime) -> int:
    """黑名单 TTL（覆盖 refresh 剩余生命周期；至少 1 秒）。

    Args:
        expires_at: 会话 refresh 过期时间。
        now: 当前 UTC 时间。

    Returns:
        int: TTL（秒，最小 1）。
    """
    return max(1, int((expires_at - now).total_seconds()))


@dataclass(frozen=True)
class SessionRevokeResult(BaseObject):
    """统一撤销原语结果（不存在 / 已撤销 / 本次撤销三态）。"""

    session_id: str
    found: bool
    already_revoked: bool


class SessionService(BaseObject):
    """会话管理服务（统一撤销原语 + 多端上限 + 列表 / 详情 / 踢出）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        security: BaseSessionSecurity,
        store: BaseSessionStore,
        publisher: BaseRealtimePublisher,
    ) -> None:
        """初始化。

        Args:
            session: 认证服务租户库会话。
            uow: 工作单元（写事务）。
            security: 会话安全原语（黑名单键）。
            store: 会话标记存储（黑名单 / 标记删除）。
            publisher: 实时推送器（`session.revoked` 广播占位）。
        """
        self._uow = uow
        self._repo = SessionRepository(session)
        self._security = security
        self._store = store
        self._publisher = publisher

    async def list_sessions(
        self,
        query: BasePageQuery,
        *,
        user_id: int | None = None,
        device: str | None = None,
        ip: str | None = None,
        login_from: datetime | None = None,
        login_to: datetime | None = None,
    ) -> tuple[list[SysSession], int]:
        """在线会话分页查询（仅未撤销未过期）。

        Args:
            query: 页码分页请求（含排序参数）。
            user_id: 用户 ID（精确，可选）。
            device: 设备标识（模糊，可选）。
            ip: 登录 IP（模糊，可选）。
            login_from: 登录时间下界（可选）。
            login_to: 登录时间上界（可选）。

        Returns:
            tuple[list[SysSession], int]: (当前页会话, 命中的在线会话总数)。
        """
        now = _utc_now()
        items = await self._repo.list_active(
            query, now=now, user_id=user_id, device=device, ip=ip, login_from=login_from, login_to=login_to
        )
        total = await self._repo.count_active(
            now=now, user_id=user_id, device=device, ip=ip, login_from=login_from, login_to=login_to
        )
        return items, total

    async def detail(self, session_id: str) -> SysSession:
        """会话详情（返回任意记录，含已撤销，供 revoked 状态查询）。

        Args:
            session_id: 会话 id。

        Returns:
            SysSession: 会话记录。

        Raises:
            SessionNotFoundError: 会话不存在（20011 / 404）。
        """
        record = await self._repo.get_by_session_id(session_id)
        if record is None:
            raise SessionNotFoundError("会话不存在")
        return record

    async def kick(self, session_id: str, *, tenant: str, actor: int | None = None) -> KickResult:
        """强制踢出：统一撤销原语 + 结构化日志留痕。

        Args:
            session_id: 会话 id。
            tenant: 租户编码（定位 Redis 标记键）。
            actor: 操作者用户 ID（缺失记 system）。

        Returns:
            KickResult: 踢出结果（会话 id / 撤销时间 / 原因）。

        Raises:
            SessionNotFoundError: 会话不存在（20011 / 404）。
            SessionRevokedError: 会话已撤销（重复踢出；20013）。
            SessionExpiredError: 会话已过期（20012）。
        """
        now = _utc_now()
        expired = False
        async with self._uow.begin():
            record = await self._repo.get_by_session_id(session_id)
            if record is None:
                raise SessionNotFoundError("会话不存在")
            if record.revoked_at is not None:
                raise SessionRevokedError("会话已撤销")
            expired = record.expires_at <= now
            if not expired:
                await self._repo.revoke(record.session_id, revoked_at=now)
        if expired:
            await self._cleanup(record, tenant=tenant, now=now)
            raise SessionExpiredError("会话已失效")
        await self._after_revoke(record, tenant=tenant, reason=REASON_KICK, broadcast=True, now=now)
        _LOGGER.info("会话强制踢出", session_id=session_id, tenant=tenant, actor=actor or "system", result="revoked")
        return KickResult(session_id=session_id, revoked_at=now, reason=REASON_KICK)

    async def revoke(
        self, session_id: str, *, tenant: str | None, reason: str, broadcast: bool = False
    ) -> SessionRevokeResult:
        """统一撤销原语（不抛）：黑名单 + 落库 + 删标记 +（可选）广播。

        登出 / 踢出 / 多端上限共用；不存在或已撤销不重复写（幂等）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码（定位 Redis 标记键）。
            reason: 撤销原因（`REASON_LOGOUT` / `REASON_KICK` / `REASON_MAX_ACTIVE`）。
            broadcast: 是否广播 `session.revoked`（踢出 / 超限 True，登出 False）。

        Returns:
            SessionRevokeResult: 撤销结果。
        """
        now = _utc_now()
        record: SysSession | None = None
        async with self._uow.begin():
            record = await self._repo.get_by_session_id(session_id)
            if record is None:
                return SessionRevokeResult(session_id=session_id, found=False, already_revoked=False)
            if record.revoked_at is not None:
                return SessionRevokeResult(session_id=session_id, found=True, already_revoked=True)
            await self._repo.revoke(record.session_id, revoked_at=now)
        await self._after_revoke(record, tenant=tenant, reason=reason, broadcast=broadcast, now=now)
        return SessionRevokeResult(session_id=session_id, found=True, already_revoked=False)

    async def enforce_max_active(self, user_id: int, *, tenant: str, max_active: int) -> list[str]:
        """多端上限：超限作废该用户最旧在线会话（为新建会话腾位）。

        Args:
            user_id: 用户 ID。
            tenant: 租户编码。
            max_active: 活跃会话上限。

        Returns:
            list[str]: 被作废的会话 id（未超限为空）。
        """
        now = _utc_now()
        targets: list[SysSession] = []
        async with self._uow.begin():
            active = await self._repo.list_active_by_user(user_id, now=now)
            overflow = len(active) - max_active + 1
            if overflow <= 0:
                return []
            targets = active[:overflow]
            for record in targets:
                await self._repo.revoke(record.session_id, revoked_at=now)
        for record in targets:
            await self._after_revoke(record, tenant=tenant, reason=REASON_MAX_ACTIVE, broadcast=True, now=now)
        return [record.session_id for record in targets]

    async def _after_revoke(
        self, record: SysSession, *, tenant: str | None, reason: str, broadcast: bool, now: datetime
    ) -> None:
        """撤销后处理：清理运行时标记 +（可选）广播占位（事务已提交）。

        Args:
            record: 已撤销的会话记录。
            tenant: 租户编码。
            reason: 撤销原因。
            broadcast: 是否广播。
            now: 撤销时间（UTC）。
        """
        await self._cleanup(record, tenant=tenant, now=now)
        if broadcast:
            await self._publisher.emit(
                RealtimeEvent(
                    event=SESSION_REVOKED_EVENT,
                    session_id=record.session_id,
                    data={
                        "session_id": record.session_id,
                        "user_id": record.user_id,
                        "reason": reason,
                        "revoked_at": now.isoformat(),
                    },
                )
            )

    async def _cleanup(self, record: SysSession, *, tenant: str | None, now: datetime) -> None:
        """清理运行时标记：refresh 入黑名单 + 删会话标记（尽力而为）。

        Args:
            record: 会话记录。
            tenant: 租户编码。
            now: 当前 UTC 时间。
        """
        ttl = _remaining_ttl(record.expires_at, now)
        await self._store.blacklist(self._security.blacklist_key(record.session_id), ttl=ttl)
        await self._store.delete(record.session_id, tenant=tenant)
