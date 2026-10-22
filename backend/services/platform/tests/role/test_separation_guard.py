"""三权分立校验器用例（Kiwi 2314，`03_02`，需求 07-6）。

覆盖 `services/separation.py` 的全部判定分支：

- `RoleBusinessPermissions.permission_ids`：命中 `sys_business(code='role')` 与业务码缺失（空集）；
- `SeparationGuard.ensure_role_domain_operator`：无操作人 / 自定义角色 / 安全管理员放行，
  系统管理员与审计管理员拒绝（`30048`），系统 + 安全兼任（测试装配）放行；
- `ensure_role_grant_exclusive`（增量分配）：目标非三权类型放行、同类角色放行、异类冲突拒绝（`30010`）；
- `ensure_user_roles_exclusive`（全量覆盖）：单类型 / 仅自定义放行，两类拒绝（`30010`）；
- `ensure_grant_scope` / `ensure_not_self_lock`：`role` 业务归属（仅安全管理员）与防自锁（`30048`）；
- 审计留痕：四类拒绝均经 `AuditCapturer.capture()` 产生事件；无捕获器时跳过。
"""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import reset_current_user_id, set_current_user_id
from bms_core.core.exceptions import RoleSeparationConflictError, UserSeparationConflictError
from bms_core.events.base import EventEnvelope
from bms_core.models.platform.role import (
    ROLE_TYPE_AUDIT,
    ROLE_TYPE_CUSTOM,
    ROLE_TYPE_SECURITY,
    ROLE_TYPE_SYSTEM,
    SysRole,
)
from bms_platform.repositories.menu import ActionRepository, BusinessRepository, PermissionRepository
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.services.separation import RoleBusinessPermissions, SeparationGuard
from tests.role import helpers

_ACTOR = 7001


class _RecordingCapturer(AuditCapturer):
    """记录型审计捕获器（断言拒绝尝试产生审计事件；不落库）。"""

    def __init__(self) -> None:
        """初始化空事件清单。"""
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    def is_audited(self, table: str) -> bool:
        """三权拒绝涉及的表均视为审计表。

        Args:
            table: 表名。

        Returns:
            bool: 恒 True（用例只关心是否被调用）。
        """
        return table in {"sys_user_role", "sys_role", "sys_role_permission"}

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """记录审计事件。

        Args:
            table: 表名。
            model_id: 记录主键。
            changes: 字段变更清单。
            actor: 操作人主键。

        Returns:
            EventEnvelope: 审计事件。
        """
        envelope = EventEnvelope(
            event_type="audit.separation_rejected",
            payload=ConcurrentStableDict(
                {"table": table, "model_id": model_id, "actor": actor, "changes": len(changes)}
            ),
        )
        self.events.add(envelope)
        return envelope


@pytest.fixture(autouse=True)
def actor() -> Iterator[int]:
    """置当前操作人上下文（三权判定依据 `current_user_id`）。

    Yields:
        int: 操作人主键。
    """
    token = set_current_user_id(_ACTOR)
    yield _ACTOR
    reset_current_user_id(token)


