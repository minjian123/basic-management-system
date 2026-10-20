"""用户保存编排写入器与 XA 分支路径用例（`02_02/_02` 补齐，Kiwi 2278）。

补齐 `services/user_assignments.py` 未覆盖面：

- **写入器**（`UserAssignmentWriter`）：基础资料分段（乐观锁 / 状态合法性 / 联系方式格式 / 内置保护）、
  角色分段全量覆盖（软删集合外 + 恢复 / 新建）、`sys.user.updated` 事件发射；
- **XA 全局事务路径**：平台分支进程内执行 + 组织域分支远端执行 + 提交 / 回滚，分支未就绪与
  分支状态解析失败分支；
- **纯函数载荷**：`_platform_args` / `_posts_args` / `_depts_args` / `_dedupe` / `_clean_optional`。

真库两阶段（达梦 / MySQL / PostgreSQL）由 CI `txn-2pc` 作业与 `05_07` 收尾验证。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RoleNotFoundError,
    RoleSubjectInvalidError,
    ServiceUnavailableError,
    TransactionUnavailableError,
    UserNotFoundError,
    UserProtectedError,
    UserSeparationConflictError,
)
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_core.transaction.base import BRANCH_PREPARED, BRANCH_REJECTED, BranchRef, GlobalTransaction
from bms_platform.models.role import ROLE_TYPE_SYSTEM, SysRole, SysUserRole
from bms_platform.models.user import SysUser
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import (
    UserAssignmentDepts,
    UserAssignmentPosts,
    UserAssignmentProfile,
    UserAssignmentsRequest,
)
from bms_platform.services.separation import SeparationGuard
from bms_platform.services.user_assignments import (
    BRANCH_ID_ORG,
    BRANCH_ID_PLATFORM,
    ORG_USER_DEPTS_OP,
    ORG_USER_POSTS_OP,
    SEGMENT_ROLES,
    USER_ASSIGNMENTS_OP,
    UserAssignmentsService,
    UserAssignmentWriter,
    _branch_state,  # pyright: ignore[reportPrivateUsage]
    _clean_optional,  # pyright: ignore[reportPrivateUsage]
    _dedupe,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = [pytest.mark.kiwi_id(2278)]


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时内存 SQLite 会话（建全量平台元数据表）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


async def _seed_user(session: AsyncSession, *, status: str = "enabled") -> SysUser:
    """插入一条启用态用户（`version` 由模型缺省给出）。

    Args:
        session: 会话。
        status: 账号状态。

    Returns:
        SysUser: 持久化后的用户行。
    """
    user = SysUser(username="u1", password_hash="hash", name="用户一", status=status)
    session.add(user)
    await session.commit()
    return user


async def _seed_role(session: AsyncSession, code: str, *, role_type: str = "custom") -> SysRole:
    """插入一条角色。

    Args:
        session: 会话。
        code: 角色码。
        role_type: 角色类型。

    Returns:
        SysRole: 持久化后的角色行。
    """
    role = SysRole(code=code, name=code, role_type=role_type)
    session.add(role)
    await session.commit()
    return role


class _OutboxSpy:
    """发件箱替身（记录事件信封，不落库）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.events: ConcurrentStableList[Any] = ConcurrentStableList()

    async def enqueue(self, session: object, envelope: Any) -> None:
        """记录一次事件入队。

        Args:
            session: 会话（未使用）。
            envelope: 事件信封。
        """
        self.events.add(envelope)


def _writer(session: AsyncSession, outbox: _OutboxSpy, *, guard: SeparationGuard | None = None) -> UserAssignmentWriter:
    """构造写入器（真实仓储 + 发件箱替身）。

    Args:
        session: 会话。
        outbox: 发件箱替身。
        guard: 三权分立校验器（缺省不校验，`03_02` 专项用例显式传入）。

    Returns:
        UserAssignmentWriter: 写入器。
    """
    return UserAssignmentWriter(
        cast("Any", session),
        DbUnitOfWork(cast("Any", session)),
        UserRepository(cast("Any", session)),
        UserRoleRepository(cast("Any", session)),
        RoleRepository(cast("Any", session)),
        cast("Any", outbox),
        guard,
    )


