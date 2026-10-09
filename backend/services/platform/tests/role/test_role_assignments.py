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
from bms_core.core.exceptions import ConcurrentConflictError, RoleProtectedError, RoleSubjectInvalidError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
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
    ORG_INTERNAL_ROLE_DEPTS_PATH,
    ORG_INTERNAL_ROLE_POSTS_PATH,
    ORG_ROLE_DEPTS_OP,
    ORG_ROLE_POSTS_OP,
    RoleAssignmentsService,
    RoleAssignmentWriter,
    build_org_ops,
    collect_segments,
)
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
    """服务间调用客户端替身（记录请求并回「已就绪」状态）。"""

    def __init__(self) -> None:
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录调用并回成功响应。"""
        self.requests.add(request)
        body = json.dumps({"code": 0, "data": {"state": "prepared"}}).encode("utf-8")
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
) -> tuple[RoleAssignmentsService, _WriterSpy, _CacheSpy]:
    """构造编排服务与替身。"""
    writer = _WriterSpy()
    cache = _CacheSpy()
    resolved_users = users if users is not None else ConcurrentStableList([_User(7)])
    resolved_ids = user_ids if user_ids is not None else ConcurrentStableList([7])
    service = RoleAssignmentsService(
        writer=cast("Any", writer),
        roles=cast("Any", _RolesSpy()),
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
    assert paths == [ORG_INTERNAL_ROLE_POSTS_PATH.format(role_id=5)]
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
    assert [request.path for request in client.requests] == [ORG_INTERNAL_ROLE_DEPTS_PATH.format(role_id=5)]


def test_org_branch_ops_share_one_branch_request() -> None:
    """组织域分支载荷：岗位 / 部门各一 op，同一分支（同一 `xid`）一次请求内按序执行。"""
    req = RoleAssignmentsRequest(
        role_posts=RoleAssignmentPosts(post_ids=ConcurrentStableList([11, 12])),
        role_depts=RoleAssignmentDepts(dept_ids=ConcurrentStableList([21])),
    )
    ops = build_org_ops(role_id=5, req=req, idempotency_key="k-1")

    assert [op for op, _args in ops] == [ORG_ROLE_POSTS_OP, ORG_ROLE_DEPTS_OP]
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


def _writer(target: AsyncSession) -> RoleAssignmentWriter:
    """构造 platform 侧写入器（真实仓储 + 内存会话）。"""
    return RoleAssignmentWriter(
        target,
        DbUnitOfWork(target),
        RoleRepository(target),
        UserRoleRepository(target),
        UserRepository(target),
        NullConfigSource(),
    )


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
