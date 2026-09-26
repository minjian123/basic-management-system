"""认证与身份服务 repositories 层：会话记录仓储（`sys_session`）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, func, select

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_identity.models.session import SysSession


class SessionRepository(BaseDbRepository[SysSession]):
    """会话仓储（`sys_session`）：创建 / 按会话 id 取数 / 轮换哈希 / 撤销 / 在线查询。"""

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

    async def list_active(
        self,
        query: BasePageQuery,
        *,
        now: datetime,
        user_id: int | None = None,
        device: str | None = None,
        ip: str | None = None,
        login_from: datetime | None = None,
        login_to: datetime | None = None,
    ) -> list[SysSession]:
        """在线会话分页查询（未撤销且未过期；筛选 + 统一排序）。

        Args:
            query: 页码分页请求（含排序参数）。
            now: 当前 UTC 时间（过期判定基准）。
            user_id: 用户 ID（精确，可选）。
            device: 设备标识（模糊，可选）。
            ip: 登录 IP（模糊，可选）。
            login_from: 登录时间下界（闭区间，可选）。
            login_to: 登录时间上界（闭区间，可选）。

        Returns:
            list[SysSession]: 当前页会话。
        """
        statement = self._apply_sort(
            self._select().where(*self._active_conditions(now, user_id, device, ip, login_from, login_to)),
            self._resolve_sort(query),
        )
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_active(
        self,
        *,
        now: datetime,
        user_id: int | None = None,
        device: str | None = None,
        ip: str | None = None,
        login_from: datetime | None = None,
        login_to: datetime | None = None,
    ) -> int:
        """在线会话总数（与 `list_active` 同筛选口径）。

        Args:
            now: 当前 UTC 时间（过期判定基准）。
            user_id: 用户 ID（精确，可选）。
            device: 设备标识（模糊，可选）。
            ip: 登录 IP（模糊，可选）。
            login_from: 登录时间下界（闭区间，可选）。
            login_to: 登录时间上界（闭区间，可选）。

        Returns:
            int: 命中的在线会话条数。
        """
        statement = (
            select(func.count())
            .select_from(SysSession)
            .where(
                *self._scope_where(),
                *self._active_conditions(now, user_id, device, ip, login_from, login_to),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def list_active_by_user(self, user_id: int, *, now: datetime) -> list[SysSession]:
        """取指定用户的在线会话（按登录时间升序、主键兜底；多端上限作废最旧用）。

        Args:
            user_id: 用户 ID。
            now: 当前 UTC 时间（过期判定基准）。

        Returns:
            list[SysSession]: 该用户在线会话（最旧在前）。
        """
        statement = (
            self._select()
            .where(self._column("user_id") == user_id, *self._active_conditions(now))
            .order_by(self._column("login_at").asc(), self._column("id").asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    def _active_conditions(
        self,
        now: datetime,
        user_id: int | None = None,
        device: str | None = None,
        ip: str | None = None,
        login_from: datetime | None = None,
        login_to: datetime | None = None,
    ) -> list[ColumnElement[bool]]:
        """在线会话筛选条件（未撤销 + 未过期 + 可选筛选）。

        Args:
            now: 当前 UTC 时间。
            user_id: 用户 ID（精确，可选）。
            device: 设备标识（模糊，可选）。
            ip: 登录 IP（模糊，可选）。
            login_from: 登录时间下界（可选）。
            login_to: 登录时间上界（可选）。

        Returns:
            list[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions: list[ColumnElement[bool]] = [
            self._column("revoked_at").is_(None),
            self._column("expires_at") > now,
        ]
        if user_id is not None:
            conditions.append(self._column("user_id") == user_id)
        if device:
            conditions.append(self._column("device").contains(device, autoescape=True))
        if ip:
            conditions.append(self._column("ip").contains(ip, autoescape=True))
        if login_from is not None:
            conditions.append(self._column("login_at") >= login_from)
        if login_to is not None:
            conditions.append(self._column("login_at") <= login_to)
        return conditions