@pytest.mark.kiwi_id(2314)
async def test_writer_roles_reject_separation_conflict_before_write() -> None:
    """三权互斥前置（`30010`）：角色集合含两类内置管理员 → 拒绝且既有绑定未软删。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        keep = await _seed_role(session, "keep")
        system = await _seed_role(session, "system_admin", role_type="system")
        security = await _seed_role(session, "security_admin", role_type="security")
        uid, keep_id, system_id, security_id = user.id, keep.id, system.id, security.id
        session.add(SysUserRole(role_id=keep_id, user_id=uid))
        await session.commit()

        guard = SeparationGuard(
            roles=RoleRepository(cast("Any", session)),
            user_roles=UserRoleRepository(cast("Any", session)),
        )
        writer = _writer(session, _OutboxSpy(), guard=guard)

        with pytest.raises(UserSeparationConflictError) as conflict:
            await writer.write(
                user_id=uid,
                profile=None,
                role_ids=ConcurrentStableList([keep_id, system_id, security_id]),
            )
        assert conflict.value.code == 30010

        # 拒绝发生在软删之前：既有绑定保持
        active = set(await UserRoleRepository(cast("Any", session)).list_role_ids_by_user(uid))
        assert active == {keep_id}

        # 单一内置类型放行
        await session.rollback()
        await writer.write(user_id=uid, profile=None, role_ids=ConcurrentStableList([keep_id, system_id]))
        active = set(await UserRoleRepository(cast("Any", session)).list_role_ids_by_user(uid))
        assert active == {keep_id, system_id}
        await session.rollback()
    finally:
        await engine.dispose()


async def test_writer_profile_updates_fields_and_emits_event() -> None:
    """基础资料分段：写入 + 清空（空串→None）+ `sys.user.updated` 事件。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        outbox = _OutboxSpy()
        writer = _writer(session, outbox)

        updated = await writer.write(
            user_id=user.id,
            profile=UserAssignmentProfile(
                version=user.version,
                name="  新名字  ",
                email="a@example.com",
                phone="13800000000",
                status="enabled",
            ),
            role_ids=None,
        )
        assert updated.name == "新名字"
        assert updated.email == "a@example.com"
        assert updated.phone == "13800000000"
        event = next(iter(outbox.events))
        assert event.event_type == "sys.user.updated"
        assert event.payload.get("user_id") == str(user.id)

        # 空串 → 清空（None）；`null` → 不改。
        cleared = await writer.write(
            user_id=user.id,
            profile=UserAssignmentProfile(version=user.version, email="   ", phone=""),
            role_ids=None,
        )
        assert cleared.email is None
        assert cleared.phone is None
    finally:
        await engine.dispose()


async def test_writer_profile_rejects_conflict_and_invalid_values() -> None:
    """基础资料分段失败分支：乐观锁冲突（10003）、状态非法（10001）、联系方式格式非法（10001）。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        uid, version = user.id, user.version
        writer = _writer(session, _OutboxSpy())

        with pytest.raises(ConcurrentConflictError):
            await writer.write(
                user_id=uid,
                profile=UserAssignmentProfile(version=version + 1, name="x"),
                role_ids=None,
            )
        # 状态取值非法：契约层已收敛为字面量，此处绕过校验直造非法值以覆盖防御分支。
        illegal_status = UserAssignmentProfile.model_construct(version=version, status="unknown")
        with pytest.raises(ParamError):
            await writer.write(user_id=uid, profile=illegal_status, role_ids=None)
        with pytest.raises(ParamError):
            await writer.write(
                user_id=uid,
                profile=UserAssignmentProfile(version=version, email="not-an-email"),
                role_ids=None,
            )
        with pytest.raises(ParamError):
            await writer.write(
                user_id=uid,
                profile=UserAssignmentProfile(version=version, phone="abc"),
                role_ids=None,
            )
        with pytest.raises(UserNotFoundError):
            await writer.write(
                user_id=uid + 999,
                profile=UserAssignmentProfile(version=1, name="x"),
                role_ids=None,
            )
    finally:
        await engine.dispose()


async def test_writer_roles_full_overwrite_soft_deletes_restores_and_creates() -> None:
    """角色分段：集合外软删、已软删恢复、未分配新建、集合内保留。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        keep = await _seed_role(session, "keep")
        restore = await _seed_role(session, "restore")
        fresh = await _seed_role(session, "fresh")
        removed = await _seed_role(session, "removed")

        uid = user.id
        keep_id, restore_id, fresh_id, removed_id = keep.id, restore.id, fresh.id, removed.id
        session.add_all(
            [
                SysUserRole(role_id=keep_id, user_id=uid),
                SysUserRole(role_id=removed_id, user_id=uid),
            ]
        )
        await session.commit()
        session.add(SysUserRole(role_id=restore_id, user_id=uid, deleted_at=datetime(2026, 1, 1, tzinfo=UTC)))
        await session.commit()

        writer = _writer(session, _OutboxSpy())
        await writer.write(
            user_id=uid,
            profile=None,
            role_ids=ConcurrentStableList([keep_id, restore_id, fresh_id, fresh_id]),
        )

        user_roles = UserRoleRepository(cast("Any", session))
        active = set(await user_roles.list_role_ids_by_user(uid))
        assert active == {keep_id, restore_id, fresh_id}
        assert await user_roles.get_deleted_by_role_user(removed_id, uid) is not None
        assert await user_roles.get_deleted_by_role_user(restore_id, uid) is None
        await session.rollback()

        with pytest.raises(RoleNotFoundError):
            await writer.write(
                user_id=uid,
                profile=None,
                role_ids=ConcurrentStableList([keep_id, 987654]),
            )
    finally:
        await engine.dispose()


