"""平台服务权限解析器用例（`04_01` 下沉后）：mdm 组织链降级 / 出口解析 / 并集收敛。

引擎主流程、校验器判定与数据来源接缝的逐分支用例已下沉基座
（`libs/bms_core/tests/permission/{test_engine,test_sources}.py`）；本文件只覆盖**平台侧取数件**：

- `OrgRoleResolver`：跨服务不可达降级、严格模式抛错、非 2xx 降级、出口载荷解析与形态回落；
- `DirectRoleResolver`：真实仓储取数（`sys_user_role`）；
- 主体链并集：多解析器结果去重合并（基座收敛服务 + 平台解析器组合）。
"""

from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.exceptions import InternalError
from bms_core.permission.snapshot import set_current_permission_snapshot
from bms_core.permission.subject import PermissionSubjectService
from bms_platform.services.permission_subject import DirectRoleResolver, OrgRoleResolver


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
            request: 请求（忽略）。

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
    """每例前后清空快照与上下文。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    yield
    set_current_permission_snapshot(None)
    current_user_id.set(None)
    current_tenant_id.set(None)


@pytest.mark.kiwi_id(2320)
async def test_org_resolver_degrades_when_service_unreachable() -> None:
    """跨服务降级：mdm 不可达 → 空集 + 不抛（缺省口径）；严格模式抛 `InternalError`。"""
    degraded = OrgRoleResolver(_Client(error=RuntimeError("conn refused")))  # type: ignore[arg-type]
    assert list(await degraded.resolve(user_id=1)) == []
    strict = OrgRoleResolver(_Client(error=RuntimeError("conn refused")), require_roles=True)  # type: ignore[arg-type]
    with pytest.raises(InternalError):
        await strict.resolve(user_id=1)
    bad_status = OrgRoleResolver(_Client(response=_Response(502, {})))  # type: ignore[arg-type]
    assert list(await bad_status.resolve(user_id=1)) == []


@pytest.mark.kiwi_id(2320)
async def test_org_resolver_reads_role_ids_from_payload() -> None:
    """出口解析：`data.role_ids` 取并集；非整数项忽略。"""
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    inner: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    inner.set("role_ids", [7, 8, "x", True])
    payload.set("data", dict(inner))
    resolver = OrgRoleResolver(_Client(response=_Response(200, dict(payload))))  # type: ignore[arg-type]
    assert sorted(await resolver.resolve(user_id=5)) == [7, 8]


@pytest.mark.kiwi_id(2320)
async def test_org_resolver_payload_shape_fallbacks() -> None:
    """出口解析回落：`data` 非对象 / `role_ids` 非序列 → 空集。"""
    bad_data = OrgRoleResolver(_Client(response=_Response(200, {"data": "x"})))  # type: ignore[arg-type]
    assert list(await bad_data.resolve(user_id=1)) == []

    bad_ids = OrgRoleResolver(_Client(response=_Response(200, {"data": {"role_ids": "x"}})))  # type: ignore[arg-type]
    assert list(await bad_ids.resolve(user_id=1)) == []


@pytest.mark.kiwi_id(2320)
async def test_subject_service_unions_resolvers() -> None:
    """主体链并集：多解析器结果去重合并（基座收敛服务驱动平台解析器）。"""

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
                user_id: 用户主键（忽略）。

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


@pytest.mark.kiwi_id(2320)
def test_subject_service_from_registry() -> None:
    """按基座注册表构造主体链服务（缺省装配路径）。"""
    service = PermissionSubjectService.from_registry()
    assert isinstance(service, PermissionSubjectService)


@pytest.mark.kiwi_id(2320)
async def test_direct_resolver_reads_user_roles() -> None:
    """直接角色解析器：经仓储取 `sys_user_role` 未软删角色（替身仓储）。"""

    class _Repo:
        """`UserRoleRepository` 替身。"""

        async def list_role_ids_by_user(self, user_id: int) -> ConcurrentStableList[int]:
            """返回固定角色集合。

            Args:
                user_id: 用户主键（忽略）。

            Returns:
                ConcurrentStableList[int]: 角色主键列表。
            """
            del user_id
            result: ConcurrentStableList[int] = ConcurrentStableList()
            result.add(11)
            result.add(12)
            return result

    resolver = DirectRoleResolver(_Repo())  # type: ignore[arg-type]
    assert sorted(await resolver.resolve(user_id=5)) == [11, 12]
