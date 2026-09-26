"""认证与身份服务 repositories 层：会话记录仓储（`sys_session`）。"""

from __future__ import annotations

from datetime import datetime

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_identity.models.session import SysSession


class SessionRepository(BaseDbRepository[SysSession]):
    """会话仓储（`sys_session`）：创建 / 按会话 id 取数 / 轮换哈希 / 撤销。"""

    model = SysSession
    sortable_fields = frozenset({"id", "login_at", "expires_at"})

    async def get_by_session_id(self, session_id: str) -> SysSession | None:
        """按会话 id 查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            session_id: 会话 id（JWT `jti`）。

        Returns:
            SysSession | None: 会话记录；不存在返回 None。
        """
        statement = self._select().where(self._column("session_id") == session_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create_session(
        self,
        *,
        session_id: str,
        user_id: int,
        refresh_token_hash: str,
        login_at: datetime,
        expires_at: datetime,
        device: str | None = None,
        ip: str | None = None,
    ) -> SysSession:
        """创建会话记录（`id` 与 `session_id` 同值 = 雪花会话 id）。

        Args:
            session_id: 会话 id（雪花十进制字符串；同时作为主键）。
            user_id: 用户 ID。
            refresh_token_hash: refresh token 哈希。
            login_at: 登录时间（UTC）。
            expires_at: refresh 过期时间（UTC）。
            device: 设备标识（可选）。
            ip: 登录 IP（可选）。

        Returns:
            SysSession: 新建会话记录。
        """
        item = SysSession(
            id=int(session_id),
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            device=device,
            ip=ip,
            login_at=login_at,
            expires_at=expires_at,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def update_refresh_hash(self, session_id: str, refresh_token_hash: str) -> SysSession | None:
        """更新会话的 refresh 哈希（刷新轮换）。

        Args:
            session_id: 会话 id。
            refresh_token_hash: 新 refresh token 哈希。

        Returns:
            SysSession | None: 更新后的记录；不存在返回 None。
        """
        item = await self.get_by_session_id(session_id)
        if item is None:
            return None
        return await self.update(item.id, refresh_token_hash=refresh_token_hash)

    async def revoke(self, session_id: str, *, revoked_at: datetime) -> bool:
        """撤销会话（置 `revoked_at`；幂等）。

        Args:
            session_id: 会话 id。
            revoked_at: 撤销时间（UTC）。

        Returns:
            bool: 命中并更新为 True；不存在为 False。
        """
        item = await self.get_by_session_id(session_id)
        if item is None:
            return False
        if item.revoked_at is None:
            await self.update(item.id, revoked_at=revoked_at)
        return True
