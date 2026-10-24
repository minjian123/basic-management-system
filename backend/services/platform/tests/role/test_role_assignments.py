"""角色保存编排（`02_03/_02` · Kiwi 2283）：分段校验 + 双路径编排（顺序提交路径）+ 提交后副作用。

覆盖：分段收集（`null` 不参与）；`provider=null` 顺序提交路径的编排顺序（platform 本地写入 →
组织域内部写通道 role-posts / role-depts ×2）与提交后副作用（角色段 / `user_ids` 段 ⇒ 权限版本 +1）；
组织域**分支载荷**构造（同一分支内两 op）；角色 × 用户全量覆盖（保留集合外软删 + 恢复原行）。
XA 全局事务路径的真库两阶段由 CI `2pc` 作业与 `05_07` 收尾验证（本机无真库）。
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RoleCodeExistsError,
    RoleNotFoundError,
    RoleProtectedError,
    RoleSubjectInvalidError,
    ServiceUnavailableError,
    TransactionUnavailableError,
    UserSeparationConflictError,
)
from bms_core.db.keys import build_tenant_db_key
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_core.transaction.base import BRANCH_PREPARED, BRANCH_REJECTED, BranchRef, GlobalTransaction
from bms_core.transaction.null import NullTransactionManager, NullTransactionParticipant
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.role import (
    RoleAssignmentDepts,
    RoleAssignmentPosts,
    RoleAssignmentProfile,
    RoleAssignmentsRequest,
)
from bms_platform.services.role_assignments import (
    MDM_INTERNAL_ROLE_DEPTS_PATH,
    MDM_INTERNAL_ROLE_POSTS_PATH,
    MDM_ROLE_DEPTS_OP,
    MDM_ROLE_POSTS_OP,
    RoleAssignmentsService,
    RoleAssignmentWriter,
    _branch_state,  # pyright: ignore[reportPrivateUsage]
    build_org_ops,
    collect_segments,
)
from bms_platform.services.separation import SeparationGuard
from tests.role import helpers

pytestmark = [pytest.mark.kiwi_id(2283)]

_TENANT = "1001"


class _Role:
    """角色记录替身（回读面所需最小字段）。"""

    def __init__(self, role_id: int) -> None:
        self.id = role_id
        self.code = "ops"
        self.name = "运维角色"
        self.status = "enabled"
        self.role_type = "custom"
        self.version = 1


class _User:
    """用户记录替身。"""

    def __init__(self, user_id: int, *, status: str = "enabled") -> None:
        self.id = user_id
        self.username = f"u{user_id}"
        self.name = f"用户{user_id}"
        self.status = status


class _WriterSpy:
    """写入器替身（记录入参，不落库）。"""

    def __init__(self) -> None:
        self.calls: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    async def write(self, *, role_id: int, profile: object, user_ids: object) -> object:
        """记录一次写入调用。"""
        call: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        call.set("role_id", role_id)
        call.set("profile", profile)
        call.set("user_ids", user_ids)
        self.calls.add(call)
        return _Role(role_id)


class _ClientSpy:
    """服务间调用客户端替身（记录请求并回可配置分支状态）。"""

    def __init__(self, *, state: str = "prepared") -> None:
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()
        self.state = state

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录调用并回成功响应。"""
        self.requests.add(request)
        body = json.dumps({"code": 0, "data": {"state": self.state}}).encode("utf-8")
        return ServiceResponse(status_code=200, content=body)


class _CacheSpy:
    """缓存 Region 替身（记录权限版本递增键）。"""

    def __init__(self) -> None:
        self.bumped: ConcurrentStableList[str] = ConcurrentStableList()

    async def aincrease(self, key: str) -> int:
        """记录递增键。"""
        self.bumped.add(key)
        return 1


class _RolesSpy:
    """角色仓储替身（回读生效后角色）。"""

    async def get(self, role_id: int) -> _Role:
        """按主键取角色。"""
        return _Role(role_id)


class _UserRolesSpy:
    """角色 × 用户分配仓储替身（回读分配用户主键）。"""

    def __init__(self, user_ids: ConcurrentStableList[int]) -> None:
        self.user_ids = user_ids

    async def list_user_ids_by_role(self, role_id: int) -> ConcurrentStableList[int]:
        """取角色已分配用户主键。"""
        return self.user_ids


