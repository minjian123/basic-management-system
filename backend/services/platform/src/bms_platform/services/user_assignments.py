"""平台服务 services 层：用户保存编排（分段全量覆盖 + 跨服务原子；需求 07-11 §5）。

口径：

- **分段全量覆盖**：`profile`（基础资料）/ `role_ids`（直接角色）/ `user_posts`（岗位）/ `user_depts`（部门）；
  分段为 `None` 表示**不参与**，空集表示清空；主要项须落在集合内。
- **两条路径**：`[transaction_manager].provider = "xa"` ⇒ TM 全局事务（platform 自身分支**进程内执行**、
  mdm 分支经参与端点 `POST /api/v1/txn/branches` 执行，全部 `PREPARED` 后由 TM 提交）；
  `provider = null`（dev / test 的 SQLite）⇒ **顺序提交**（platform 本地事务 → mdm 内部写通道），
  **不做反向补偿**（过渡期基线与屏障判据属废路径）。
- **跨服务副作用在提交之后**：停用账号的会话失效、角色分配变更的权限版本递增均为**提交后**尽力而为
  （失败不阻断、不影响已提交结果），避免把跨服务调用卷进两阶段窗口。
- **不含**：组织字段落 platform（`sys_user` 不落组织字段）、`locale` / `timezone`。
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING, cast

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RoleNotFoundError,
    RoleSubjectInvalidError,
    ServiceUnavailableError,
    TransactionUnavailableError,
    UserNotFoundError,
    UserProtectedError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.keys import TENANT_DB_KEY_PREFIX, build_tenant_db_key
from bms_core.db.tenant import current_tenant_context
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.version import permission_version_key
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    BaseTransactionManager,
    BaseTransactionParticipant,
    BranchOp,
    BranchSpec,
    GlobalTransaction,
)
from bms_platform import SERVICE_NAME
from bms_platform.models.role import ROLE_TYPE_CUSTOM, SysRole
from bms_platform.models.user import SysUser
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import (
    UserAssignmentDepts,
    UserAssignmentPosts,
    UserAssignmentProfile,
    UserAssignmentsRequest,
)
from bms_platform.services.user_sessions import REASON_USER_DISABLED, UserSessionClient
from bms_platform.services.users_admin import USER_STATUSES, USER_UPDATED_EVENT

if TYPE_CHECKING:
    from bms_core.db.session import DbSession

USER_ASSIGNMENTS_OP = "sys.user.assignments"
"""platform 侧分支操作名（分支处理器注册表键）。"""

ORG_SERVICE = "org"
"""组织域（mdm）服务键。"""

ORG_USER_POSTS_OP = "org.user-posts.assign"
"""mdm 分支操作名：用户-岗位全量覆盖 + 主要岗位。"""

ORG_USER_DEPTS_OP = "org.user-depts.assign"
"""mdm 分支操作名：用户-部门全量覆盖 + 主要部门。"""

ORG_INTERNAL_USER_POSTS_PATH = "/api/v1/org/internal/user-posts/{user_id}"
"""mdm 内部写通道：用户-岗位（`provider=null` 顺序提交路径）。"""

ORG_INTERNAL_USER_DEPTS_PATH = "/api/v1/org/internal/user-depts/{user_id}"
"""mdm 内部写通道：用户-部门（`provider=null` 顺序提交路径）。"""

BRANCH_ID_PLATFORM = "p"
"""platform 分支标识（同一全局事务内唯一，≤ 16 字符）。"""

BRANCH_ID_ORG = "m"
"""组织域分支标识。"""

BRANCH_EXECUTE_PATH = "/api/v1/txn/branches"
"""参与端点：分支执行路径。"""

SEGMENT_PROFILE = "profile"
"""分段名：用户基础资料。"""

SEGMENT_ROLES = "role_ids"
"""分段名：用户直接角色。"""

SEGMENT_POSTS = "user_posts"
"""分段名：用户-岗位。"""

SEGMENT_DEPTS = "user_depts"
"""分段名：用户-部门。"""

ENABLED_USER_STATUS = "enabled"
"""可分配用户状态（停用用户不可持有角色 / 岗位 / 部门分配）。"""

DISABLED_USER_STATUS = "disabled"
"""停用状态（停用即失效会话，受内置保护规则约束）。"""

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_PHONE_PATTERN = r"^[+]?[0-9][0-9\-\s]{5,31}$"


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


def _dedupe(values: ConcurrentStableList[int]) -> ConcurrentStableList[int]:
    """入参去重（保持首次出现序）。

    Args:
        values: 原始主键清单。

    Returns:
        ConcurrentStableList[int]: 去重后的清单。
    """
    seen: ConcurrentStableSet[int] = ConcurrentStableSet()
    result: ConcurrentStableList[int] = ConcurrentStableList()
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.add(item)
    return result


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


class UserAssignmentWriter(BaseFrameworkObject):
    """platform 侧写入器：用户基础资料 + 角色全量覆盖（**不含跨服务调用与提交后副作用**）。

    同一份写入逻辑同时服务于两条路径：XA 分支处理器（传入分支同步会话）与 `provider=null`
    顺序提交路径（传入请求会话）——**不复制业务逻辑**。
    """

    def __init__(
        self,
        session: DbSession,
        uow: UnitOfWork,
        users: UserRepository,
        user_roles: UserRoleRepository,
        roles: RoleRepository,
        outbox: BaseOutboxStore,
    ) -> None:
        """初始化。

        Args:
            session: 会话（分支同步会话或请求会话；发件箱与业务数据同事务）。
            uow: 工作单元（分支上下文内收敛为 SAVEPOINT）。
            users: 用户仓储。
            user_roles: 角色 × 用户分配仓储。
            roles: 角色仓储。
            outbox: 事务性发件箱存储。
        """
        self._session = session
        self._uow = uow
        self._users = users
        self._user_roles = user_roles
        self._roles = roles
        self._outbox = outbox

    async def write(
        self,
        *,
        user_id: int,
        profile: UserAssignmentProfile | None,
        role_ids: ConcurrentStableList[int] | None,
    ) -> SysUser:
        """执行 platform 侧分段写入（基础资料 → 角色）。

        Args:
            user_id: 用户主键。
            profile: 基础资料分段（`None` = 不改）。
            role_ids: 角色分段（`None` = 不改；空集 = 清空）。

        Returns:
            SysUser: 写入后的用户记录。

        Raises:
            UserNotFoundError: 用户不存在或已软删（30002）。
            UserProtectedError: 内置管理员或操作人自身（30009）。
            ConcurrentConflictError: 乐观锁冲突（10003）。
            RoleSubjectInvalidError: 停用用户参与分配段（30045）。
            RoleNotFoundError: 角色不存在。
            ParamError: 联系方式格式非法（10001）。
        """
        async with self._uow.begin():
            user = await self._require(user_id)
            if profile is not None:
                await self._apply_profile(user, profile)
            if role_ids is not None:
                await self._apply_roles(user, role_ids)
        return user

    async def _require(self, user_id: int) -> SysUser:
        """取用户记录（不存在即 30002）。

        Args:
            user_id: 用户主键。

        Returns:
            SysUser: 用户记录。

        Raises:
            UserNotFoundError: 用户不存在或已软删（30002）。
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("用户不存在")
        return user

    async def _apply_profile(self, user: SysUser, profile: UserAssignmentProfile) -> None:
        """应用基础资料分段（乐观锁 + 内置保护规则）。

        Args:
            user: 用户记录（就地修改）。
            profile: 基础资料分段。

        Raises:
            ConcurrentConflictError: 乐观锁冲突（10003）。
            UserProtectedError: 内置管理员或操作人自身（30009）。
            ParamError: 状态取值 / 联系方式格式非法（10001）。
        """
        if profile.version != user.version:
            raise ConcurrentConflictError("用户已被他人修改，请刷新后重试")
        if profile.status is not None:
            if profile.status not in USER_STATUSES:
                raise ParamError(f"账号状态非法：{profile.status}")
            if profile.status != user.status and profile.status == DISABLED_USER_STATUS:
                await self._assert_not_protected(user, action="停用")
            user.status = profile.status
        if profile.name is not None:
            user.name = profile.name.strip()
        if profile.email is not None:
            clean_email = _clean_optional(profile.email)
            _require_pattern(clean_email, _EMAIL_PATTERN, "邮箱")
            user.email = clean_email
        if profile.phone is not None:
            clean_phone = _clean_optional(profile.phone)
            _require_pattern(clean_phone, _PHONE_PATTERN, "手机号")
            user.phone = clean_phone
        await self._users.flush()
        await self._emit(USER_UPDATED_EVENT, user)

    async def _apply_roles(self, user: SysUser, role_ids: ConcurrentStableList[int]) -> None:
        """应用角色分段（全量覆盖：软删集合外 + 恢复 / 新建集合内）。

        Args:
            user: 用户记录（生效后状态用于「仅启用用户可分配」判定）。
            role_ids: 角色主键集合（全量）。

        Raises:
            RoleSubjectInvalidError: 停用用户参与分配（30045）。
            RoleNotFoundError: 角色不存在。
        """
        if user.status != ENABLED_USER_STATUS:
            raise RoleSubjectInvalidError("停用账号不可分配角色 / 岗位 / 部门，请先启用")
        normalized = _dedupe(role_ids)
        for role_id in normalized:
            if await self._roles.get(role_id) is None:
                raise RoleNotFoundError(f"角色不存在：{role_id}")
        await self._user_roles.soft_delete_by_user_except(user.id, ConcurrentStableSet(normalized))
        for role_id in normalized:
            if await self._user_roles.get_by_role_user(role_id, user.id) is not None:
                continue
            deleted = await self._user_roles.get_deleted_by_role_user(role_id, user.id)
            if deleted is not None:
                await self._user_roles.restore(deleted.id)
            else:
                await self._user_roles.create(role_id=role_id, user_id=user.id)

    async def _assert_not_protected(self, user: SysUser, *, action: str) -> None:
        """校验内置管理员保护与「不得操作自身」。

        Args:
            user: 目标用户。
            action: 动作名（错误提示用）。

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

    async def _emit(self, event_type: str, user: SysUser) -> None:
        """在写事务内发射用户事件（事务性发件箱）。

        Args:
            event_type: 事件类型（`sys.user.*`）。
            user: 用户记录。
        """
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(event_type=event_type, payload=_user_payload(user), aggregate_key=f"user:{user.id}"),
        )


class UserAssignmentsService(BaseFrameworkObject):
    """用户保存编排服务：分段校验 + 双路径（TM 全局事务 / 顺序提交）+ 提交后副作用。"""

    def __init__(
        self,
        *,
        writer: UserAssignmentWriter,
        user_roles: UserRoleRepository,
        roles: RoleRepository,
        users: UserRepository,
        sessions: UserSessionClient,
        cache: CacheRegion,
        manager: BaseTransactionManager,
        participant: BaseTransactionParticipant,
        client: BaseServiceClient,
        tenant_id: str | None,
    ) -> None:
        """初始化。

        Args:
            writer: platform 侧写入器（顺序提交路径使用）。
            user_roles: 角色 × 用户分配仓储（回读生效后角色）。
            roles: 角色仓储（回读生效后角色）。
            users: 用户仓储（回读生效后用户）。
            sessions: 用户会话失效客户端（提交后尽力而为）。
            cache: 缓存能力域（角色分配变更后权限版本递增）。
            manager: 事务管理器（`provider=null` 时为 Null 实现，`enabled` 为假）。
            participant: 事务参与方（platform 自身分支进程内执行）。
            client: 服务间调用客户端（mdm 分支执行 / 顺序提交内部写通道）。
            tenant_id: 当前租户标识（权限版本键作用域）。
        """
        self._writer = writer
        self._user_roles = user_roles
        self._roles = roles
        self._users = users
        self._sessions = sessions
        self._cache = cache
        self._manager = manager
        self._participant = participant
        self._client = client
        self._tenant_id = tenant_id

    async def apply(
        self,
        *,
        user_id: int,
        req: UserAssignmentsRequest,
        idempotency_key: str | None = None,
    ) -> tuple[SysUser, ConcurrentStableList[SysRole], ConcurrentStableList[str]]:
        """执行一次用户保存编排。

        Args:
            user_id: 用户主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键（透传给 mdm 内部写通道 / 分支载荷）。

        Returns:
            tuple[SysUser, ConcurrentStableList[SysRole], ConcurrentStableList[str]]:
                生效后用户、生效后直接角色清单、本次参与的分段名。

        Raises:
            ParamError: 未提供任何分段 / 主要项不在集合内（10001）。
            TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
            ServiceUnavailableError: 跨服务调用失败（10007）。
        """
        applied = collect_segments(req)
        if not applied:
            raise ParamError("至少需提供一段（profile / role_ids / user_posts / user_depts）")
        if self._manager.enabled:
            await self._apply_via_global_txn(user_id=user_id, req=req, idempotency_key=idempotency_key)
        else:
            await self._apply_sequential(user_id=user_id, req=req, idempotency_key=idempotency_key)
        await self._after_commit(user_id=user_id, req=req, applied=applied)
        user = await self._require_user(user_id)
        return user, await self._read_roles(user_id), applied

    async def _apply_via_global_txn(
        self,
        *,
        user_id: int,
        req: UserAssignmentsRequest,
        idempotency_key: str | None,
    ) -> None:
        """`provider=xa`：TM 全局事务路径（platform 分支进程内 + mdm 分支远端）。

        Args:
            user_id: 用户主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。

        Raises:
            TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
            ServiceUnavailableError: 分支执行调用失败（10007）。
        """
        platform_db_key = current_tenant_context().db_key
        org_db_key = build_tenant_db_key(platform_db_key[len(TENANT_DB_KEY_PREFIX) :], service=ORG_SERVICE)
        has_org = req.user_posts is not None or req.user_depts is not None
        specs: ConcurrentStableList[BranchSpec] = ConcurrentStableList()
        specs.add(BranchSpec(branch_id=BRANCH_ID_PLATFORM, service=SERVICE_NAME, db_key=platform_db_key))
        if has_org:
            specs.add(BranchSpec(branch_id=BRANCH_ID_ORG, service=ORG_SERVICE, db_key=org_db_key))
        txn = await self._manager.begin(caller_service=SERVICE_NAME, branches=tuple(specs))
        try:
            platform_xid = self._xid_of(txn, BRANCH_ID_PLATFORM)
            state = await self._participant.execute_branch(
                xid=platform_xid,
                db_key=platform_db_key,
                ops=(
                    BranchOp(
                        op=USER_ASSIGNMENTS_OP,
                        args=self._platform_args(user_id=user_id, req=req, idempotency_key=idempotency_key),
                    ),
                ),
            )
            if state != BRANCH_PREPARED:
                raise TransactionUnavailableError(f"platform 分支未就绪：{state}")
            if has_org:
                await self._execute_org_branches(
                    xid=self._xid_of(txn, BRANCH_ID_ORG),
                    db_key=org_db_key,
                    user_id=user_id,
                    req=req,
                    idempotency_key=idempotency_key,
                )
            await self._manager.commit(txn.global_txn_id)
        except Exception:
            await self._manager.rollback(txn.global_txn_id)
            raise

    async def _execute_org_branches(
        self,
        *,
        xid: str,
        db_key: str,
        user_id: int,
        req: UserAssignmentsRequest,
        idempotency_key: str | None,
    ) -> None:
        """执行 mdm 分支（岗位 + 部门合并为**同一分支的同一请求**，按序执行）。

        一个分支＝一条 XA 事务＝一条数据库连接，故两段必须一次请求提交（基座 `ops` 列表）。

        Args:
            xid: 组织域分支事务标识（TM 分配）。
            db_key: 组织域租户库键。
            user_id: 用户主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。

        Raises:
            TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
        """
        branch_ops = build_org_ops(user_id=user_id, req=req, idempotency_key=idempotency_key)
        if not branch_ops:
            return
        payload: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for op, args in branch_ops:
            entry: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            entry.set("op", op)
            entry.set("args", args)
            payload.add(entry)
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        body.set("xid", xid)
        body.set("db_key", db_key)
        body.set("ops", list(payload))
        response = await self._client.call(
            ServiceRequest(
                service=ORG_SERVICE,
                method="POST",
                path=BRANCH_EXECUTE_PATH,
                json_body=body,
                tenant_id=self._tenant_id,
            )
        )
        state = _branch_state(response)
        if state != BRANCH_PREPARED:
            raise TransactionUnavailableError(f"组织域分支未就绪：{state}")

    async def _apply_sequential(
        self,
        *,
        user_id: int,
        req: UserAssignmentsRequest,
        idempotency_key: str | None,
    ) -> None:
        """`provider=null`：顺序提交路径（platform 本地事务 → mdm 内部写通道；无补偿）。

        Args:
            user_id: 用户主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。
        """
        await self._writer.write(user_id=user_id, profile=req.profile, role_ids=req.role_ids)
        if req.user_posts is not None:
            await self._call_org_internal(
                path=ORG_INTERNAL_USER_POSTS_PATH.format(user_id=user_id),
                body=_posts_args(req.user_posts),
                idempotency_key=idempotency_key,
            )
        if req.user_depts is not None:
            await self._call_org_internal(
                path=ORG_INTERNAL_USER_DEPTS_PATH.format(user_id=user_id),
                body=_depts_args(req.user_depts),
                idempotency_key=idempotency_key,
            )

    async def _call_org_internal(
        self,
        *,
        path: str,
        body: ConcurrentStableDict[str, object],
        idempotency_key: str | None,
    ) -> None:
        """调 mdm 内部写通道（服务身份由客户端附上；幂等键经请求头透传）。

        Args:
            path: 目标路径。
            body: 请求体。
            idempotency_key: 业务幂等键（可空）。
        """
        headers: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        if idempotency_key:
            headers.set("Idempotency-Key", idempotency_key)
        await self._client.call(
            ServiceRequest(
                service=ORG_SERVICE,
                method="PUT",
                path=path,
                json_body=body,
                headers=headers,
                tenant_id=self._tenant_id,
            )
        )

    @staticmethod
    def _xid_of(txn: GlobalTransaction, branch_id: str) -> str:
        """取指定分支的 `xid`。

        Args:
            txn: 全局事务快照。
            branch_id: 分支标识。

        Returns:
            str: 分支 `xid`。

        Raises:
            TransactionUnavailableError: 分支缺失（10013）。
        """
        for branch in txn.branches:
            if branch.branch_id == branch_id:
                return branch.xid
        raise TransactionUnavailableError(f"全局事务缺少分支：{branch_id}")

    @staticmethod
    def _platform_args(
        *,
        user_id: int,
        req: UserAssignmentsRequest,
        idempotency_key: str | None,
    ) -> ConcurrentStableDict[str, object]:
        """构造 platform 分支载荷（分支处理器解包后调用同一写入器）。

        Args:
            user_id: 用户主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。

        Returns:
            ConcurrentStableDict[str, object]: 分支载荷。
        """
        args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        args.set("user_id", user_id)
        if req.profile is not None:
            profile: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            profile.set("name", req.profile.name)
            profile.set("email", req.profile.email)
            profile.set("phone", req.profile.phone)
            profile.set("status", req.profile.status)
            profile.set("version", req.profile.version)
            args.set("profile", profile)
        if req.role_ids is not None:
            args.set("role_ids", list(req.role_ids))
        if idempotency_key:
            args.set("idempotency_key", idempotency_key)
        return args

    async def _after_commit(
        self,
        *,
        user_id: int,
        req: UserAssignmentsRequest,
        applied: ConcurrentStableList[str],
    ) -> None:
        """提交后副作用（尽力而为、不阻断）：权限版本递增 + 停用账号会话失效。

        Args:
            user_id: 用户主键。
            req: 分段全量覆盖请求。
            applied: 本次参与的分段名。
        """
        if SEGMENT_ROLES in applied:
            await self._cache.aincrease(permission_version_key(self._tenant_id))
        if req.profile is not None and req.profile.status == DISABLED_USER_STATUS:
            # 提交后最佳努力：会话失效失败不影响已提交结果（跨服务不阻断主流程）。
            with contextlib.suppress(Exception):
                await self._sessions.revoke_user_sessions(user_id, reason=REASON_USER_DISABLED)

    async def _require_user(self, user_id: int) -> SysUser:
        """回读生效后用户记录。

        Args:
            user_id: 用户主键。

        Returns:
            SysUser: 用户记录。

        Raises:
            UserNotFoundError: 用户不存在（30002）。
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("用户不存在")
        return user

    async def _read_roles(self, user_id: int) -> ConcurrentStableList[SysRole]:
        """回读生效后直接角色清单。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysRole]: 角色清单（按主键升序）。
        """
        role_ids = await self._user_roles.list_role_ids_by_user(user_id)
        if not role_ids:
            return ConcurrentStableList()
        return await self._roles.list_by_ids(ConcurrentStableSet(role_ids))