async def test_writer_roles_rejects_disabled_subject() -> None:
    """停用账号参与角色段 → 30045（`RoleSubjectInvalidError`）。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session, status="disabled")
        role = await _seed_role(session, "r1")
        writer = _writer(session, _OutboxSpy())

        with pytest.raises(RoleSubjectInvalidError):
            await writer.write(user_id=user.id, profile=None, role_ids=ConcurrentStableList([role.id]))
    finally:
        await engine.dispose()


async def test_protection_rules_block_self_and_builtin_admin() -> None:
    """保护规则：停用自身（操作人）与持有内置角色的账号均被拒（30009）。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        uid, version = user.id, user.version
        writer = _writer(session, _OutboxSpy())

        current_user_id.set(uid)
        try:
            with pytest.raises(UserProtectedError):
                await writer.write(
                    user_id=uid,
                    profile=UserAssignmentProfile(version=version, status="disabled"),
                    role_ids=None,
                )
        finally:
            current_user_id.set(None)

        builtin = await _seed_role(session, "sysadmin", role_type=ROLE_TYPE_SYSTEM)
        session.add(SysUserRole(role_id=builtin.id, user_id=uid))
        await session.commit()

        with pytest.raises(UserProtectedError):
            await writer.write(
                user_id=uid,
                profile=UserAssignmentProfile(version=version, status="disabled"),
                role_ids=None,
            )
    finally:
        await engine.dispose()


def test_dedupe_keeps_first_seen_order() -> None:
    """去重保持首次出现序。"""
    assert list(_dedupe(ConcurrentStableList([3, 1, 3, 2, 1]))) == [3, 1, 2]


class _ManagerSpy:
    """事务管理器替身（可切换是否 enabled / 分支快照）。"""

    def __init__(self, *, enabled: bool = True, branches: ConcurrentStableList[BranchRef] | None = None) -> None:
        """初始化。

        Args:
            enabled: `enabled` 判定（决定走 XA 还是顺序提交）。
            branches: 覆写的分支快照（缺省按 `begin` 入参生成）。
        """
        self.enabled = enabled
        self._branches = branches
        self.begun: ConcurrentStableList[Any] = ConcurrentStableList()
        self.commits: ConcurrentStableList[str] = ConcurrentStableList()
        self.rollbacks: ConcurrentStableList[str] = ConcurrentStableList()

    async def begin(self, *, caller_service: str, branches: Any) -> GlobalTransaction:
        """记录分支声明并返回全局事务快照。

        Args:
            caller_service: 发起方服务键。
            branches: 分支声明清单。

        Returns:
            GlobalTransaction: 快照。
        """
        self.begun.add((caller_service, tuple(branches)))
        refs = self._branches
        if refs is None:
            refs = tuple(
                BranchRef(
                    branch_id=spec.branch_id, service=spec.service, db_key=spec.db_key, xid=f"xid-{spec.branch_id}"
                )
                for spec in branches
            )
        return GlobalTransaction(global_txn_id="gtx-1", caller_service=caller_service, state="active", branches=refs)  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定

    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """记录提交。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 快照。
        """
        self.commits.add(global_txn_id)
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """记录回滚。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 快照。
        """
        self.rollbacks.add(global_txn_id)
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _ParticipantSpy:
    """事务参与方替身（返回可配置状态）。"""

    def __init__(self, state: str = BRANCH_PREPARED) -> None:
        """初始化。

        Args:
            state: `execute_branch` 返回的分支状态。
        """
        self.state = state
        self.calls: ConcurrentStableList[Any] = ConcurrentStableList()

    async def execute_branch(self, *, xid: str, db_key: str, ops: Any) -> str:
        """记录分支执行并返回配置状态。

        Args:
            xid: 分支事务标识。
            db_key: 分支库键。
            ops: 分支操作。

        Returns:
            str: 分支状态。
        """
        self.calls.add((xid, db_key, tuple(ops)))
        return self.state