class _UsersSpy:
    """用户仓储替身（回读生效后用户）。"""

    def __init__(self, users: ConcurrentStableList[_User]) -> None:
        self.users: ConcurrentStableDict[int, _User] = ConcurrentStableDict({user.id: user for user in users})

    async def list_by_ids(self, ids: object) -> ConcurrentStableList[_User]:
        """取用户记录。"""
        items: ConcurrentStableList[_User] = ConcurrentStableList()
        for user_id in cast("ConcurrentStableList[int]", ids):
            if user_id in self.users:
                items.add(self.users[user_id])
        return items


def _service(
    manager: Any,
    participant: Any,
    client: _ClientSpy,
    *,
    users: ConcurrentStableList[_User] | None = None,
    user_ids: ConcurrentStableList[int] | None = None,
    roles: Any = None,
) -> tuple[RoleAssignmentsService, _WriterSpy, _CacheSpy]:
    """构造编排服务与替身。"""
    writer = _WriterSpy()
    cache = _CacheSpy()
    resolved_users = users if users is not None else ConcurrentStableList([_User(7)])
    resolved_ids = user_ids if user_ids is not None else ConcurrentStableList([7])
    service = RoleAssignmentsService(
        writer=cast("Any", writer),
        roles=cast("Any", roles if roles is not None else _RolesSpy()),
        users=cast("Any", _UsersSpy(resolved_users)),
        user_roles=cast("Any", _UserRolesSpy(resolved_ids)),
        cache=cast("Any", cache),
        manager=manager,
        participant=participant,
        client=cast("Any", client),
        tenant_id=_TENANT,
    )
    return service, writer, cache


def test_collect_segments() -> None:
    """分段收集：`null` 不参与。"""
    assert collect_segments(RoleAssignmentsRequest()) == []

    segments = collect_segments(
        RoleAssignmentsRequest(
            role=RoleAssignmentProfile(version=1),
            user_ids=ConcurrentStableList(),
            role_posts=RoleAssignmentPosts(post_ids=ConcurrentStableList([11])),
            role_depts=None,
        )
    )
    assert list(segments) == ["role", "user_ids", "role_posts"]


async def test_sequential_path_orders_writes_and_bumps_permission_version() -> None:
    """`provider=null`（顺序提交）：本地写入 → 组织域内部写通道 ×2；角色段 ⇒ 权限版本 +1。"""
    client = _ClientSpy()
    service, writer, cache = _service(
        NullTransactionManager(), NullTransactionParticipant(), client, user_ids=ConcurrentStableList([7])
    )

    role, users, applied = await service.apply(
        role_id=5,
        req=RoleAssignmentsRequest(
            role=RoleAssignmentProfile(name="运维角色", version=1),
            user_ids=ConcurrentStableList([7]),
            role_posts=RoleAssignmentPosts(post_ids=ConcurrentStableList([11])),
            role_depts=None,
        ),
        idempotency_key="k-1",
    )

    assert role.id == 5
    assert [user.id for user in users] == [7]
    assert list(applied) == ["role", "user_ids", "role_posts"]
    assert len(writer.calls) == 1
    paths = [request.path for request in client.requests]
    assert paths == [MDM_INTERNAL_ROLE_POSTS_PATH.format(role_id=5)]
    assert client.requests[0].headers is not None
    assert client.requests[0].headers.get("Idempotency-Key") == "k-1"
    assert list(cache.bumped) == ["bms:1001:permission:version"]


async def test_sequential_path_skips_bump_when_only_org_segments() -> None:
    """仅组织分配段（无角色本体 / 用户分配）：不递增平台权限版本。"""
    client = _ClientSpy()
    service, _writer, cache = _service(NullTransactionManager(), NullTransactionParticipant(), client)

    await service.apply(
        role_id=5,
        req=RoleAssignmentsRequest(role_depts=RoleAssignmentDepts(dept_ids=ConcurrentStableList([21]))),
        idempotency_key=None,
    )

    assert cache.bumped == []
    assert [request.path for request in client.requests] == [MDM_INTERNAL_ROLE_DEPTS_PATH.format(role_id=5)]


async def test_sequential_path_posts_without_idempotency_key() -> None:
    """顺序提交路径：岗位段不带幂等键时内部写通道载荷不含 `idempotency_key`。"""
    client = _ClientSpy()
    service, _writer, _cache = _service(NullTransactionManager(), NullTransactionParticipant(), client)

    await service.apply(
        role_id=5,
        req=RoleAssignmentsRequest(role_posts=RoleAssignmentPosts(post_ids=ConcurrentStableList([11]))),
        idempotency_key=None,
    )

    assert [request.path for request in client.requests] == [MDM_INTERNAL_ROLE_POSTS_PATH.format(role_id=5)]
    body = client.requests[0].json_body
    assert body is not None
    assert body.get("post_ids") == [11]
    assert "idempotency_key" not in body


