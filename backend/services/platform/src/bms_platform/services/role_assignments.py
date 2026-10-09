"""平台服务 services 层：角色保存编排（分段全量覆盖 + 跨服务原子；需求 07-11 §5）。

与用户侧 `user_assignments.py` 对称（角色侧切片）：

- **分段全量覆盖**：`role`（角色本体）/ `user_ids`（角色 × 用户分配）/ `role_posts`（岗位）/
  `role_depts`（部门）；分段为 `None` 表示**不参与**，空集表示清空；角色侧**无主要项**语义。
- **两条路径**：`[transaction_manager].provider = "xa"` ⇒ TM 全局事务（platform 自身分支**进程内执行**、
  mdm 分支经参与端点 `POST /api/v1/txn/branches` 执行，全部 `PREPARED` 后由 TM 提交）；
  `provider = null`（dev / test 的 SQLite）⇒ **顺序提交**（platform 本地事务 → mdm 内部写通道），
  **不做反向补偿、不做一致性屏障**（过渡期基线与屏障判据属废路径）。
- **跨服务副作用在提交之后**：角色 / 角色分配变更的权限版本递增为**提交后**尽力而为（失败不阻断、
  不影响已提交结果），避免把跨服务调用卷进两阶段窗口。
- **不含**：权限配置（菜单 / 表单 / 字段 / 数据）写接口（各自既有端点，不并入本编排）。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RoleCodeExistsError,
    RoleNotFoundError,
    RoleProtectedError,
    RoleSubjectInvalidError,
    ServiceUnavailableError,
    TransactionUnavailableError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.keys import TENANT_DB_KEY_PREFIX, build_tenant_db_key
from bms_core.db.tenant import current_tenant_context
from bms_core.db.unit_of_work import UnitOfWork
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
from bms_platform.schemas.role import (
    RoleAssignmentDepts,
    RoleAssignmentPosts,
    RoleAssignmentProfile,
    RoleAssignmentsRequest,
)
from bms_platform.services.role import ROLE_STATUSES, resolve_role_code_pattern

if TYPE_CHECKING:
    from bms_core.db.session import DbSession

ROLE_ASSIGNMENTS_OP = "sys.role.assignments"
"""platform 侧分支操作名（分支处理器注册表键）。"""

ORG_SERVICE = "org"
"""组织域（mdm）服务键。"""

ORG_ROLE_POSTS_OP = "org.role-posts.assign"
"""mdm 分支操作名：角色-岗位全量覆盖。"""

ORG_ROLE_DEPTS_OP = "org.role-depts.assign"
"""mdm 分支操作名：角色-部门全量覆盖。"""

ORG_INTERNAL_ROLE_POSTS_PATH = "/api/v1/org/internal/role-posts/{role_id}"
"""mdm 内部写通道：角色-岗位（`provider=null` 顺序提交路径）。"""

ORG_INTERNAL_ROLE_DEPTS_PATH = "/api/v1/org/internal/role-depts/{role_id}"
"""mdm 内部写通道：角色-部门（`provider=null` 顺序提交路径）。"""

BRANCH_ID_PLATFORM = "p"
"""platform 分支标识（同一全局事务内唯一，≤ 16 字符）。"""

BRANCH_ID_ORG = "m"
"""组织域分支标识。"""

BRANCH_EXECUTE_PATH = "/api/v1/txn/branches"
"""参与端点：分支执行路径。"""

SEGMENT_ROLE = "role"
"""分段名：角色本体。"""

SEGMENT_USER_IDS = "user_ids"
"""分段名：角色 × 用户分配。"""

SEGMENT_ROLE_POSTS = "role_posts"
"""分段名：角色-岗位。"""

SEGMENT_ROLE_DEPTS = "role_depts"
"""分段名：角色-部门。"""

ENABLED_USER_STATUS = "enabled"
"""可分配用户状态（停用用户不可被分配角色）。"""


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


class RoleAssignmentWriter(BaseFrameworkObject):
    """platform 侧写入器：角色本体 + 角色 × 用户全量覆盖（**不含跨服务调用与提交后副作用**）。

    同一份写入逻辑同时服务于两条路径：XA 分支处理器（传入分支同步会话）与 `provider=null`
    顺序提交路径（传入请求会话）——**不复制业务逻辑**。
    """

    def __init__(
        self,
        session: DbSession,
        uow: UnitOfWork,
        roles: RoleRepository,
        user_roles: UserRoleRepository,
        users: UserRepository,
        config: BaseConfigSource,
    ) -> None:
        """初始化。

        Args:
            session: 会话（分支同步会话或请求会话）。
            uow: 工作单元（分支上下文内收敛为 SAVEPOINT）。
            roles: 角色仓储。
            user_roles: 角色 × 用户分配仓储。
            users: 用户仓储（同库；分配主体有效性校验）。
            config: 系统参数取数（角色码格式）。
        """
        self._session = session
        self._uow = uow
        self._roles = roles
        self._user_roles = user_roles
        self._users = users
        self._config = config

    async def write(
        self,
        *,
        role_id: int,
        profile: RoleAssignmentProfile | None,
        user_ids: ConcurrentStableList[int] | None,
    ) -> SysRole:
        """执行 platform 侧分段写入（角色本体 → 角色 × 用户）。

        Args:
            role_id: 角色主键。
            profile: 角色本体分段（`None` = 不改）。
            user_ids: 角色 × 用户分段（`None` = 不改；空集 = 清空）。

        Returns:
            SysRole: 写入后的角色记录。

        Raises:
            RoleNotFoundError: 角色不存在（30041）。
            RoleCodeExistsError: 角色码已被占用（30042）。
            RoleProtectedError: 内置角色被停用 / 启用（30043）。
            RoleSubjectInvalidError: 存在不存在 / 已停用的用户（30045）。
            ConcurrentConflictError: 乐观锁冲突（10003）。
            ParamError: 角色码 / 状态非法（10001）。
        """
        async with self._uow.begin():
            role = await self._require(role_id)
            if profile is not None:
                await self._apply_profile(role, profile)
            if user_ids is not None:
                await self._apply_users(role, user_ids)
        return role

    async def _require(self, role_id: int) -> SysRole:
        """取角色记录（不存在即 30041）。

        Args:
            role_id: 角色主键。

        Returns:
            SysRole: 角色记录。

        Raises:
            RoleNotFoundError: 角色不存在（30041）。
        """
        role = await self._roles.get(role_id)
        if role is None:
            raise RoleNotFoundError()
        return role

    async def _apply_profile(self, role: SysRole, profile: RoleAssignmentProfile) -> None:
        """应用角色本体分段（乐观锁 + 内置保护 + 角色码唯一）。

        Args:
            role: 角色记录（就地修改）。
            profile: 角色本体分段。

        Raises:
            ConcurrentConflictError: 乐观锁冲突（10003）。
            RoleProtectedError: 内置角色被停用 / 启用（30043）。
            RoleCodeExistsError: 角色码已被占用（30042）。
            ParamError: 角色码 / 状态非法（10001）。
        """
        if profile.version != role.version:
            raise ConcurrentConflictError("角色已被他人修改，请刷新后重试")
        if profile.status is not None:
            if profile.status not in ROLE_STATUSES:
                raise ParamError(f"角色状态非法：{profile.status}")
            if profile.status != role.status and role.role_type != ROLE_TYPE_CUSTOM:
                raise RoleProtectedError("内置角色不可停用 / 启用")
            role.status = profile.status
        if profile.code is not None:
            pattern = await resolve_role_code_pattern(self._config)
            normalized = profile.code.strip()
            if re.fullmatch(pattern, normalized) is None:
                raise ParamError("角色码格式非法（小写字母开头，2~32 位字母 / 数字 / 下划线 / 连字符）")
            if normalized != role.code:
                existing = await self._roles.get_by_code(normalized)
                if existing is not None and existing.id != role.id:
                    raise RoleCodeExistsError()
                role.code = normalized
        if profile.name is not None:
            role.name = profile.name.strip()
        await self._roles.flush()

    async def _apply_users(self, role: SysRole, user_ids: ConcurrentStableList[int]) -> None:
        """应用角色 × 用户分段（全量覆盖：软删集合外 + 恢复 / 新建集合内）。

        Args:
            role: 角色记录。
            user_ids: 用户主键集合（全量）。

        Raises:
            RoleSubjectInvalidError: 存在不存在 / 已停用的用户（30045）。
        """
        normalized = _dedupe(user_ids)
        for user_id in normalized:
            user = await self._users.get_by_id(user_id)
            if user is None or user.status != ENABLED_USER_STATUS:
                raise RoleSubjectInvalidError(f"用户不存在或已停用：{user_id}")
        await self._user_roles.soft_delete_by_role_except(role.id, ConcurrentStableSet(normalized))
        for user_id in normalized:
            if await self._user_roles.get_by_role_user(role.id, user_id) is not None:
                continue
            deleted = await self._user_roles.get_deleted_by_role_user(role.id, user_id)
            if deleted is not None:
                await self._user_roles.restore(deleted.id)
            else:
                await self._user_roles.create(role_id=role.id, user_id=user_id)


class RoleAssignmentsService(BaseFrameworkObject):
    """角色保存编排服务：分段校验 + 双路径（TM 全局事务 / 顺序提交）+ 提交后版本递增。"""

    def __init__(
        self,
        *,
        writer: RoleAssignmentWriter,
        roles: RoleRepository,
        users: UserRepository,
        user_roles: UserRoleRepository,
        cache: CacheRegion,
        manager: BaseTransactionManager,
        participant: BaseTransactionParticipant,
        client: BaseServiceClient,
        tenant_id: str | None,
    ) -> None:
        """初始化。

        Args:
            writer: platform 侧写入器（顺序提交路径使用）。
            roles: 角色仓储（回读生效后角色）。
            users: 用户仓储（回读生效后用户清单）。
            user_roles: 角色 × 用户分配仓储（回读生效后清单）。
            cache: 缓存能力域（角色 / 分配变更后权限版本递增）。
            manager: 事务管理器（`provider=null` 时为 Null 实现，`enabled` 为假）。
            participant: 事务参与方（platform 自身分支进程内执行）。
            client: 服务间调用客户端（mdm 分支执行 / 顺序提交内部写通道）。
            tenant_id: 当前租户标识（权限版本键作用域）。
        """
        self._writer = writer
        self._roles = roles
        self._users = users
        self._user_roles = user_roles
        self._cache = cache
        self._manager = manager
        self._participant = participant
        self._client = client
        self._tenant_id = tenant_id

    async def apply(
        self,
        *,
        role_id: int,
        req: RoleAssignmentsRequest,
        idempotency_key: str | None = None,
    ) -> tuple[SysRole, ConcurrentStableList[SysUser], ConcurrentStableList[str]]:
        """执行一次角色保存编排。

        Args:
            role_id: 角色主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键（透传给 mdm 内部写通道 / 分支载荷）。

        Returns:
            tuple[SysRole, ConcurrentStableList[SysUser], ConcurrentStableList[str]]:
                生效后角色、生效后已分配用户清单、本次参与的分段名。

        Raises:
            ParamError: 未提供任何分段（10001）。
            TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
            ServiceUnavailableError: 跨服务调用失败（10007）。
        """
        applied = collect_segments(req)
        if not applied:
            raise ParamError("至少需提供一段（role / user_ids / role_posts / role_depts）")
        if self._manager.enabled:
            await self._apply_via_global_txn(role_id=role_id, req=req, idempotency_key=idempotency_key)
        else:
            await self._apply_sequential(role_id=role_id, req=req, idempotency_key=idempotency_key)
        await self._after_commit(applied=applied)
        role = await self._require_role(role_id)
        return role, await self._read_users(role_id), applied

    async def _apply_via_global_txn(
        self,
        *,
        role_id: int,
        req: RoleAssignmentsRequest,
        idempotency_key: str | None,
    ) -> None:
        """`provider=xa`：TM 全局事务路径（platform 分支进程内 + mdm 分支远端）。

        Args:
            role_id: 角色主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。

        Raises:
            TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
            ServiceUnavailableError: 分支执行调用失败（10007）。
        """
        platform_db_key = current_tenant_context().db_key
        org_db_key = build_tenant_db_key(platform_db_key[len(TENANT_DB_KEY_PREFIX) :], service=ORG_SERVICE)
        has_org = req.role_posts is not None or req.role_depts is not None
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
                        op=ROLE_ASSIGNMENTS_OP,
                        args=self._platform_args(role_id=role_id, req=req, idempotency_key=idempotency_key),
                    ),
                ),
            )
            if state != BRANCH_PREPARED:
                raise TransactionUnavailableError(f"platform 分支未就绪：{state}")
            if has_org:
                await self._execute_org_branches(
                    xid=self._xid_of(txn, BRANCH_ID_ORG),
                    db_key=org_db_key,
                    role_id=role_id,
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
        role_id: int,
        req: RoleAssignmentsRequest,
        idempotency_key: str | None,
    ) -> None:
        """执行 mdm 分支（岗位 + 部门合并为**同一分支的同一请求**，按序执行）。

        一个分支＝一条 XA 事务＝一条数据库连接，故两段必须一次请求提交（基座 `ops` 列表）。

        Args:
            xid: 组织域分支事务标识（TM 分配）。
            db_key: 组织域租户库键。
            role_id: 角色主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。

        Raises:
            TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
        """
        branch_ops = build_org_ops(role_id=role_id, req=req, idempotency_key=idempotency_key)
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
        role_id: int,
        req: RoleAssignmentsRequest,
        idempotency_key: str | None,
    ) -> None:
        """`provider=null`：顺序提交路径（platform 本地事务 → mdm 内部写通道；无补偿）。

        Args:
            role_id: 角色主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。
        """
        await self._writer.write(role_id=role_id, profile=req.role, user_ids=req.user_ids)
        if req.role_posts is not None:
            await self._call_org_internal(
                path=ORG_INTERNAL_ROLE_POSTS_PATH.format(role_id=role_id),
                body=_posts_args(req.role_posts, idempotency_key=idempotency_key),
                idempotency_key=idempotency_key,
            )
        if req.role_depts is not None:
            await self._call_org_internal(
                path=ORG_INTERNAL_ROLE_DEPTS_PATH.format(role_id=role_id),
                body=_depts_args(req.role_depts, idempotency_key=idempotency_key),
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
        role_id: int,
        req: RoleAssignmentsRequest,
        idempotency_key: str | None,
    ) -> ConcurrentStableDict[str, object]:
        """构造 platform 分支载荷（分支处理器解包后调用同一写入器）。

        Args:
            role_id: 角色主键。
            req: 分段全量覆盖请求。
            idempotency_key: 业务幂等键。

        Returns:
            ConcurrentStableDict[str, object]: 分支载荷。
        """
        args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        args.set("role_id", role_id)
        if req.role is not None:
            role: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            role.set("code", req.role.code)
            role.set("name", req.role.name)
            role.set("status", req.role.status)
            role.set("version", req.role.version)
            args.set("role", role)
        if req.user_ids is not None:
            args.set("user_ids", list(req.user_ids))
        if idempotency_key:
            args.set("idempotency_key", idempotency_key)
        return args

    async def _after_commit(self, *, applied: ConcurrentStableList[str]) -> None:
        """提交后副作用（尽力而为、不阻断）：角色 / 角色分配变更权限版本一次递增。

        Args:
            applied: 本次参与的分段名。
        """
        if SEGMENT_ROLE in applied or SEGMENT_USER_IDS in applied:
            await self._cache.aincrease(permission_version_key(self._tenant_id))

    async def _require_role(self, role_id: int) -> SysRole:
        """回读生效后角色记录。

        Args:
            role_id: 角色主键。

        Returns:
            SysRole: 角色记录。

        Raises:
            RoleNotFoundError: 角色不存在（30041）。
        """
        role = await self._roles.get(role_id)
        if role is None:
            raise RoleNotFoundError()
        return role

    async def _read_users(self, role_id: int) -> ConcurrentStableList[SysUser]:
        """回读生效后已分配用户清单。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysUser]: 用户清单（按分配行主键升序）。
        """
        user_ids = await self._user_roles.list_user_ids_by_role(role_id)
        if not user_ids:
            return ConcurrentStableList()
        users = await self._users.list_by_ids(ConcurrentStableList(user_ids))
        by_id = ConcurrentStableDict[int, SysUser]({user.id: user for user in users})
        return ConcurrentStableList(by_id[user_id] for user_id in user_ids if user_id in by_id)


def _posts_args(
    posts: RoleAssignmentPosts,
    *,
    role_id: int | None = None,
    idempotency_key: str | None = None,
) -> ConcurrentStableDict[str, object]:
    """构造岗位段载荷（分支 op 与内部写通道共用）。

    Args:
        posts: 岗位分段。
        role_id: 角色主键（分支载荷用；内部写通道经路径承载时为空）。
        idempotency_key: 业务幂等键（可空）。

    Returns:
        ConcurrentStableDict[str, object]: 载荷。
    """
    args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if role_id is not None:
        args.set("role_id", role_id)
    args.set("post_ids", list(posts.post_ids))
    if idempotency_key:
        args.set("idempotency_key", idempotency_key)
    return args


def _depts_args(
    depts: RoleAssignmentDepts,
    *,
    role_id: int | None = None,
    idempotency_key: str | None = None,
) -> ConcurrentStableDict[str, object]:
    """构造部门段载荷（分支 op 与内部写通道共用）。

    Args:
        depts: 部门分段。
        role_id: 角色主键（分支载荷用；内部写通道经路径承载时为空）。
        idempotency_key: 业务幂等键（可空）。

    Returns:
        ConcurrentStableDict[str, object]: 载荷。
    """
    args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if role_id is not None:
        args.set("role_id", role_id)
    args.set("dept_ids", list(depts.dept_ids))
    if idempotency_key:
        args.set("idempotency_key", idempotency_key)
    return args


def collect_segments(req: RoleAssignmentsRequest) -> ConcurrentStableList[str]:
    """收集本次参与的分段名。

    Args:
        req: 分段全量覆盖请求。

    Returns:
        ConcurrentStableList[str]: 分段名清单（登记序）。
    """
    applied: ConcurrentStableList[str] = ConcurrentStableList()
    if req.role is not None:
        applied.add(SEGMENT_ROLE)
    if req.user_ids is not None:
        applied.add(SEGMENT_USER_IDS)
    if req.role_posts is not None:
        applied.add(SEGMENT_ROLE_POSTS)
    if req.role_depts is not None:
        applied.add(SEGMENT_ROLE_DEPTS)
    return applied


def build_org_ops(
    *,
    role_id: int,
    req: RoleAssignmentsRequest,
    idempotency_key: str | None,
) -> ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]]:
    """构造组织域**分支**操作清单（岗位 / 部门各一 op；同一分支内按序执行）。

    Args:
        role_id: 角色主键。
        req: 分段全量覆盖请求。
        idempotency_key: 业务幂等键。

    Returns:
        ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]]: (op, 载荷) 清单。
    """
    ops: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()
    if req.role_posts is not None:
        ops.add((ORG_ROLE_POSTS_OP, _posts_args(req.role_posts, role_id=role_id, idempotency_key=idempotency_key)))
    if req.role_depts is not None:
        ops.add((ORG_ROLE_DEPTS_OP, _depts_args(req.role_depts, role_id=role_id, idempotency_key=idempotency_key)))
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