class _ClientSpy:
    """服务间调用客户端替身（回可配置响应）。"""

    def __init__(self, response: ServiceResponse | None = None) -> None:
        """初始化。

        Args:
            response: 固定响应（缺省 `code=0 / state=prepared`）。
        """
        self.response = response
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并回固定响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 响应。
        """
        self.requests.add(request)
        if self.response is not None:
            return self.response
        return ServiceResponse(status_code=200, content=json.dumps({"code": 0, "data": {"state": "prepared"}}).encode())


class _CacheSpy:
    """缓存 Region 替身。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.bumped: ConcurrentStableList[str] = ConcurrentStableList()

    async def aincrease(self, key: str) -> int:
        """记录递增键。

        Args:
            key: 键。

        Returns:
            int: 恒 1。
        """
        self.bumped.add(key)
        return 1


class _SessionsSpy:
    """会话失效客户端替身。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.revoked: ConcurrentStableList[int] = ConcurrentStableList()

    async def revoke_user_sessions(self, user_id: int, *, reason: str) -> bool:
        """记录撤销调用。

        Args:
            user_id: 用户主键。
            reason: 撤销原因。

        Returns:
            bool: 恒真。
        """
        self.revoked.add(user_id)
        return True


class _UsersSpy:
    """用户仓储替身（回读生效后用户）。"""

    async def get_by_id(self, user_id: int) -> Any:
        """按主键取用户替身。

        Args:
            user_id: 用户主键。

        Returns:
            object: 用户替身。
        """

        class _User:
            id = 7
            status = "enabled"
            version = 1

        return _User()


class _RolesSpy:
    """角色仓储替身。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.ids: ConcurrentStableList[Any] = ConcurrentStableList()

    async def get(self, role_id: int) -> Any:
        """按主键取角色替身。

        Args:
            role_id: 角色主键。

        Returns:
            object: 角色替身。
        """

        class _Role:
            def __init__(self, rid: int) -> None:
                self.id = rid
                self.code = f"r{rid}"

        return _Role(role_id)

    async def list_by_ids(self, role_ids: Any) -> ConcurrentStableList[Any]:
        """按主键集合取角色。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[Any]: 角色替身清单。
        """
        self.ids.add(tuple(role_ids))
        return ConcurrentStableList()


class _UserRolesSpy:
    """角色分配仓储替身（XA 路径不落库，仅回读）。"""

    async def list_role_ids_by_user(self, user_id: int) -> ConcurrentStableList[int]:
        """取用户直接角色。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[int]: 角色主键。
        """
        return ConcurrentStableList()


