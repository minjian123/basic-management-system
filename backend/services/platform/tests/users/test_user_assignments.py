"""用户保存编排（`02_02/_02` · Kiwi 2278）：分段校验 + 双路径编排（顺序提交路径）+ 提交后副作用。

覆盖：分段收集（`null` 不参与）与「主要项须落在集合内」（10001）；`provider=null` 顺序提交路径的
编排顺序（platform 本地写入 → 组织域内部写通道 ×2）与提交后副作用（角色段 ⇒ 权限版本 +1；停用 ⇒
会话失效尽力而为）；组织域**分支载荷**构造（同一分支内两 op）。
XA 全局事务路径的真库两阶段由 CI `2pc` 作业与 `05_07` 收尾验证（本机无 docker / 无真库）。
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_core.transaction.null import NullTransactionManager, NullTransactionParticipant
from bms_platform.schemas.users import (
    UserAssignmentDepts,
    UserAssignmentPosts,
    UserAssignmentProfile,
    UserAssignmentsRequest,
)
from bms_platform.services.user_assignments import (
    ORG_INTERNAL_USER_DEPTS_PATH,
    ORG_INTERNAL_USER_POSTS_PATH,
    ORG_USER_DEPTS_OP,
    ORG_USER_POSTS_OP,
    UserAssignmentsService,
    build_org_ops,
    collect_segments,
)

pytestmark = [pytest.mark.kiwi_id(2278)]


class _User:
    """用户记录替身（编排返回面所需的最小字段）。"""

    def __init__(self, user_id: int, *, status: str = "enabled") -> None:
        """初始化。

        Args:
            user_id: 用户主键。
            status: 账号状态。
        """
        self.id = user_id
        self.username = f"u{user_id}"
        self.name = f"用户{user_id}"
        self.status = status
        self.version = 1


class _WriterSpy:
    """写入器替身（记录入参，不落库）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.calls: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    async def write(self, *, user_id: int, profile: object, role_ids: object) -> object:
        """记录一次写入调用。

        Args:
            user_id: 用户主键。
            profile: 基础资料分段。
            role_ids: 角色分段。

        Returns:
            object: 用户记录替身。
        """
        call: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        call.set("user_id", user_id)
        call.set("profile", profile)
        call.set("role_ids", role_ids)
        self.calls.add(call)
        return _User(user_id)


class _ClientSpy:
    """服务间调用客户端替身（记录请求并回「已就绪」状态）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录调用并回成功响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: `state=prepared` 的成功响应。
        """
        self.requests.add(request)
        body = json.dumps({"code": 0, "data": {"state": "prepared"}}).encode("utf-8")
        return ServiceResponse(status_code=200, content=body)


class _CacheSpy:
    """缓存 Region 替身（记录权限版本递增键）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.bumped: ConcurrentStableList[str] = ConcurrentStableList()

    async def aincrease(self, key: str) -> int:
        """记录递增键。

        Args:
            key: 键。

        Returns:
            int: 递增后的值（替身恒 1）。
        """
        self.bumped.add(key)
        return 1


class _SessionsSpy:
    """会话失效客户端替身（记录撤销调用）。"""

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

    def __init__(self, user: _User) -> None:
        """初始化。

        Args:
            user: 用户记录替身。
        """
        self.user = user

    async def get_by_id(self, user_id: int) -> _User | None:
        """按主键取用户。

        Args:
            user_id: 用户主键。

        Returns:
            _User | None: 用户记录替身。
        """
        return self.user if user_id == self.user.id else None


class _UserRolesSpy:
    """角色分配仓储替身（回读用户直接角色）。"""

    def __init__(self, role_ids: ConcurrentStableList[int]) -> None:
        """初始化。

        Args:
            role_ids: 用户直接角色主键。
        """
        self.role_ids = role_ids

    async def list_role_ids_by_user(self, user_id: int) -> ConcurrentStableList[int]:
        """取用户直接角色主键。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[int]: 角色主键。
        """
        return self.role_ids


class _RolesSpy:
    """角色仓储替身（回读角色记录）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.codes: ConcurrentStableList[str] = ConcurrentStableList()

    async def list_by_ids(self, role_ids: object) -> ConcurrentStableList[object]:
        """取角色记录。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[object]: 角色记录替身清单。
        """

        class _Role:
            def __init__(self) -> None:
                self.id = 1
                self.code = "role_a"
                self.name = "角色甲"
                self.role_type = "custom"

        return ConcurrentStableList([_Role()])


