"""权限引擎用例（`02_04`）：码级判定 / 豁免 / 未预加载从严 / 校验链接缝 / 跨服务降级 / 失效链路 / 聚合。

均以替身驱动主流程（不接库）：校验器读 contextvar 快照；主体链解析器、聚合仓储、
菜单元数据快照均为轻量替身——覆盖**判定口径**与**接缝行为**，存储正确性由服务侧用例覆盖。
"""

from collections.abc import Iterator

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.exceptions import InternalError
from bms_core.permission.guard import (
    BasePermissionGuard,
    PermissionGuardContext,
    register_permission_guard,
    reset_permission_guards,
)
from bms_core.permission.snapshot import (
    TIER_PLATFORM_ADMIN,
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    set_current_permission_snapshot,
)
from bms_core.permission.version import permission_user_cache_key, permission_version_key
from bms_platform.services.permission import PermissionService, invalidate_permission_cache
from bms_platform.services.permission_subject import DirectRoleResolver, OrgRoleResolver, PermissionSubjectService


class _DenyGuard(BasePermissionGuard):
    """恒拒校验链环节（测接缝 3：码命中后仍可被条件环节拦下）。"""

    key: str = "deny_all"

    def allow(self, context: PermissionGuardContext) -> bool:
        """恒拒。

        Args:
            context: 校验上下文。

        Returns:
            bool: False。
        """
        del context
        return False


class _Response:
    """服务间响应替身。"""

    def __init__(self, status_code: int, data: object) -> None:
        """初始化。

        Args:
            status_code: 状态码。
            data: 响应体。
        """
        self.status_code = status_code
        self._data = data

    def payload(self) -> object:
        """响应体。

        Returns:
            object: 响应体。
        """
        return self._data