def _posts_args(
    posts: UserAssignmentPosts,
    *,
    user_id: int | None = None,
    idempotency_key: str | None = None,
) -> ConcurrentStableDict[str, object]:
    """构造岗位段载荷（分支 op 与内部写通道共用）。

    Args:
        posts: 岗位分段。
        user_id: 用户主键（分支载荷用；内部写通道经路径承载时为空）。
        idempotency_key: 业务幂等键（可空）。

    Returns:
        ConcurrentStableDict[str, object]: 载荷。
    """
    args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if user_id is not None:
        args.set("user_id", user_id)
    args.set("post_ids", list(posts.post_ids))
    args.set("primary_post_id", posts.primary_post_id)
    if idempotency_key:
        args.set("idempotency_key", idempotency_key)
    return args


def _depts_args(
    depts: UserAssignmentDepts,
    *,
    user_id: int | None = None,
    idempotency_key: str | None = None,
) -> ConcurrentStableDict[str, object]:
    """构造部门段载荷（分支 op 与内部写通道共用）。

    Args:
        depts: 部门分段。
        user_id: 用户主键（分支载荷用；内部写通道经路径承载时为空）。
        idempotency_key: 业务幂等键（可空）。

    Returns:
        ConcurrentStableDict[str, object]: 载荷。
    """
    args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if user_id is not None:
        args.set("user_id", user_id)
    args.set("dept_ids", list(depts.dept_ids))
    args.set("primary_dept_id", depts.primary_dept_id)
    if idempotency_key:
        args.set("idempotency_key", idempotency_key)
    return args


