"""平台服务 services 层：主体链收敛（`02_04`）。

主体链 = 用户经**任意来源**获得的角色并集：

- 直接角色（`DirectRoleResolver`）：platform 租户库 `sys_user_role`，同库查询；
- 岗位 / 部门链角色（`OrgRoleResolver`）：mdm 只读出口 `GET /api/v1/org/user-roles`（服务令牌 `aud=service`，
  mdm 出口白名单只放行 `platform`）。

**主流程只做「解析器并集去重」**：来源增减一律经基座注册表（`bms_core.permission.resolver`）登记，
不改本服务主流程（《02_04 详细设计》§11.2 接缝 1）。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.core.exceptions import InternalError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_id_str
from bms_core.permission.resolver import BaseRoleResolver, registered_role_resolvers
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest
from bms_platform.repositories.role import UserRoleRepository

_logger = logging.getLogger(__name__)

ORG_SERVICE_KEY = "org"
"""mdm 组织域服务标识（服务目录登记名；服务间基址模板占位 `{service}`）。"""

ORG_USER_ROLES_PATH = "/api/v1/org/user-roles"
"""mdm 只读出口路径：按用户解析角色（响应 `data.role_ids: integer[]`）。"""


class DirectRoleResolver(BaseRoleResolver):
    """直接角色解析器（`sys_user_role`；platform 租户库同库查询）。"""

    key: str = "direct"
    order: int = 10

    def __init__(self, user_roles: UserRoleRepository) -> None:
        """初始化。

        Args:
            user_roles: 角色 × 用户分配仓储（`sys_user_role`）。
        """
        self._user_roles = user_roles

    async def resolve(self, *, user_id: int) -> ConcurrentStableSet[int]:
        """解析用户直接分配的角色主键集合。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合（未去重由主流程统一处理）。
        """
        return ConcurrentStableSet(await self._user_roles.list_role_ids_by_user(user_id))


class OrgRoleResolver(BaseRoleResolver):
    """岗位 / 部门链角色解析器（mdm 只读出口；不可达按降级或严格模式处置）。"""

    key: str = "org"
    order: int = 20

    def __init__(self, client: BaseServiceClient, *, require_roles: bool = False) -> None:
        """初始化。

        Args:
            client: 服务间同步调用客户端（附服务令牌，`aud=service`）。
            require_roles: 严格模式（跨服务失败即拒；缺省 False 表示降级——仅直接角色生效并上报）。
        """
        self._client = client
        self._require_roles = require_roles

    async def resolve(self, *, user_id: int) -> ConcurrentStableSet[int]:
        """解析用户经岗位 / 部门链获得的角色主键集合。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合（不可达且非严格模式时为空集）。

        Raises:
            InternalError: 严格模式下跨服务解析失败（10002）。
        """
        query: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        query.set("user_id", str(user_id))
        request = ServiceRequest(
            service=ORG_SERVICE_KEY,
            method="GET",
            path=ORG_USER_ROLES_PATH,
            query=query,
            tenant_id=current_tenant_id_str(),
        )
        try:
            response = await self._client.call(request)
        except Exception as exc:  # 跨服务异常（网络 / 熔断 / 限流）一律按不可达处置
            return self._degrade(f"组织域不可达：{exc}")
        if response.status_code != 200:
            return self._degrade(f"组织域返回状态码 {response.status_code}")
        return _read_role_ids(response.payload())

    def _degrade(self, reason: str) -> ConcurrentStableSet[int]:
        """按口径处置跨服务失败（严格模式抛错、否则降级并上报）。

        Args:
            reason: 失败原因（入日志）。

        Returns:
            ConcurrentStableSet[int]: 空集合（降级路径）。

        Raises:
            InternalError: 严格模式（`require_roles`）下的失败（10002）。
        """
        if self._require_roles:
            raise InternalError(f"跨服务角色解析失败（严格模式）：{reason}")
        _logger.warning("岗位 / 部门链角色降级：仅用户直接角色生效（%s）", reason)
        return ConcurrentStableSet()


def _read_role_ids(payload: object) -> ConcurrentStableSet[int]:
    """从出口响应体取 `data.role_ids`（缺字段 / 类型异常一律回落空集）。

    Args:
        payload: 响应体 JSON（`ServiceResponse.payload()` 产物）。

    Returns:
        ConcurrentStableSet[int]: 角色主键集合。
    """
    row = cast("Any", payload)
    if not isinstance(row, dict):
        return ConcurrentStableSet()
    data = cast("Any", row).get("data")
    if not isinstance(data, dict):
        return ConcurrentStableSet()
    raw = cast("Any", data).get("role_ids")
    if not isinstance(raw, list | tuple):
        return ConcurrentStableSet()
    result: ConcurrentStableSet[int] = ConcurrentStableSet()
    for item in cast("Any", raw):
        if isinstance(item, int) and not isinstance(item, bool):
            result.add(item)
    return result


class PermissionSubjectService(BaseFrameworkObject):
    """主体链收敛服务：按注册顺序执行解析器并做并集去重。"""

    def __init__(self, resolvers: tuple[BaseRoleResolver, ...]) -> None:
        """初始化。

        Args:
            resolvers: 解析器有序元组（装配期经基座注册表取用，便于测试注入）。
        """
        self._resolvers = resolvers

    @classmethod
    def from_registry(cls) -> PermissionSubjectService:
        """按基座注册表构造（装配期缺省路径）。

        Returns:
            PermissionSubjectService: 服务实例。
        """
        return cls(registered_role_resolvers())

    async def resolve_role_ids(self, user_id: int) -> ConcurrentStableSet[int]:
        """收敛用户角色集合（各来源并集去重）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合（插入序稳定）。
        """
        merged: ConcurrentStableSet[int] = ConcurrentStableSet()
        for resolver in self._resolvers:
            resolved = await resolver.resolve(user_id=user_id)
            for role_id in resolved:
                merged.add(role_id)
        return merged