def _xa_service(
    manager: _ManagerSpy,
    participant: _ParticipantSpy,
    client: _ClientSpy,
    *,
    cache: _CacheSpy | None = None,
    sessions: _SessionsSpy | None = None,
    writer: Any = None,
    users: Any = None,
) -> UserAssignmentsService:
    """构造 XA 路径编排服务（全替身）。

    Args:
        manager: 事务管理器替身。
        participant: 事务参与方替身。
        client: 服务间调用客户端替身。
        cache: 缓存替身。
        sessions: 会话失效替身。
        writer: 写入器替身（顺序提交路径用；缺省空对象）。
        users: 用户仓储替身（缺省返回固定用户）。

    Returns:
        UserAssignmentsService: 编排服务。
    """
    return UserAssignmentsService(
        writer=cast("Any", writer if writer is not None else object()),
        user_roles=cast("Any", _UserRolesSpy()),
        roles=cast("Any", _RolesSpy()),
        users=cast("Any", users if users is not None else _UsersSpy()),
        sessions=cast("Any", sessions or _SessionsSpy()),
        cache=cast("Any", cache or _CacheSpy()),
        manager=cast("Any", manager),
        participant=cast("Any", participant),
        client=cast("Any", client),
        tenant_id="1001",
    )


async def test_xa_path_declares_branches_and_commits() -> None:
    """XA 路径：平台分支进程内执行 + 组织域分支远端执行，双方就绪后提交。"""
    manager = _ManagerSpy()
    participant = _ParticipantSpy()
    client = _ClientSpy()
    cache = _CacheSpy()
    service = _xa_service(manager, participant, client, cache=cache)

    user, _roles, applied = await service.apply(
        user_id=7,
        req=UserAssignmentsRequest(
            role_ids=ConcurrentStableList([11]),
            user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([21]), primary_post_id=21),
            user_depts=UserAssignmentDepts(dept_ids=ConcurrentStableList([31]), primary_dept_id=31),
        ),
        idempotency_key="k-1",
    )

    assert user.id == 7
    assert list(applied) == [SEGMENT_ROLES, "user_posts", "user_depts"]
    _caller, specs = manager.begun[0]
    assert [spec.branch_id for spec in specs] == [BRANCH_ID_PLATFORM, BRANCH_ID_ORG]
    xid, _db_key, ops = participant.calls[0]
    assert xid == f"xid-{BRANCH_ID_PLATFORM}"
    assert ops[0].op == USER_ASSIGNMENTS_OP
    assert ops[0].args.get("user_id") == 7
    assert ops[0].args.get("role_ids") == [11]
    assert ops[0].args.get("idempotency_key") == "k-1"

    assert len(client.requests) == 1
    body = cast("Any", client.requests[0].json_body)
    assert body.get("xid") == f"xid-{BRANCH_ID_ORG}"
    org_ops = body.get("ops")
    assert [entry.get("op") for entry in org_ops] == [ORG_USER_POSTS_OP, ORG_USER_DEPTS_OP]
    assert org_ops[0].get("args").get("user_id") == 7
    assert list(manager.commits) == ["gtx-1"]
    assert manager.rollbacks == []
    assert list(cache.bumped) == ["bms:1001:permission:version"]


async def test_xa_path_rolls_back_when_platform_branch_not_prepared() -> None:
    """平台分支未达 `PREPARED` → 10013 并回滚全局事务。"""
    manager = _ManagerSpy()
    participant = _ParticipantSpy(state=BRANCH_REJECTED)
    service = _xa_service(manager, participant, _ClientSpy())

    with pytest.raises(TransactionUnavailableError):
        await service.apply(
            user_id=7,
            req=UserAssignmentsRequest(profile=UserAssignmentProfile(version=1, name="x")),
        )

    assert list(manager.rollbacks) == ["gtx-1"]
    assert manager.commits == []


async def test_xa_path_rolls_back_when_org_branch_not_prepared() -> None:
    """组织域分支未达 `PREPARED` → 10013 并回滚全局事务。"""
    manager = _ManagerSpy()
    participant = _ParticipantSpy()
    client = _ClientSpy(
        ServiceResponse(status_code=200, content=json.dumps({"code": 0, "data": {"state": "rejected"}}).encode())
    )
    service = _xa_service(manager, participant, client)

    with pytest.raises(TransactionUnavailableError):
        await service.apply(
            user_id=7,
            req=UserAssignmentsRequest(user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([21]))),
        )

    assert list(manager.rollbacks) == ["gtx-1"]


async def test_xa_path_missing_branch_raises() -> None:
    """全局事务快照缺分支 → 10013。"""
    manager = _ManagerSpy(branches=ConcurrentStableList(()))
    service = _xa_service(manager, _ParticipantSpy(), _ClientSpy())

    with pytest.raises(TransactionUnavailableError):
        await service.apply(
            user_id=7,
            req=UserAssignmentsRequest(profile=UserAssignmentProfile(version=1, name="x")),
        )
    assert list(manager.rollbacks) == ["gtx-1"]