def _service(
    manager: Any,
    participant: Any,
    client: _ClientSpy,
    *,
    user: _User | None = None,
) -> tuple[UserAssignmentsService, _WriterSpy, _CacheSpy, _SessionsSpy]:
    """构造编排服务与替身。

    Args:
        manager: 事务管理器（替身或 Null 实现）。
        participant: 事务参与方（替身或 Null 实现）。
        client: 服务间调用客户端替身。
        user: 用户记录替身（缺省启用态）。

    Returns:
        tuple[UserAssignmentsService, _WriterSpy, _CacheSpy, _SessionsSpy]: (服务, 写入器, 缓存, 会话)。
    """
    writer = _WriterSpy()
    cache = _CacheSpy()
    sessions = _SessionsSpy()
    service = UserAssignmentsService(
        writer=cast("Any", writer),
        user_roles=cast("Any", _UserRolesSpy(ConcurrentStableList([1]))),
        roles=cast("Any", _RolesSpy()),
        users=cast("Any", _UsersSpy(user or _User(7))),
        sessions=cast("Any", sessions),
        cache=cast("Any", cache),
        manager=manager,
        participant=participant,
        client=cast("Any", client),
        tenant_id="1001",
    )
    return service, writer, cache, sessions


def _collect(req: UserAssignmentsRequest) -> ConcurrentStableList[str]:
    """以最小实例调用分段收集（纯逻辑，不触外部依赖）。

    Args:
        req: 分段请求。

    Returns:
        ConcurrentStableList[str]: 参与分段名。
    """
    return collect_segments(req)


def test_collect_segments_and_primary_bounds() -> None:
    """分段收集：`null` 不参与；主要项须落在集合内（越界 10001）。"""
    assert _collect(UserAssignmentsRequest()) == []

    segments = _collect(
        UserAssignmentsRequest(
            profile=UserAssignmentProfile(version=1),
            role_ids=ConcurrentStableList(),
            user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([11]), primary_post_id=11),
            user_depts=UserAssignmentDepts(dept_ids=ConcurrentStableList(), primary_dept_id=None),
        )
    )
    assert list(segments) == ["profile", "role_ids", "user_posts", "user_depts"]

    with pytest.raises(ParamError):
        _collect(
            UserAssignmentsRequest(
                user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([11]), primary_post_id=12)
            )
        )

    with pytest.raises(ParamError):
        _collect(
            UserAssignmentsRequest(
                user_depts=UserAssignmentDepts(dept_ids=ConcurrentStableList([21]), primary_dept_id=22)
            )
        )


async def test_sequential_path_orders_writes_and_bumps_permission_version() -> None:
    """`provider=null`（顺序提交）：本地写入 → 组织域内部写通道 ×2；角色段 ⇒ 权限版本 +1。"""
    client = _ClientSpy()
    service, writer, cache, sessions = _service(NullTransactionManager(), NullTransactionParticipant(), client)

    user, roles, applied = await service.apply(
        user_id=7,
        req=UserAssignmentsRequest(
            profile=UserAssignmentProfile(name="张三丰", version=1),
            role_ids=ConcurrentStableList([1]),
            user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([11]), primary_post_id=11),
            user_depts=UserAssignmentDepts(dept_ids=ConcurrentStableList([21]), primary_dept_id=None),
        ),
        idempotency_key="k-1",
    )

    assert user.id == 7
    assert [role.code for role in roles] == ["role_a"]
    assert list(applied) == ["profile", "role_ids", "user_posts", "user_depts"]
    assert len(writer.calls) == 1
    paths = [request.path for request in client.requests]
    assert paths == [
        ORG_INTERNAL_USER_POSTS_PATH.format(user_id=7),
        ORG_INTERNAL_USER_DEPTS_PATH.format(user_id=7),
    ]
    assert client.requests[0].headers is not None
    assert client.requests[0].headers.get("Idempotency-Key") == "k-1"
    assert list(cache.bumped) == ["bms:1001:permission:version"]
    assert sessions.revoked == []


async def test_sequential_path_revokes_sessions_when_disabled() -> None:
    """停用账号：提交后尽力而为地失效其全部会话。"""
    client = _ClientSpy()
    service, _writer, _cache, sessions = _service(NullTransactionManager(), NullTransactionParticipant(), client)

    await service.apply(
        user_id=7,
        req=UserAssignmentsRequest(profile=UserAssignmentProfile(status="disabled", version=1)),
        idempotency_key=None,
    )

    assert list(sessions.revoked) == [7]
    assert client.requests == []


def test_org_branch_ops_share_one_branch_request() -> None:
    """组织域分支载荷：岗位 / 部门各一 op，同一分支（同一 `xid`）一次请求内按序执行。"""
    req = UserAssignmentsRequest(
        user_posts=UserAssignmentPosts(post_ids=ConcurrentStableList([11, 12]), primary_post_id=12),
        user_depts=UserAssignmentDepts(dept_ids=ConcurrentStableList([21]), primary_dept_id=21),
    )
    ops = build_org_ops(user_id=7, req=req, idempotency_key="k-1")

    assert [op for op, _args in ops] == [ORG_USER_POSTS_OP, ORG_USER_DEPTS_OP]
    posts_args = ops[0][1]
    assert posts_args.get("user_id") == 7
    assert posts_args.get("post_ids") == [11, 12]
    assert posts_args.get("primary_post_id") == 12
    depts_args = ops[1][1]
    assert depts_args.get("dept_ids") == [21]
    assert depts_args.get("primary_dept_id") == 21