def _assert_primary(posts: UserAssignmentPosts) -> None:
    """校验主要岗位落在岗位集合内。

    Args:
        posts: 岗位分段。

    Raises:
        ParamError: 主要岗位不在集合内（10001）。
    """
    if posts.primary_post_id is not None and posts.primary_post_id not in tuple(posts.post_ids):
        raise ParamError("主要岗位须在岗位集合内")


def _assert_primary_dept(depts: UserAssignmentDepts) -> None:
    """校验主要部门落在部门集合内。

    Args:
        depts: 部门分段。

    Raises:
        ParamError: 主要部门不在集合内（10001）。
    """
    if depts.primary_dept_id is not None and depts.primary_dept_id not in tuple(depts.dept_ids):
        raise ParamError("主要部门须在部门集合内")


def collect_segments(req: UserAssignmentsRequest) -> ConcurrentStableList[str]:
    """收集本次参与的分段名（并校验主要项落在集合内）。

    Args:
        req: 分段全量覆盖请求。

    Returns:
        ConcurrentStableList[str]: 分段名清单（登记序）。

    Raises:
        ParamError: 主要项不在集合内（10001）。
    """
    applied: ConcurrentStableList[str] = ConcurrentStableList()
    if req.profile is not None:
        applied.add(SEGMENT_PROFILE)
    if req.role_ids is not None:
        applied.add(SEGMENT_ROLES)
    if req.user_posts is not None:
        _assert_primary(req.user_posts)
        applied.add(SEGMENT_POSTS)
    if req.user_depts is not None:
        _assert_primary_dept(req.user_depts)
        applied.add(SEGMENT_DEPTS)
    return applied