def test_org_branch_ops_share_one_branch_request() -> None:
    """组织域分支载荷：岗位 / 部门各一 op，同一分支（同一 `xid`）一次请求内按序执行。"""
    req = RoleAssignmentsRequest(
        role_posts=RoleAssignmentPosts(post_ids=ConcurrentStableList([11, 12])),
        role_depts=RoleAssignmentDepts(dept_ids=ConcurrentStableList([21])),
    )
    ops = build_org_ops(role_id=5, req=req, idempotency_key="k-1")

    assert [op for op, _args in ops] == [MDM_ROLE_POSTS_OP, MDM_ROLE_DEPTS_OP]
    posts_args = ops[0][1]
    assert posts_args.get("role_id") == 5
    assert posts_args.get("post_ids") == [11, 12]
    assert posts_args.get("idempotency_key") == "k-1"
    depts_args = ops[1][1]
    assert depts_args.get("dept_ids") == [21]


async def _seed(target: AsyncSession) -> tuple[int, int, int, int]:
    """播种一个角色与三个用户（一名停用）。

    Returns:
        tuple[int, int, int, int]: (角色 ID, 用户 A, 用户 B, 停用用户 C)。
    """
    role = await RoleRepository(target).create(code="ops", name="运维角色")
    users = UserRepository(target)
    user_a = await users.create(username="alice", password_hash="x", name="爱丽丝")
    user_b = await users.create(username="bob", password_hash="x", name="鲍勃")
    user_c = await users.create(username="carol", password_hash="x", name="卡罗", status="disabled")
    await target.commit()
    return role.id, user_a.id, user_b.id, user_c.id


def _writer(target: AsyncSession, *, guard: SeparationGuard | None = None) -> RoleAssignmentWriter:
    """构造 platform 侧写入器（真实仓储 + 内存会话）。

    Args:
        target: 会话。
        guard: 三权分立校验器（缺省不校验，`03_02` 专项用例显式传入）。

    Returns:
        RoleAssignmentWriter: 写入器。
    """
    return RoleAssignmentWriter(
        target,
        DbUnitOfWork(target),
        RoleRepository(target),
        UserRoleRepository(target),
        UserRepository(target),
        NullConfigSource(),
        guard,
    )


@pytest.mark.kiwi_id(2314)
async def test_writer_rejects_separation_conflict_before_write() -> None:
    """三权互斥前置（`30010`）：用户已持安全管理员时再写入系统管理员 → 拒绝且未软删既有行。"""
    target, engine = await helpers.session()
    role_id, user_a, _b, _c = await _seed(target)
    system = await RoleRepository(target).create(code="system_admin", name="系统管理员", role_type="system")
    security = await RoleRepository(target).create(code="security_admin", name="安全管理员", role_type="security")
    await target.commit()
    system_id, security_id = system.id, security.id

    writer = _writer(target, guard=helpers.separation_guard(target))
    # 先绑安全管理员（单一内置类型：放行）
    await writer.write(role_id=security_id, profile=None, user_ids=ConcurrentStableList((user_a,)))
    await helpers.commit(target)
    assert [row.user_id for row in await UserRoleRepository(target).list_by_role(security_id)] == [user_a]
    await helpers.commit(target)

    # 再绑系统管理员：兼任冲突 → 拒绝，且安全管理员绑定未被软删
    with pytest.raises(UserSeparationConflictError) as conflict:
        await writer.write(role_id=system_id, profile=None, user_ids=ConcurrentStableList((user_a,)))
    assert conflict.value.code == 30010
    await helpers.commit(target)
    assert await UserRoleRepository(target).list_by_role(system_id) == []
    assert [row.user_id for row in await UserRoleRepository(target).list_by_role(security_id)] == [user_a]
    assert role_id  # 保留播种的自定义角色（不受三权约束）
    await engine.dispose()


