"""平台服务 services 层：用户完整域管理面（需求 07-2；《02_01 详细设计》§4）。

职责：用户 CRUD / 启停 / 软删除 / 重置密码 / 角色分配查看（只读）。

口径要点：

- **同库**：`sys_user` / `sys_user_role` / `sys_role` / `sys_account_lock` 全在 platform 服务租户库；
- **事务**：写操作一律 `async with self._uow.begin()` 包住「读 + 写」；
- **会话失效**：跨服务（identity 内部端点），一律在**事务提交之后**调用、**不阻断主流程**（返回布尔）；
- **保护规则**：内置管理员（`role_type != custom`）与当前操作人自身不可停用 / 删除（30009）；
  删除前校验角色分配引用（30011）；
- **事件**：`sys.user.created` / `sys.user.updated` / `sys.user.deleted` / `sys.user.password_reset`
  在写事务内经事务性发件箱发射（载荷不含组织字段）；
- **不含**：组织（部门 / 岗位）字段与关系（归 mdm，需求 `07-11`）、`locale` / `timezone`（个人中心）。
"""

from __future__ import annotations

import json
import re
import secrets
import string
from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    InternalError,
    ParamError,
    PasswordPolicyViolationError,
    PasswordReusedError,
    UsernameExistsError,
    UserNotFoundError,
    UserProtectedError,
    UserReferencedError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.outbox.base import BaseOutboxStore
from bms_core.password.base import BasePasswordPolicy
from bms_core.security.base import BasePasswordHasher
from bms_platform.models.role import ROLE_TYPE_CUSTOM, SysRole
from bms_platform.models.user import UNLOCK_MODE_AUTO, SysUser
from bms_platform.repositories.account_lock import AccountLockRepository
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.services.credentials import parse_password_history
from bms_platform.services.user_sessions import (
    REASON_PASSWORD_RESET,
    REASON_USER_DELETED,
    REASON_USER_DISABLED,
    UserSessionClient,
)

USER_CREATED_EVENT = "sys.user.created"
"""用户创建事件。"""

USER_UPDATED_EVENT = "sys.user.updated"
"""用户修改事件（基本资料 / 状态变更）。"""

USER_DELETED_EVENT = "sys.user.deleted"
"""用户删除（软删）事件。"""

USER_PASSWORD_RESET_EVENT = "sys.user.password_reset"
"""管理员重置密码事件。"""

USER_STATUSES: tuple[str, ...] = ("enabled", "disabled")
"""账号状态取值。"""

_GENERATED_PASSWORD_LENGTH = 16
"""后端随机初始密码长度（含大小写 / 数字 / 符号，逐次经密码策略校验）。"""

_GENERATED_PASSWORD_ATTEMPTS = 8
"""随机初始密码生成尝试次数（策略过严时提前失败，不静默降级）。"""

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_PHONE_PATTERN = r"^[+]?[0-9][0-9\-\s]{5,31}$"


def _utc_now() -> datetime:
    """当前 UTC 时间（naive；与库内时间列口径一致）。

    Returns:
        datetime: 当前 UTC naive 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _clean_optional(value: str | None) -> str | None:
    """清洗可空字符串：`None` 表示不改，空串表示清空。

    Args:
        value: 原始入参。

    Returns:
        str | None: 去空白后的值；空串 → None。
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _require_pattern(value: str | None, pattern: str, label: str) -> None:
    """校验非空联系方式格式。

    Args:
        value: 值（None / 空串不校验）。
        pattern: 正则表达式。
        label: 字段名（错误提示用）。

    Raises:
        ParamError: 格式非法（10001）。
    """
    if value and re.match(pattern, value) is None:
        raise ParamError(f"{label}格式非法")