async def test_execute_org_branches_returns_early_without_org_segments() -> None:
    """无组织域分段时组织分支执行直接返回（不发起远端调用）。"""
    client = _ClientSpy()
    service = _xa_service(_ManagerSpy(), _ParticipantSpy(), client)

    await service._execute_org_branches(  # pyright: ignore[reportPrivateUsage]
        xid="x",
        db_key="k",
        user_id=7,
        req=UserAssignmentsRequest(role_ids=ConcurrentStableList()),
        idempotency_key=None,
    )

    assert client.requests == []


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (ServiceResponse(status_code=503, content=b"{}"), ServiceUnavailableError),
        (ServiceResponse(status_code=200, content=b"[]"), ServiceUnavailableError),
        (ServiceResponse(status_code=200, content=json.dumps({"code": 10007}).encode()), ServiceUnavailableError),
        (
            ServiceResponse(status_code=200, content=json.dumps({"code": 0, "data": "x"}).encode()),
            ServiceUnavailableError,
        ),
    ],
)
def test_branch_state_failure_branches(response: ServiceResponse, expected: type[Exception]) -> None:
    """分支状态解析失败分支：非 2xx / 非 JSON 对象 / 业务码非 0 / 缺 data → 10007。"""
    with pytest.raises(expected):
        _branch_state(response)


def test_branch_state_returns_state() -> None:
    """分支状态解析：2xx + `code=0` + `data.state` → 原样返回。"""
    response = ServiceResponse(status_code=200, content=json.dumps({"code": 0, "data": {"state": "prepared"}}).encode())
    assert _branch_state(response) == "prepared"


def test_clean_optional_handles_none_and_blank() -> None:
    """`_clean_optional`：`None` 原样返回；纯空白归一为 `None`。"""
    assert _clean_optional(None) is None
    assert _clean_optional("   ") is None