def build_org_ops(
    *,
    user_id: int,
    req: UserAssignmentsRequest,
    idempotency_key: str | None,
) -> ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]]:
    """构造组织域**分支**操作清单（岗位 / 部门各一 op；同一分支内按序执行）。

    Args:
        user_id: 用户主键。
        req: 分段全量覆盖请求。
        idempotency_key: 业务幂等键。

    Returns:
        ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]]: (op, 载荷) 清单。
    """
    ops: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()
    if req.user_posts is not None:
        posts_args = _posts_args(req.user_posts, user_id=user_id, idempotency_key=idempotency_key)
        ops.add((ORG_USER_POSTS_OP, posts_args))
    if req.user_depts is not None:
        depts_args = _depts_args(req.user_depts, user_id=user_id, idempotency_key=idempotency_key)
        ops.add((ORG_USER_DEPTS_OP, depts_args))
    return ops


def _branch_state(response: object) -> str:
    """从参与端点响应中取分支状态（非 2xx / 业务非 0 即失败）。

    Args:
        response: 服务间调用响应。

    Returns:
        str: 分支状态（`prepared` / `rejected`）。

    Raises:
        ServiceUnavailableError: 传输 / 业务失败（10007 / 503）。
    """
    status_code = cast("int", getattr(response, "status_code", 0))
    if status_code // 100 != 2:
        raise ServiceUnavailableError(f"分支执行失败：HTTP {status_code}")
    payload = cast("object", getattr(response, "payload", lambda: None)())
    if not isinstance(payload, dict):
        raise ServiceUnavailableError("分支执行响应非法（非 JSON 对象）")
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        raise ServiceUnavailableError(f"分支执行业务失败：{body.get('message')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise ServiceUnavailableError("分支执行响应缺少 data")
    return str(cast("dict[str, object]", data).get("state", ""))