class _Client:
    """服务间客户端替身（可配置抛错 / 响应）。"""

    def __init__(self, *, response: object = None, error: Exception | None = None) -> None:
        """初始化。

        Args:
            response: 返回值。
            error: 抛出的异常。
        """
        self.response = response
        self.error = error

    async def call(self, request: object) -> object:
        """模拟调用。

        Args:
            request: 请求。

        Returns:
            object: 响应替身。

        Raises:
            Exception: 配置的异常。
        """
        del request
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    """每例前后清空快照 / 校验链 / 上下文。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    reset_permission_guards()
    yield
    set_current_permission_snapshot(None)
    reset_permission_guards()
    current_user_id.set(None)
    current_tenant_id.set(None)


@pytest.mark.kiwi_id(2269)
def test_check_uses_snapshot_codes() -> None:
    """码级判定：业务码 / 动作码命中即通过；未命中即拒。"""
    from bms_platform.permission.checker import RbacPermissionChecker

    checker = RbacPermissionChecker()
    codes: ConcurrentStableSet[str] = ConcurrentStableSet()
    codes.add("menu")
    actions: ConcurrentStableSet[str] = ConcurrentStableSet()
    actions.add("role:grant")
    set_current_permission_snapshot(
        PermissionSnapshot(tier=TIER_STANDARD, business_codes=codes, action_codes=actions)
    )
    assert checker.check("menu") is True
    assert checker.check("role:grant") is True
    assert checker.check("role:delete") is False


@pytest.mark.kiwi_id(2269)
def test_check_denies_without_preloaded_snapshot() -> None:
    """未预加载（依赖漏挂）时**从严拒绝**，而非放行。"""
    from bms_platform.permission.checker import RbacPermissionChecker

    checker = RbacPermissionChecker()
    assert checker.check("menu") is False


@pytest.mark.kiwi_id(2269)
def test_exempt_tiers_allow_all() -> None:
    """豁免层级（系统管理员 / 平台层）恒通过，且不校验码集。"""
    from bms_platform.permission.checker import RbacPermissionChecker

    checker = RbacPermissionChecker()
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_SYSTEM_ADMIN))
    assert checker.check("anything:at-all") is True
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_PLATFORM_ADMIN))
    assert checker.check("anything:at-all") is True


@pytest.mark.kiwi_id(2269)
def test_guard_chain_can_deny_after_code_hit() -> None:
    """校验链（接缝 3）：码命中后仍可被条件环节拦下；移出环节即恢复。"""
    from bms_platform.permission.checker import RbacPermissionChecker

    checker = RbacPermissionChecker()
    actions: ConcurrentStableSet[str] = ConcurrentStableSet()
    actions.add("role:grant")
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_STANDARD, action_codes=actions))
    assert checker.check("role:grant") is True
    register_permission_guard(_DenyGuard())
    assert checker.check("role:grant") is False
    reset_permission_guards()
    assert checker.check("role:grant") is True


@pytest.mark.kiwi_id(2269)
async def test_org_resolver_degrades_when_service_unreachable() -> None:
    """跨服务降级：mdm 不可达 → 空集 + 不抛（缺省口径）；严格模式抛 `InternalError`。"""
    degraded = OrgRoleResolver(_Client(error=RuntimeError("conn refused")))  # type: ignore[arg-type]
    assert list(await degraded.resolve(user_id=1)) == []
    strict = OrgRoleResolver(_Client(error=RuntimeError("conn refused")), require_roles=True)  # type: ignore[arg-type]
    with pytest.raises(InternalError):
        await strict.resolve(user_id=1)
    bad_status = OrgRoleResolver(_Client(response=_Response(502, {})))  # type: ignore[arg-type]
    assert list(await bad_status.resolve(user_id=1)) == []


@pytest.mark.kiwi_id(2269)
async def test_org_resolver_reads_role_ids_from_payload() -> None:
    """出口解析：`data.role_ids` 取并集；非整数项忽略。"""
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    inner: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    inner.set("role_ids", [7, 8, "x", True])
    payload.set("data", dict(inner))
    resolver = OrgRoleResolver(_Client(response=_Response(200, dict(payload))))  # type: ignore[arg-type]
    assert sorted(await resolver.resolve(user_id=5)) == [7, 8]


@pytest.mark.kiwi_id(2269)
async def test_subject_service_unions_resolvers() -> None:
    """主体链并集：多解析器结果去重合并。"""

    class _Fixed(DirectRoleResolver):
        """固定结果的直接角色解析器替身。"""

        def __init__(self, ids: ConcurrentStableList[int]) -> None:
            """初始化。

            Args:
                ids: 返回的角色 id。
            """
            super().__init__(object())  # type: ignore[arg-type]
            self._ids = ids

        async def resolve(self, *, user_id: int) -> ConcurrentStableSet[int]:
            """返回固定集合。

            Args:
                user_id: 用户主键。

            Returns:
                ConcurrentStableSet[int]: 角色集合。
            """
            del user_id
            result: ConcurrentStableSet[int] = ConcurrentStableSet()
            for item in self._ids:
                result.add(item)
            return result

    ids_a: ConcurrentStableList[int] = ConcurrentStableList()
    ids_a.add(1)
    ids_a.add(2)
    ids_b: ConcurrentStableList[int] = ConcurrentStableList()
    ids_b.add(2)
    ids_b.add(3)
    service = PermissionSubjectService((_Fixed(ids_a), _Fixed(ids_b)))
    assert sorted(await service.resolve_role_ids(9)) == [1, 2, 3]


@pytest.mark.kiwi_id(2269)
async def test_invalidate_bumps_version_and_evicts_previous_user_key() -> None:
    """失效链路：租户权限版本 +1，并删除受影响用户的旧版本键。"""
    cache = MemoryCacheRegion()
    version_key = permission_version_key("1001")
    await cache.aincrease(version_key)
    await cache.aincrease(version_key)
    old_key = permission_user_cache_key("1001", 7, 2)
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    await cache.aset(old_key, dict(payload), ttl=60)
    version = await invalidate_permission_cache(cache, tenant_id="1001", user_ids=(7,))
    assert version == 3
    assert await cache.aget(old_key) is None
    assert await invalidate_permission_cache(cache, tenant_id="1001") == 4


@pytest.mark.kiwi_id(2269)
async def test_engine_aggregates_menu_form_and_action_codes() -> None:
    """聚合：菜单授权连带其表单业务码、表单授权取业务码、动作授权取 `业务:动作`。"""
    service = _build_service()
    snapshot = await service.compute(user_id=5, version=1)
    assert sorted(snapshot.business_codes) == ["data", "menu"]
    assert sorted(snapshot.action_codes) == ["data:export", "role:grant"]
    assert snapshot.tier == TIER_SYSTEM_ADMIN
    assert snapshot.exempt is True


class _Form:
    """表单快照替身。"""

    def __init__(self, form_id: int, business_code: str, buttons: ConcurrentStableList[object] | None = None) -> None:
        """初始化。

        Args:
            form_id: 表单 id。
            business_code: 业务码。
            buttons: 按钮列表。
        """
        self.id = form_id
        self.business_code = business_code
        self.buttons = buttons or ConcurrentStableList()


class _Button:
    """按钮快照替身。"""

    def __init__(self, action_id: int, action_code: str) -> None:
        """初始化。

        Args:
            action_id: 动作 id。
            action_code: 动作码。
        """
        self.action_id = action_id
        self.action_code = action_code


class _Menu:
    """菜单快照替身。"""

    def __init__(self, menu_id: int, forms: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            menu_id: 菜单 id。
            forms: 表单列表。
        """
        self.id = menu_id
        self.forms = forms