def _user_payload(user: SysUser) -> ConcurrentStableDict[str, object]:
    """构造用户事件载荷（`sys.user.*`；不含组织字段）。

    Args:
        user: 用户记录。

    Returns:
        ConcurrentStableDict[str, object]: 事件载荷。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    payload.set("user_id", str(user.id))
    payload.set("username", user.username)
    payload.set("status", user.status)
    return payload


class UserAdminService(BaseFrameworkObject):
    """用户完整域管理面服务（CRUD / 启停 / 删除 / 重置密码 / 角色查看）。"""

    def __init__(
        self,
        session: DbSession,
        uow: UnitOfWork,
        users: UserRepository,
        user_roles: UserRoleRepository,
        roles: RoleRepository,
        account_locks: AccountLockRepository,
        hasher: BasePasswordHasher,
        policy: BasePasswordPolicy,
        outbox: BaseOutboxStore,
        sessions: UserSessionClient,
    ) -> None:
        """初始化。

        Args:
            session: 请求级会话（发件箱与业务数据同事务）。
            uow: 请求级工作单元。
            users: 用户仓储。
            user_roles: 角色 × 用户分配仓储。
            roles: 角色仓储（内置判定与角色查看）。
            account_locks: 账号锁定记录仓储（删除时闭锁）。
            hasher: 口令哈希器（PBKDF2）。
            policy: 密码策略（复杂度 / 历史）。
            outbox: 事务性发件箱存储（事件发布）。
            sessions: 用户会话失效客户端（跨服务）。
        """
        self._session = session
        self._uow = uow
        self._users = users
        self._user_roles = user_roles
        self._roles = roles
        self._account_locks = account_locks
        self._hasher = hasher
        self._policy = policy
        self._outbox = outbox
        self._sessions = sessions

    # ------------------------------------------------------------------ 查询

    async def get_user(self, user_id: int) -> SysUser:
        """取用户记录（不存在抛 30002）。

        Args:
            user_id: 用户主键。

        Returns:
            SysUser: 用户记录。

        Raises:
            UserNotFoundError: 用户不存在或已软删除（30002）。
        """
        return await self._require(user_id)

    async def list_user_roles(self, user_id: int) -> ConcurrentStableList[SysRole]:
        """取该用户直接绑定的角色（只读；维护归角色管理）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysRole]: 角色列表（按主键升序）。

        Raises:
            UserNotFoundError: 用户不存在或已软删除（30002）。
        """
        await self._require(user_id)
        role_ids = await self._user_roles.list_role_ids_by_user(user_id)
        if not role_ids:
            return ConcurrentStableList()
        return await self._roles.list_by_ids(ConcurrentStableSet(role_ids))

    # ------------------------------------------------------------------ 写操作

    async def create_user(
        self,
        *,
        username: str,
        name: str,
        password: str | None,
        pwd_reset_required: bool,
        email: str | None,
        phone: str | None,
        status: str,
    ) -> tuple[SysUser, str | None]:
        """新建用户（初始化密码可选；缺省随机生成并回传给调用方一次性展示）。

        Args:
            username: 登录账号（租户内唯一）。
            name: 昵称 / 显示名。
            password: 初始密码（None = 后端随机生成）。
            pwd_reset_required: 是否强制下次登录改密。
            email: 邮箱（可空）。
            phone: 手机号（可空）。
            status: 初始状态（enabled / disabled）。

        Returns:
            tuple[SysUser, str | None]: 用户记录与后端生成的初始密码（调用方指定密码时为 None）。

        Raises:
            UsernameExistsError: 用户名已被占用（30003）。
            ParamError: 状态 / 联系方式格式非法（10001）。
            PasswordPolicyViolationError: 指定密码不符合复杂度策略（30005）。
            InternalError: 随机初始密码未能通过策略（10002）。
        """
        normalized = username.strip()
        if status not in USER_STATUSES:
            raise ParamError(f"账号状态非法：{status}")
        clean_email = _clean_optional(email)
        clean_phone = _clean_optional(phone)
        _require_pattern(clean_email, _EMAIL_PATTERN, "邮箱")
        _require_pattern(clean_phone, _PHONE_PATTERN, "手机号")
        generated: str | None = None
        async with self._uow.begin():
            if await self._users.get_by_username(normalized) is not None:
                raise UsernameExistsError("用户名已存在")
            if password is None:
                initial = await self._generate_password(normalized)
                generated = initial
            else:
                initial = password
                await self._assert_password_policy(initial, username=normalized)
            user = await self._users.create(
                username=normalized,
                password_hash=self._hasher.hash(initial),
                name=name.strip(),
                status=status,
                pwd_changed_at=_utc_now(),
                pwd_reset_required=pwd_reset_required,
                email=clean_email,
                phone=clean_phone,
            )
            await self._emit(USER_CREATED_EVENT, user)
        return user, generated

    async def update_user(
        self,
        user_id: int,
        *,
        name: str | None,
        email: str | None,
        phone: str | None,
        version: int,
    ) -> SysUser:
        """修改用户基本资料（昵称 / 邮箱 / 手机；乐观锁比对）。

        Args:
            user_id: 用户主键。
            name: 昵称 / 显示名（None = 不改）。
            email: 邮箱（None = 不改；空串 = 清空）。
            phone: 手机号（None = 不改；空串 = 清空）。
            version: 客户端版本（乐观锁比对）。

        Returns:
            SysUser: 更新后的用户记录。

        Raises:
            UserNotFoundError: 用户不存在（30002）。
            ConcurrentConflictError: 乐观锁冲突（10003）。
            ParamError: 联系方式格式非法（10001）。
        """
        clean_email = _clean_optional(email)
        clean_phone = _clean_optional(phone)
        _require_pattern(clean_email, _EMAIL_PATTERN, "邮箱")
        _require_pattern(clean_phone, _PHONE_PATTERN, "手机号")
        async with self._uow.begin():
            user = await self._require(user_id)
            if version != user.version:
                raise ConcurrentConflictError("用户已被他人修改，请刷新后重试")
            if name is not None:
                user.name = name.strip()
            if email is not None:
                user.email = clean_email
            if phone is not None:
                user.phone = clean_phone
            await self._users.flush()
            await self._emit(USER_UPDATED_EVENT, user)
        return user

    async def update_status(self, user_id: int, *, status: str) -> tuple[SysUser, bool]:
        """启用 / 停用账号（停用即失效该用户全部会话）。

        Args:
            user_id: 用户主键。
            status: 目标状态（enabled / disabled）。

        Returns:
            tuple[SysUser, bool]: 用户记录与会话是否已失效（状态未变化时为 False）。

        Raises:
            ParamError: 状态取值非法（10001）。
            UserNotFoundError: 用户不存在（30002）。
            UserProtectedError: 内置管理员或操作人自身（30009）。
        """
        if status not in USER_STATUSES:
            raise ParamError(f"账号状态非法：{status}")
        async with self._uow.begin():
            user = await self._require(user_id)
            if status == user.status:
                return user, False
            if status == "disabled":
                await self._assert_not_protected(user, action="停用")
            user.status = status
            await self._users.flush()
            await self._emit(USER_UPDATED_EVENT, user)
        revoked = False
        if status == "disabled":
            revoked = await self._sessions.revoke_user_sessions(user_id, reason=REASON_USER_DISABLED)
        return user, revoked

    async def delete_user(self, user_id: int) -> bool:
        """软删除用户（引用校验 + 关闭未解锁锁定记录 + 失效全部会话）。

        Args:
            user_id: 用户主键。

        Returns:
            bool: 会话是否已失效。

        Raises:
            UserNotFoundError: 用户不存在（30002）。
            UserProtectedError: 内置管理员或操作人自身（30009）。
            UserReferencedError: 该用户仍存在角色分配（30011）。
        """
        async with self._uow.begin():
            user = await self._require(user_id)
            await self._assert_not_protected(user, action="删除")
            if await self._user_roles.count_by_user(user_id) > 0:
                raise UserReferencedError("用户仍存在角色分配，禁止删除")
            await self._users.soft_delete(user_id)
            await self._close_open_locks(user_id)
            await self._emit(USER_DELETED_EVENT, user)
        return await self._sessions.revoke_user_sessions(user_id, reason=REASON_USER_DELETED)

    async def reset_password(self, user_id: int, *, new_password: str, force_change: bool) -> bool:
        """管理员重置密码（策略校验 + 重哈希 + 写变更时间 / 历史 / 强制改密 + 失效全部会话）。

        Args:
            user_id: 用户主键。
            new_password: 新密码明文。
            force_change: 是否强制下次登录改密。

        Returns:
            bool: 会话是否已失效。

        Raises:
            UserNotFoundError: 用户不存在（30002）。
            PasswordPolicyViolationError: 新密码不符合复杂度策略（30005）。
            PasswordReusedError: 新密码与近 N 次历史密码重复（30006）。
        """
        async with self._uow.begin():
            user = await self._require(user_id)
            await self._assert_password_policy(new_password, username=user.username)
            history = parse_password_history(user.pwd_history)
            if await self._policy.reused(new_password, history=ConcurrentStableList([user.password_hash, *history])):
                raise PasswordReusedError("新密码与近 N 次历史密码重复")
            keep = await self._policy.history_count()
            history.add(user.password_hash)
            trimmed = history[-keep:] if keep > 0 else ConcurrentStableList()
            user.password_hash = self._hasher.hash(new_password)
            user.pwd_changed_at = _utc_now()
            user.pwd_history = json.dumps(list(trimmed), ensure_ascii=False)
            user.pwd_reset_required = force_change
            await self._users.flush()
            await self._emit(USER_PASSWORD_RESET_EVENT, user, payload_only_user_id=True)
        return await self._sessions.revoke_user_sessions(user_id, reason=REASON_PASSWORD_RESET)

    # ------------------------------------------------------------------ 内部

    async def _require(self, user_id: int) -> SysUser:
        """取用户记录（不存在抛 30002）。

        Args:
            user_id: 用户主键。

        Returns:
            SysUser: 用户记录。

        Raises:
            UserNotFoundError: 用户不存在或已软删除（30002）。
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("用户不存在")
        return user

    async def _assert_password_policy(self, password: str, *, username: str) -> None:
        """校验密码复杂度策略。

        Args:
            password: 密码明文。
            username: 登录账号（策略可禁含账号）。

        Raises:
            PasswordPolicyViolationError: 不符合复杂度策略（30005）。
        """
        violations = await self._policy.validate(password, username=username)
        if violations:
            raise PasswordPolicyViolationError("密码不符合复杂度策略", violations=tuple(violations))

    async def _assert_not_protected(self, user: SysUser, *, action: str) -> None:
        """校验内置管理员保护与「不得操作自身」。

        Args:
            user: 目标用户。
            action: 动作名（停用 / 删除；错误提示用）。

        Raises:
            UserProtectedError: 内置管理员或操作人自身（30009）。
        """
        actor = get_current_user_id()
        if actor is not None and actor == user.id:
            raise UserProtectedError(f"不得{action}当前操作人自身")
        role_ids = await self._user_roles.list_role_ids_by_user(user.id)
        if not role_ids:
            return
        roles = await self._roles.list_by_ids(ConcurrentStableSet(role_ids))
        for role in roles:
            if role.role_type != ROLE_TYPE_CUSTOM:
                raise UserProtectedError("内置管理员不可停用 / 删除")

    async def _close_open_locks(self, user_id: int) -> None:
        """关闭该用户全部未解锁锁定记录（删除用户时；`unlock_mode=auto` 留痕）。

        Args:
            user_id: 用户主键。
        """
        now = _utc_now()
        rows = await self._account_locks.list_open_by_user(user_id)
        for row in rows:
            await self._account_locks.update(
                row.id,
                unlock_at=now,
                unlock_by=get_current_user_id(),
                unlock_mode=UNLOCK_MODE_AUTO,
            )

    async def _generate_password(self, username: str) -> str:
        """生成随机初始密码（逐次经密码策略校验）。

        Args:
            username: 登录账号（策略可禁含账号）。

        Returns:
            str: 通过策略的随机密码。

        Raises:
            InternalError: 多次生成均未通过策略（10002；策略配置过严时快速失败）。
        """
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
        for _ in range(_GENERATED_PASSWORD_ATTEMPTS):
            candidate = "".join(secrets.choice(alphabet) for _ in range(_GENERATED_PASSWORD_LENGTH))
            if not await self._policy.validate(candidate, username=username):
                return candidate
        raise InternalError("随机初始密码未通过密码策略，请检查密码策略配置")

    async def _emit(self, event_type: str, user: SysUser, *, payload_only_user_id: bool = False) -> None:
        """在写事务内发射用户事件（事务性发件箱）。

        Args:
            event_type: 事件类型（`sys.user.*`）。
            user: 用户记录。
            payload_only_user_id: 载荷是否仅含 `user_id`（`password_reset` 口径）。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if payload_only_user_id:
            payload.set("user_id", str(user.id))
        else:
            payload = _user_payload(user)
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(event_type=event_type, payload=payload, aggregate_key=f"user:{user.id}"),
        )