async def test_writer_profile_with_email_only_skips_phone() -> None:
    """基础资料只给邮箱（`phone` 保持 `None`）时跳过手机号分支。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        updated = await _writer(session, _OutboxSpy()).write(
            user_id=user.id,
            profile=UserAssignmentProfile(version=user.version, email="a@example.com"),
            role_ids=None,
        )
        assert updated.email == "a@example.com"
        assert updated.phone is None
    finally:
        await engine.dispose()


async def test_assert_not_protected_allows_disable_without_roles_and_scans_roles() -> None:
    """保护规则：无角色时停用放行；持有多个自定义角色时逐个扫描，命中内置即拒。"""
    session, engine = await _session()
    try:
        plain = await _seed_user(session)
        writer = _writer(session, _OutboxSpy())

        # 无角色 + 非操作人自身 → 停用放行（`_assert_not_protected` 早退分支）。
        await writer.write(
            user_id=plain.id,
            profile=UserAssignmentProfile(version=plain.version, status="disabled"),
            role_ids=None,
        )
        assert plain.status == "disabled"

        # 另一用户持有两个自定义角色 + 一个内置角色：循环扫描命中内置后拒绝。
        target = SysUser(username="u2", password_hash="hash", name="用户二", status="enabled")
        session.add(target)
        await session.commit()
        uid, version = target.id, target.version
        custom_a = await _seed_role(session, "a")
        custom_b = await _seed_role(session, "b")
        builtin = await _seed_role(session, "sys", role_type=ROLE_TYPE_SYSTEM)
        session.add_all(
            [
                SysUserRole(role_id=custom_a.id, user_id=uid),
                SysUserRole(role_id=custom_b.id, user_id=uid),
                SysUserRole(role_id=builtin.id, user_id=uid),
            ]
        )
        await session.commit()

        with pytest.raises(UserProtectedError):
            await writer.write(
                user_id=uid,
                profile=UserAssignmentProfile(version=version, status="disabled"),
                role_ids=None,
            )
    finally:
        await engine.dispose()


async def test_assert_not_protected_passes_with_only_custom_roles() -> None:
    """保护规则：仅持有自定义角色时扫描完集合放行停用。"""
    session, engine = await _session()
    try:
        user = await _seed_user(session)
        uid, version = user.id, user.version
        role_a = await _seed_role(session, "a")
        role_b = await _seed_role(session, "b")
        session.add_all([SysUserRole(role_id=role_a.id, user_id=uid), SysUserRole(role_id=role_b.id, user_id=uid)])
        await session.commit()

        await _writer(session, _OutboxSpy()).write(
            user_id=uid,
            profile=UserAssignmentProfile(version=version, status="disabled"),
            role_ids=None,
        )
        assert user.status == "disabled"
    finally:
        await engine.dispose()


async def test_apply_requires_at_least_one_segment() -> None:
    """未提供任何分段 → 10001。"""
    service = _xa_service(_ManagerSpy(), _ParticipantSpy(), _ClientSpy())
    with pytest.raises(ParamError):
        await service.apply(user_id=7, req=UserAssignmentsRequest())
    assert service is not None


async def test_xa_path_without_org_branches_commits() -> None:
    """XA 路径（无组织域分段）：只声明平台分支并提交。"""
    manager = _ManagerSpy()
    participant = _ParticipantSpy()
    client = _ClientSpy()
    service = _xa_service(manager, participant, client)

    await service.apply(
        user_id=7,
        req=UserAssignmentsRequest(
            profile=UserAssignmentProfile(version=1, name="x"),
            role_ids=ConcurrentStableList([11]),
        ),
    )

    _caller, specs = manager.begun[0]
    assert [spec.branch_id for spec in specs] == [BRANCH_ID_PLATFORM]
    assert client.requests == []
    assert list(manager.commits) == ["gtx-1"]


async def test_apply_raises_when_user_missing_after_write() -> None:
    """提交后回读用户为空 → 30002。"""
    service = _xa_service(_ManagerSpy(), _ParticipantSpy(), _ClientSpy(), users=_UsersNoneSpy())

    with pytest.raises(UserNotFoundError):
        await service.apply(user_id=7, req=UserAssignmentsRequest(profile=UserAssignmentProfile(version=1, name="x")))


async def test_sequential_path_without_idempotency_key_omits_header() -> None:
    """顺序提交路径未给幂等键：组织域内部写通道不带 `Idempotency-Key` 头。"""
    manager = _ManagerSpy(enabled=False)
    participant = _ParticipantSpy()
    client = _ClientSpy()
    service = _xa_service(manager, participant, client, writer=_WriterSpy())

    await service.apply(
        user_id=7,
        req=UserAssignmentsRequest(user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([21]))),
        idempotency_key=None,
    )

    assert len(client.requests) == 1
    assert client.requests[0].headers == {}


async def test_after_commit_swallows_session_failure() -> None:
    """提交后会话失效失败被吞掉（不影响已提交结果）。"""
    manager = _ManagerSpy(enabled=False)
    service = _xa_service(
        manager, _ParticipantSpy(), _ClientSpy(), sessions=cast("Any", _FailingSessionsSpy()), writer=_WriterSpy()
    )

    await service.apply(
        user_id=7,
        req=UserAssignmentsRequest(profile=UserAssignmentProfile(version=1, status="disabled")),
    )
    assert service is not None


class _UsersNoneSpy:
    """用户仓储替身：恒无记录。"""

    async def get_by_id(self, user_id: int) -> Any:
        """按主键取用户（恒空）。

        Args:
            user_id: 用户主键。

        Returns:
            None: 恒空。
        """
        return None


class _WriterSpy:
    """写入器替身（不落库）。"""

    async def write(self, *, user_id: int, profile: object, role_ids: object) -> Any:
        """原样回用户替身。

        Args:
            user_id: 用户主键。
            profile: 基础资料分段。
            role_ids: 角色分段。

        Returns:
            object: 用户替身。
        """

        class _User:
            id = 7
            status = "enabled"
            version = 1

        return _User()


class _FailingSessionsSpy:
    """会话失效客户端替身：恒抛异常。"""

    async def revoke_user_sessions(self, user_id: int, *, reason: str) -> bool:
        """恒抛异常（验证被吞掉）。

        Args:
            user_id: 用户主键。
            reason: 撤销原因。

        Raises:
            RuntimeError: 恒抛。
        """
        raise RuntimeError("session store unavailable")
