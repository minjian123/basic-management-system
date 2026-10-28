"""平台服务：主体链角色解析器（`04_01` 下沉后只保留**服务侧取数**部分）。

主体链收敛算法（解析器并集去重）已下沉基座 `bms_core.permission.subject`；本模块只保留两个
**数据来源相关**的解析器实现：

- 直接角色（`DirectRoleResolver`）：platform 租户库 `sys_user_role`，同库查询；
- 岗位 / 部门链角色（`OrgRoleResolver`）：按能力名取用 mdm 组织域只读出口（`07B` `03_01` 收编；
  服务标识与路径一律取自能力声明，本文件不再写产品标识与对端路径）。

解析器经基座注册表登记后由基座收敛服务统一执行——**主流程只做并集去重**，来源增减不改主流程
（《02_04 详细设计》§11.2 接缝 1）。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from bms_core.collaboration.base import CapabilityEndpoint
from bms_core.collaboration.request import build_capability_request
from bms_core.collaboration.resolver import resolve_capability
from bms_core.collaboration.usage import call_capability
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableSet
from bms_core.core.exceptions import InternalError, ServiceUnavailableError
from bms_core.db.tenant import current_tenant_id_str
from bms_core.metrics.base import BaseMetrics
from bms_core.permission.resolver import BaseRoleResolver
from bms_core.servicecall.base import BaseServiceClient
from bms_platform import SERVICE_NAME
from bms_platform.capabilities import CAPABILITY_MDM_USER_ROLES
from bms_platform.domains.role.repositories.role import UserRoleRepository

_logger = logging.getLogger(__name__)


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
    """岗位 / 部门链角色解析器（mdm 只读出口；按能力名取用，不可达按降级或严格模式处置）。"""

    key: str = "org"
    order: int = 20

    def __init__(
        self,
        client: BaseServiceClient,
        *,
        require_roles: bool = False,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            client: 服务间同步调用客户端（附服务令牌，`aud=service`）。
            require_roles: 严格模式（跨服务失败即拒；缺省 False 表示降级——仅直接角色生效并上报）。
            metrics: 指标器（降级 / 取用失败打点；None 表示不记录）。
        """
        self._client = client
        self._require_roles = require_roles
        self._metrics = metrics

    async def resolve(self, *, user_id: int) -> ConcurrentStableSet[int]:
        """解析用户经岗位 / 部门链获得的角色主键集合。

        失败处置分两档：非严格模式经 `call_capability()` 按清单声明降级（有效声明 = `empty`，
        降级日志与指标由基座一次完成）；严格模式**不走降级通道**（声明是应用级的、不能按实例分档），
        直接取用并上抛。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合（不可达且非严格模式时为空集）。

        Raises:
            InternalError: 严格模式下跨服务解析失败（10002）。
            ParamError: 能力未声明 / 已禁用（10001，取用入口抛出的契约断链）。
        """
        if self._require_roles:
            return await self._resolve_required(user_id=user_id)
        return await call_capability(
            CAPABILITY_MDM_USER_ROLES,
            consumer=SERVICE_NAME,
            metrics=self._metrics,
            call=lambda endpoint: self._fetch(endpoint, user_id=user_id),
            fallback=_empty_role_ids,
        )

    async def _resolve_required(self, *, user_id: int) -> ConcurrentStableSet[int]:
        """严格模式取用（失败一律转 `InternalError`，不做降级）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合。

        Raises:
            InternalError: 取用或调用失败（10002）。
        """
        try:
            endpoint = resolve_capability(CAPABILITY_MDM_USER_ROLES)
            return await self._fetch(endpoint, user_id=user_id)
        except Exception as exc:
            raise InternalError(f"跨服务角色解析失败（严格模式）：{exc}") from exc

    async def _fetch(self, endpoint: CapabilityEndpoint, *, user_id: int) -> ConcurrentStableSet[int]:
        """按取用结果调 mdm 组织域只读出口并解析角色主键。

        Args:
            endpoint: 能力取用结果（服务标识与路径均取自声明）。
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合。

        Raises:
            ServiceUnavailableError: 非 2xx 响应（10007；由调用方的降级口径处置）。
        """
        request = build_capability_request(
            endpoint,
            method="GET",
            query=ConcurrentStableFrozenDict({"user_id": str(user_id)}),
            tenant_id=current_tenant_id_str(),
        )
        response = await self._client.call(request)
        if response.status_code != 200:
            raise ServiceUnavailableError(f"组织域返回状态码 {response.status_code}")
        return _read_role_ids(response.payload())


def _empty_role_ids() -> ConcurrentStableSet[int]:
    """降级兜底值：空角色集合（仅在清单声明了 `degrade = "empty"` 时被调用）。

    Returns:
        ConcurrentStableSet[int]: 空集合。
    """
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