async def test_writer_full_overwrite_replaces_user_set() -> None:
    """角色 × 用户全量覆盖：集合外软删 + 集合内保留 / 恢复 / 新建。"""
    target, engine = await helpers.session()
    role_id, user_a, user_b, _ = await _seed(target)

    await _writer(target).write(role_id=role_id, profile=None, user_ids=ConcurrentStableList((user_a, user_b)))
    rows = await UserRoleRepository(target).list_by_role(role_id)
    assert [row.user_id for row in rows] == [user_a, user_b]
    await helpers.commit(target)

    # 覆盖为仅 A：B 被软删，行不删除
    await _writer(target).write(role_id=role_id, profile=None, user_ids=ConcurrentStableList((user_a,)))
    assert [row.user_id for row in await UserRoleRepository(target).list_by_role(role_id)] == [user_a]
    await helpers.commit(target)

    # 重新覆盖为 A + B：B 恢复原行（行数仍 2、主键不新增）
    await _writer(target).write(role_id=role_id, profile=None, user_ids=ConcurrentStableList((user_a, user_b)))
    restored = await UserRoleRepository(target).list_by_role(role_id)
    assert len(restored) == 2 and len({row.id for row in restored}) == 2
    await helpers.commit(target)

    await engine.dispose()


async def test_writer_profile_and_guards() -> None:
    """角色本体分段：乐观锁冲突（10003）、内置角色停用（30043）、角色码 / 名称更新。"""
    target, engine = await helpers.session()
    role_id = (await RoleRepository(target).create(code="ops", name="运维角色")).id
    builtin_id = (await RoleRepository(target).create(code="system_admin", name="系统管理员", role_type="system")).id
    await target.commit()

    with pytest.raises(ConcurrentConflictError):
        await _writer(target).write(
            role_id=role_id, profile=RoleAssignmentProfile(name="新名", version=99), user_ids=None
        )
    await helpers.commit(target)

    with pytest.raises(RoleProtectedError):
        await _writer(target).write(
            role_id=builtin_id, profile=RoleAssignmentProfile(status="disabled", version=1), user_ids=None
        )
    await helpers.commit(target)

    await _writer(target).write(
        role_id=role_id,
        profile=RoleAssignmentProfile(code="ops_new", name="新名", version=1),
        user_ids=None,
    )
    updated = await RoleRepository(target).get(role_id)
    assert updated is not None and updated.code == "ops_new" and updated.name == "新名"
    await helpers.commit(target)

    await engine.dispose()


async def test_writer_rejects_invalid_user() -> None:
    """用户不存在 / 停用 → 30045。"""
    target, engine = await helpers.session()
    role_id, _a, _b, user_c = await _seed(target)

    with pytest.raises(RoleSubjectInvalidError):
        await _writer(target).write(role_id=role_id, profile=None, user_ids=ConcurrentStableList((user_c,)))
    with pytest.raises(RoleSubjectInvalidError):
        await _writer(target).write(role_id=role_id, profile=None, user_ids=ConcurrentStableList((999999999,)))
    await helpers.commit(target)

    await engine.dispose()


async def test_writer_rejects_missing_role_and_dedupes_user_ids() -> None:
    """角色不存在 → 30041；用户分配入参去重（同一用户只落一行）。"""
    target, engine = await helpers.session()
    role_id, user_a, _b, _c = await _seed(target)

    with pytest.raises(RoleNotFoundError):
        await _writer(target).write(role_id=987654321, profile=None, user_ids=None)
    await helpers.commit(target)

    await _writer(target).write(role_id=role_id, profile=None, user_ids=ConcurrentStableList((user_a, user_a)))
    rows = await UserRoleRepository(target).list_by_role(role_id)
    assert [row.user_id for row in rows] == [user_a]
    await helpers.commit(target)

    await engine.dispose()


async def test_writer_profile_status_and_code_guards() -> None:
    """角色本体分段：状态非法（10001）、状态切换、角色码格式非法（10001）与占用（30042）。"""
    target, engine = await helpers.session()
    role = await RoleRepository(target).create(code="ops", name="运维角色")
    other = await RoleRepository(target).create(code="other", name="其它")
    role_id, other_id = role.id, other.id
    await target.commit()

    with pytest.raises(ParamError):
        await _writer(target).write(
            role_id=role_id, profile=RoleAssignmentProfile.model_construct(version=1, status="unknown"), user_ids=None
        )
    await helpers.commit(target)

    current = await RoleRepository(target).get(role_id)
    assert current is not None
    version = current.version
    await helpers.commit(target)
    await _writer(target).write(
        role_id=role_id, profile=RoleAssignmentProfile(status="disabled", version=version), user_ids=None
    )
    reloaded = await RoleRepository(target).get(role_id)
    assert reloaded is not None and reloaded.status == "disabled"
    await helpers.commit(target)

    current = await RoleRepository(target).get(role_id)
    assert current is not None
    version = current.version
    await helpers.commit(target)
    with pytest.raises(ParamError):
        await _writer(target).write(
            role_id=role_id, profile=RoleAssignmentProfile(code="Bad!", version=version), user_ids=None
        )
    await helpers.commit(target)

    await _writer(target).write(
        role_id=role_id, profile=RoleAssignmentProfile(code="ops", version=version), user_ids=None
    )
    await helpers.commit(target)

    with pytest.raises(RoleCodeExistsError):
        await _writer(target).write(
            role_id=other_id, profile=RoleAssignmentProfile(code="ops", version=1), user_ids=None
        )
    await helpers.commit(target)

    await engine.dispose()