class _Snapshot:
    """菜单元数据快照替身（仅聚合所需的最小面）。"""

    def __init__(self, menus: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            menus: 菜单列表。
        """
        self.menus = menus


class _Row:
    """授权行替身。"""

    def __init__(self, perm_type: str, target_id: int) -> None:
        """初始化。

        Args:
            perm_type: 授权类型。
            target_id: 目标 id。
        """
        self.perm_type = perm_type
        self.target_id = target_id


class _Role:
    """角色替身。"""

    def __init__(self, role_type: str) -> None:
        """初始化。

        Args:
            role_type: 角色类型。
        """
        self.role_type = role_type


def _build_service() -> PermissionService:
    """构造引擎（替身仓储：菜单 1 关联表单 11；表单 12 独立；动作 21 / 22）。

    Returns:
        PermissionService: 引擎实例。
    """
    grant_button = _Button(21, "role:grant")
    export_button = _Button(22, "data:export")
    forms: ConcurrentStableList[object] = ConcurrentStableList()
    forms.add(_Form(11, "menu", _button_list(grant_button)))
    menus: ConcurrentStableList[object] = ConcurrentStableList()
    menus.add(_Menu(1, forms))

    class _Metadata:
        """菜单元数据服务替身。"""

        async def load_snapshot(self, **kwargs: object) -> object:
            """返回替身快照。

            Args:
                kwargs: 调用参数（忽略）。

            Returns:
                object: 快照替身。
            """
            del kwargs
            return _Snapshot(_menus_holder)

    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_Row("menu", 1))
    rows.add(_Row("form", 12))
    rows.add(_Row("action", 21))
    rows.add(_Row("action", 22))
    rows.add(_Row("action", 99))  # 未挂按钮的动作码 → 不进快照码集

    form_twelve: ConcurrentStableList[object] = ConcurrentStableList()
    form_twelve.add(_Form(12, "data", _button_list(export_button)))
    menus.add(_Menu(2, form_twelve))
    _menus_holder = menus

    roles: ConcurrentStableList[object] = ConcurrentStableList()
    roles.add(_Role("system"))

    return PermissionService(
        roles=_StubRoles(roles),  # type: ignore[arg-type]
        permissions=_StubPermissions(rows),  # type: ignore[arg-type]
        data_scopes=_StubScopes(),  # type: ignore[arg-type]
        metadata=_Metadata(),  # type: ignore[arg-type]
        subject=_StubSubject(),  # type: ignore[arg-type]
        cache=MemoryCacheRegion(),
        profile="smb",
    )


class _StubRoles:
    """角色仓储替身。"""

    def __init__(self, roles: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            roles: 角色列表。
        """
        self._roles = roles

    async def list_by_ids(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[object]:
        """返回角色列表。

        Args:
            role_ids: 角色 id 集合。

        Returns:
            ConcurrentStableList[object]: 角色列表。
        """
        del role_ids
        return self._roles


class _StubPermissions:
    """角色授权仓储替身。"""

    def __init__(self, rows: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            rows: 授权行。
        """
        self._rows = rows

    async def list_by_roles(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[object]:
        """返回授权行。

        Args:
            role_ids: 角色 id 集合。

        Returns:
            ConcurrentStableList[object]: 授权行。
        """
        del role_ids
        return self._rows


class _StubScopes:
    """数据权限仓储替身。"""

    async def list_by_roles(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[object]:
        """返回空规则。

        Args:
            role_ids: 角色 id 集合。

        Returns:
            ConcurrentStableList[object]: 空列表。
        """
        del role_ids
        return ConcurrentStableList()


class _StubSubject:
    """主体链替身。"""

    async def resolve_role_ids(self, user_id: int) -> ConcurrentStableSet[int]:
        """返回固定角色。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色集合。
        """
        del user_id
        result: ConcurrentStableSet[int] = ConcurrentStableSet()
        result.add(1)
        return result


def _button_list(*items: object) -> ConcurrentStableList[object]:
    """收集按钮。

    Args:
        items: 按钮。

    Returns:
        ConcurrentStableList[object]: 按钮列表。
    """
    result: ConcurrentStableList[object] = ConcurrentStableList()
    for item in items:
        result.add(item)
    return result