@pytest.fixture
async def session() -> AsyncIterator[tuple[AsyncSession, AsyncEngine]]:
    """临时内存库会话。

    Yields:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    target, engine = await helpers.session()
    try:
        yield target, engine
    finally:
        await engine.dispose()


def _guard(
    target: AsyncSession,
    *,
    audit: AuditCapturer | None = None,
    with_business: bool = False,
) -> SeparationGuard:
    """构造校验器。

    Args:
        target: 会话。
        audit: 审计捕获器。
        with_business: 是否装配 `role` 业务权限码读取器。

    Returns:
        SeparationGuard: 校验器。
    """
    return SeparationGuard(
        roles=RoleRepository(target),
        user_roles=UserRoleRepository(target),
        business_permissions=RoleBusinessPermissions(target) if with_business else None,
        audit=audit,
    )


async def _role(target: AsyncSession, *, code: str, role_type: str = ROLE_TYPE_CUSTOM) -> SysRole:
    """播种一个角色。

    Args:
        target: 会话。
        code: 角色码。
        role_type: 角色类型。

    Returns:
        SysRole: 角色记录。
    """
    role = await RoleRepository(target).create(code=code, name=code, role_type=role_type)
    await target.commit()
    return role


async def _user(target: AsyncSession, username: str) -> int:
    """播种一个用户。

    Args:
        target: 会话。
        username: 登录账号。

    Returns:
        int: 用户主键。
    """
    user = await UserRepository(target).create(username=username, password_hash="x", name=username)
    await target.commit()
    return user.id


async def _bind(target: AsyncSession, *, role_id: int, user_id: int) -> None:
    """绑定角色到用户。

    Args:
        target: 会话。
        role_id: 角色主键。
        user_id: 用户主键。
    """
    await UserRoleRepository(target).create(role_id=role_id, user_id=user_id)
    await target.commit()


@pytest.mark.kiwi_id(2314)
async def test_role_business_permissions_hit_and_empty(session: tuple[AsyncSession, AsyncEngine]) -> None:
    """`role` 业务权限码：命中业务码取其权限码；业务码缺失返回空集。"""
    target, _engine = session
    reader = RoleBusinessPermissions(target)
    assert await reader.permission_ids() == ConcurrentStableSet()

    business = await BusinessRepository(target).create(code="role", name="角色管理", status="enabled")
    action = await ActionRepository(target).create(code="grant", name="授权", status="enabled")
    permission = await PermissionRepository(target).create(
        business_id=business.id, action_id=action.id, status="enabled"
    )
    await target.commit()

    assert await reader.permission_ids() == ConcurrentStableSet({permission.id})


@pytest.mark.kiwi_id(2314)
async def test_operator_guard_allows_and_rejects(session: tuple[AsyncSession, AsyncEngine]) -> None:
    """操作人侧护栏：无操作人 / 自定义 / 安全管理员放行；系统与审计管理员拒绝（`30048`）。"""
    target, _engine = session
    audit = _RecordingCapturer()
    guard = _guard(target, audit=audit)

    # 无操作人上下文（内部通道 / 平台层）放行
    set_current_user_id(None)
    await guard.ensure_role_domain_operator()
    assert audit.events == []
    set_current_user_id(_ACTOR)

    # 无任何内置角色（自定义）放行
    custom = await _role(target, code="ops")
    await _bind(target, role_id=custom.id, user_id=_ACTOR)
    await guard.ensure_role_domain_operator()
    assert audit.events == []

    # 系统管理员拒绝
    system = await _role(target, code="system_admin", role_type=ROLE_TYPE_SYSTEM)
    await _bind(target, role_id=system.id, user_id=_ACTOR)
    with pytest.raises(RoleSeparationConflictError) as system_rejected:
        await guard.ensure_role_domain_operator()
    assert system_rejected.value.code == 30048
    assert len(audit.events) == 1

    # 系统 + 安全（测试装配口径）放行
    security = await _role(target, code="security_admin", role_type=ROLE_TYPE_SECURITY)
    await _bind(target, role_id=security.id, user_id=_ACTOR)
    await guard.ensure_role_domain_operator()
    assert len(audit.events) == 1

    # 审计管理员拒绝（换一名操作人）
    auditor = await _user(target, "auditor")
    audit_role = await _role(target, code="audit_admin", role_type=ROLE_TYPE_AUDIT)
    await _bind(target, role_id=audit_role.id, user_id=auditor)
    set_current_user_id(auditor)
    with pytest.raises(RoleSeparationConflictError):
        await guard.ensure_role_domain_operator()
    assert len(audit.events) == 2


@pytest.mark.kiwi_id(2314)
async def test_role_grant_exclusive_incremental(session: tuple[AsyncSession, AsyncEngine]) -> None:
    """增量分配互斥：非三权角色放行、同类放行、异类冲突拒绝（`30010`）。"""
    target, _engine = session
    audit = _RecordingCapturer()
    guard = _guard(target, audit=audit)
    user_id = await _user(target, "alice")

    custom = await _role(target, code="ops")
    await guard.ensure_role_grant_exclusive(role=custom, user_ids=ConcurrentStableList((user_id,)))

    system = await _role(target, code="system_admin", role_type=ROLE_TYPE_SYSTEM)
    # 用户尚无内置角色：放行
    await guard.ensure_role_grant_exclusive(role=system, user_ids=ConcurrentStableList((user_id,)))
    assert audit.events == []

    # 已持同类（system）再授予另一 system 角色：放行（同类不构成兼任）
    await _bind(target, role_id=system.id, user_id=user_id)
    other_system = await _role(target, code="system_admin_2", role_type=ROLE_TYPE_SYSTEM)
    await guard.ensure_role_grant_exclusive(role=other_system, user_ids=ConcurrentStableList((user_id,)))
    assert audit.events == []

    # 已持 system 再授予 security：拒绝
    security = await _role(target, code="security_admin", role_type=ROLE_TYPE_SECURITY)
    with pytest.raises(UserSeparationConflictError) as conflict:
        await guard.ensure_role_grant_exclusive(role=security, user_ids=ConcurrentStableList((user_id,)))
    assert conflict.value.code == 30010
    assert len(audit.events) == 1

    # 无捕获器时不产生事件（分支覆盖）
    silent = _guard(target)
    with pytest.raises(UserSeparationConflictError):
        await silent.ensure_role_grant_exclusive(role=security, user_ids=ConcurrentStableList((user_id,)))


@pytest.mark.kiwi_id(2314)
async def test_user_roles_exclusive_full_replace(session: tuple[AsyncSession, AsyncEngine]) -> None:
    """全量替换互斥：单类型 / 仅自定义放行；两类拒绝（`30010`）。"""
    target, _engine = session
    audit = _RecordingCapturer()
    guard = _guard(target, audit=audit)
    user_id = await _user(target, "bob")

    custom = await _role(target, code="ops")
    system = await _role(target, code="system_admin", role_type=ROLE_TYPE_SYSTEM)
    security = await _role(target, code="security_admin", role_type=ROLE_TYPE_SECURITY)

    await guard.ensure_user_roles_exclusive(
        user_ids=ConcurrentStableList((user_id,)), roles=ConcurrentStableList((custom,))
    )
    await guard.ensure_user_roles_exclusive(
        user_ids=ConcurrentStableList((user_id,)), roles=ConcurrentStableList((custom, system))
    )
    assert audit.events == []

    with pytest.raises(UserSeparationConflictError):
        await guard.ensure_user_roles_exclusive(
            user_ids=ConcurrentStableList((user_id,)), roles=ConcurrentStableList((system, security))
        )
    assert len(audit.events) == 1


@pytest.mark.kiwi_id(2314)
async def test_grant_scope_role_business_ownership(session: tuple[AsyncSession, AsyncEngine]) -> None:
    """`role` 业务归属：仅安全管理员角色可持；非安全管理员拒绝（`30048`）。"""
    target, _engine = session
    audit = _RecordingCapturer()
    guard = _guard(target, audit=audit, with_business=True)

    business = await BusinessRepository(target).create(code="role", name="角色管理", status="enabled")
    action = await ActionRepository(target).create(code="grant", name="授权", status="enabled")
    permission = await PermissionRepository(target).create(
        business_id=business.id, action_id=action.id, status="enabled"
    )
    other_business = await BusinessRepository(target).create(code="user", name="用户管理", status="enabled")
    other_permission = await PermissionRepository(target).create(
        business_id=other_business.id, action_id=action.id, status="enabled"
    )
    await target.commit()
    role_permissions = ConcurrentStableSet({permission.id})

    # 空授权 / 非 `role` 业务 / 安全管理员角色：均放行
    security = await _role(target, code="security_admin", role_type=ROLE_TYPE_SECURITY)
    await guard.ensure_grant_scope(role=security, permission_ids=ConcurrentStableSet())
    await guard.ensure_grant_scope(role=security, permission_ids=ConcurrentStableSet({other_permission.id}))
    await guard.ensure_grant_scope(role=security, permission_ids=role_permissions)
    assert audit.events == []

    # 系统 / 审计 / 自定义角色持 `role` 业务：拒绝
    for code, role_type in (
        ("system_admin", ROLE_TYPE_SYSTEM),
        ("audit_admin", ROLE_TYPE_AUDIT),
        ("ops", ROLE_TYPE_CUSTOM),
    ):
        role = await _role(target, code=code, role_type=role_type)
        with pytest.raises(RoleSeparationConflictError) as rejected:
            await guard.ensure_grant_scope(role=role, permission_ids=role_permissions)
        assert rejected.value.code == 30048
    assert len(audit.events) == 3

    # 无 `role` 业务读取器时不做归属校验（分支覆盖）
    await _guard(target).ensure_grant_scope(role=security, permission_ids=role_permissions)


@pytest.mark.kiwi_id(2314)
async def test_not_self_lock(session: tuple[AsyncSession, AsyncEngine]) -> None:
    """防自锁：操作人不得修改自身所属三权角色的授权集合（`30048`）。"""
    target, _engine = session
    audit = _RecordingCapturer()
    guard = _guard(target, audit=audit)

    security = await _role(target, code="security_admin", role_type=ROLE_TYPE_SECURITY)
    custom = await _role(target, code="ops")
    await _bind(target, role_id=security.id, user_id=_ACTOR)
    await _bind(target, role_id=custom.id, user_id=_ACTOR)

    # 他人角色 / 自身自定义角色：放行
    other_security = await _role(target, code="security_admin_2", role_type=ROLE_TYPE_SECURITY)
    await guard.ensure_not_self_lock(role=other_security)
    await guard.ensure_not_self_lock(role=custom)
    assert audit.events == []

    # 自身三权角色：拒绝
    with pytest.raises(RoleSeparationConflictError):
        await guard.ensure_not_self_lock(role=security)
    assert len(audit.events) == 1

    # 无操作人上下文：放行（内部通道）
    set_current_user_id(None)
    await guard.ensure_not_self_lock(role=security)
    assert len(audit.events) == 1