class _ManagerSpy:
    """事务管理器替身（可切换 `enabled` / 分支快照；记录开始 / 提交 / 回滚）。"""

    def __init__(self, *, enabled: bool = True, branches: ConcurrentStableList[BranchRef] | None = None) -> None:
        self.enabled = enabled
        self._branches = branches
        self.begun: ConcurrentStableList[Any] = ConcurrentStableList()
        self.commits: ConcurrentStableList[str] = ConcurrentStableList()
        self.rollbacks: ConcurrentStableList[str] = ConcurrentStableList()

    async def begin(self, *, caller_service: str, branches: Any) -> GlobalTransaction:
        """记录分支声明并返回全局事务快照。"""
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
        """记录提交。"""
        self.commits.add(global_txn_id)
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """记录回滚。"""
        self.rollbacks.add(global_txn_id)
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _ParticipantSpy:
    """事务参与方替身（返回可配置分支状态）。"""

    def __init__(self, state: str = BRANCH_PREPARED) -> None:
        self.state = state
        self.calls: ConcurrentStableList[Any] = ConcurrentStableList()

    async def execute_branch(self, *, xid: str, db_key: str, ops: Any) -> str:
        """记录分支执行并返回配置状态。"""
        self.calls.add((xid, db_key, tuple(ops)))
        return self.state


class _MissingRolesSpy:
    """角色仓储替身：恒无记录（回读角色时 30041）。"""

    async def get(self, role_id: int) -> None:
        """按主键取角色（恒空）。"""
        return None


async def test_apply_requires_at_least_one_segment() -> None:
    """未提供任何分段 → 10001。"""
    service, _writer, _cache = _service(NullTransactionManager(), NullTransactionParticipant(), _ClientSpy())
    with pytest.raises(ParamError):
        await service.apply(role_id=5, req=RoleAssignmentsRequest())


async def test_apply_raises_when_role_missing_after_write() -> None:
    """提交后回读角色为空 → 30041。"""
    service, _writer, _cache = _service(
        NullTransactionManager(), NullTransactionParticipant(), _ClientSpy(), roles=_MissingRolesSpy()
    )
    with pytest.raises(RoleNotFoundError):
        await service.apply(role_id=5, req=RoleAssignmentsRequest(user_ids=ConcurrentStableList([7])))


async def test_apply_returns_empty_users_when_none_assigned() -> None:
    """回读分配用户为空：短路返回空清单。"""
    service, _writer, _cache = _service(
        NullTransactionManager(), NullTransactionParticipant(), _ClientSpy(), user_ids=ConcurrentStableList()
    )
    _role, users, applied = await service.apply(role_id=5, req=RoleAssignmentsRequest(user_ids=ConcurrentStableList()))
    assert list(users) == []
    assert list(applied) == ["user_ids"]


async def test_xa_path_commits_after_all_branches_prepared() -> None:
    """XA 路径：platform 分支进程内执行 + 组织域分支远端执行，双方就绪后提交并递增权限版本。"""
    manager = _ManagerSpy()
    participant = _ParticipantSpy()
    client = _ClientSpy()
    service, writer, cache = _service(manager, participant, client, user_ids=ConcurrentStableList([7]))

    role, users, applied = await service.apply(
        role_id=5,
        req=RoleAssignmentsRequest(
            role=RoleAssignmentProfile(name="运维角色", version=1),
            user_ids=ConcurrentStableList([7]),
            role_posts=RoleAssignmentPosts(post_ids=ConcurrentStableList([11])),
            role_depts=RoleAssignmentDepts(dept_ids=ConcurrentStableList([21])),
        ),
        idempotency_key="k-1",
    )

    assert role.id == 5
    assert [user.id for user in users] == [7]
    assert list(applied) == ["role", "user_ids", "role_posts", "role_depts"]
    _caller, specs = manager.begun[0]
    assert [spec.branch_id for spec in specs] == ["p", "m"]
    xid, _db_key, ops = participant.calls[0]
    assert xid == "xid-p"
    assert ops[0].op == "sys.role.assignments"
    assert ops[0].args.get("role_id") == 5
    assert ops[0].args.get("user_ids") == [7]
    assert ops[0].args.get("idempotency_key") == "k-1"
    assert ops[0].args.get("role") == {"code": None, "name": "运维角色", "status": None, "version": 1}
    assert writer.calls == []
    body = client.requests[0].json_body
    assert body is not None
    assert body.get("xid") == "xid-m"
    assert body.get("db_key") == build_tenant_db_key("demo", service="mdm")
    entries = cast("list[ConcurrentStableDict[str, object]]", body.get("ops"))
    assert [entry.get("op") for entry in entries] == ["mdm.role-posts.assign", "mdm.role-depts.assign"]
    assert list(manager.commits) == ["gtx-1"]
    assert manager.rollbacks == []
    assert list(cache.bumped) == ["bms:1001:permission:version"]


async def test_xa_path_without_org_declares_platform_branch_only() -> None:
    """XA 路径（无组织域分段）：只声明 platform 分支并提交，不发远端调用。"""
    manager = _ManagerSpy()
    client = _ClientSpy()
    service, _writer, cache = _service(manager, _ParticipantSpy(), client, user_ids=ConcurrentStableList([7]))

    await service.apply(role_id=5, req=RoleAssignmentsRequest(role=RoleAssignmentProfile(name="运维角色", version=1)))

    _caller, specs = manager.begun[0]
    assert [spec.branch_id for spec in specs] == ["p"]
    assert client.requests == []
    assert list(manager.commits) == ["gtx-1"]
    assert list(cache.bumped) == ["bms:1001:permission:version"]


async def test_xa_path_rolls_back_when_platform_branch_rejected() -> None:
    """platform 分支未达 `PREPARED` → 10013 并回滚全局事务。"""
    manager = _ManagerSpy()
    service, _writer, _cache = _service(manager, _ParticipantSpy(state=BRANCH_REJECTED), _ClientSpy())

    with pytest.raises(TransactionUnavailableError):
        await service.apply(
            role_id=5, req=RoleAssignmentsRequest(role=RoleAssignmentProfile(name="运维角色", version=1))
        )

    assert list(manager.rollbacks) == ["gtx-1"]
    assert manager.commits == []


async def test_xa_path_rolls_back_when_org_branch_rejected() -> None:
    """组织域分支未达 `PREPARED` → 10013 并回滚全局事务。"""
    manager = _ManagerSpy()
    service, _writer, _cache = _service(manager, _ParticipantSpy(), _ClientSpy(state="rejected"))

    with pytest.raises(TransactionUnavailableError):
        await service.apply(
            role_id=5,
            req=RoleAssignmentsRequest(role_depts=RoleAssignmentDepts(dept_ids=ConcurrentStableList([21]))),
        )

    assert list(manager.rollbacks) == ["gtx-1"]


async def test_xa_path_missing_branch_raises() -> None:
    """全局事务快照缺分支 → 10013 并回滚。"""
    manager = _ManagerSpy(branches=ConcurrentStableList(()))
    service, _writer, _cache = _service(manager, _ParticipantSpy(), _ClientSpy())

    with pytest.raises(TransactionUnavailableError):
        await service.apply(
            role_id=5, req=RoleAssignmentsRequest(role=RoleAssignmentProfile(name="运维角色", version=1))
        )

    assert list(manager.rollbacks) == ["gtx-1"]


async def test_execute_org_branches_returns_early_without_org_segments() -> None:
    """无组织域分段时组织分支执行直接返回（不发起远端调用）。"""
    client = _ClientSpy()
    service, _writer, _cache = _service(_ManagerSpy(), _ParticipantSpy(), client)

    await service._execute_org_branches(  # pyright: ignore[reportPrivateUsage]
        xid="x",
        db_key="k",
        role_id=5,
        req=RoleAssignmentsRequest(role=RoleAssignmentProfile(name="运维角色", version=1)),
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
        _branch_state(response)  # pyright: ignore[reportPrivateUsage]


def test_branch_state_returns_state() -> None:
    """分支状态解析：2xx + `code=0` + `data.state` → 原样返回。"""
    response = ServiceResponse(status_code=200, content=json.dumps({"code": 0, "data": {"state": "prepared"}}).encode())
    assert _branch_state(response) == "prepared"  # pyright: ignore[reportPrivateUsage]
