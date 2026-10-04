"""远端关系数据源：非租户服务经**租户服务内部端点**读写用户↔租户可达关系（11_01）。

- 取数 / 写入：`GET` / `POST` / `DELETE /api/v1/tenant/internal/memberships`（租户服务提供）；
  经 `service_client` 调用，服务 JWT 携带调用方租户主键（归属租户）。
- 失败分支：非 2xx / 响应体非法 → `ServiceUnavailableError`（10007）；**由调用方决定是否阻断**
  （建号路径失败不阻断，见详细设计 §5.3）。
"""

from collections.abc import Mapping
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError, ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.tenant.membership import (
    REMOTE_TENANT_MEMBERSHIP_STORE,
    TENANT_MEMBERSHIP_INTERNAL_PATH,
    TenantMembershipTarget,
    register_tenant_membership_store,
)

__all__ = ["RemoteTenantMembershipStore", "register_remote_tenant_membership_store"]

_TENANT_SERVICE = "tenant"
"""契约提供方服务标识。"""

_LOGGER = get_logger("bms.tenant_membership_remote")


class RemoteTenantMembershipStore(BaseFrameworkObject):
    """远端关系数据源：经内部端点读写（实现 `TenantMembershipStore` 契约）。"""

    def __init__(self, *, client: BaseServiceClient, service: str = _TENANT_SERVICE) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
            service: 契约提供方服务标识。
        """
        self._client = client
        self._service = service

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取某用户可访问目标租户集合。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 目标集合。

        Raises:
            ServiceUnavailableError: 契约不可达或响应非法（10007）。
        """
        query = ConcurrentStableDict({"owner_tenant_id": str(tenant_id), "user_id": str(user_id)})
        if include_disabled:
            query.set("include_disabled", "true")
        response = await self._call("GET", query=query, tenant_scope=tenant_id)
        return _parse_targets(response)

    async def ensure(
        self, *, tenant_id: int, user_id: int, target_tenant_id: int, source: str
    ) -> TenantMembershipTarget:
        """建立 / 复活关系（幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 写入来源。

        Returns:
            TenantMembershipTarget: 建立 / 复活后的目标条目。

        Raises:
            ServiceUnavailableError: 契约不可达或响应非法（10007）。
        """
        response = await self._call(
            "POST",
            json_body=ConcurrentStableDict(
                {
                    "owner_tenant_id": tenant_id,
                    "user_id": user_id,
                    "target_tenant_id": target_tenant_id,
                    "source": source,
                }
            ),
            tenant_scope=tenant_id,
        )
        for item in _parse_targets(response):
            if item.tenant_id == target_tenant_id:
                return item
        raise ServiceUnavailableError("关系数据源契约响应缺少目标租户条目")

    async def revoke(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> None:
        """回收单个目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。

        Raises:
            ServiceUnavailableError: 契约不可达或响应非法（10007）。
        """
        await self._call(
            "DELETE",
            query=ConcurrentStableDict(
                {
                    "owner_tenant_id": str(tenant_id),
                    "user_id": str(user_id),
                    "target_tenant_id": str(target_tenant_id),
                }
            ),
            tenant_scope=tenant_id,
        )

    async def revoke_all(self, *, tenant_id: int, user_id: int) -> None:
        """回收该用户全部目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。

        Raises:
            ServiceUnavailableError: 契约不可达或响应非法（10007）。
        """
        await self._call(
            "DELETE",
            query=ConcurrentStableDict({"owner_tenant_id": str(tenant_id), "user_id": str(user_id)}),
            tenant_scope=tenant_id,
        )

    async def _call(
        self,
        method: str,
        *,
        query: ConcurrentStableDict[str, str] | None = None,
        json_body: ConcurrentStableDict[str, object] | None = None,
        tenant_scope: int,
    ) -> ServiceResponse:
        """发起内部端点调用（非 2xx 归一为服务不可用）。

        Args:
            method: HTTP 方法。
            query: 查询参数。
            json_body: 请求体。
            tenant_scope: 调用方租户主键（随服务 JWT 传递）。

        Returns:
            ServiceResponse: 调用响应（2xx）。

        Raises:
            ServiceUnavailableError: 非 2xx（10007）。
        """
        request = ServiceRequest(
            service=self._service,
            method=method,
            path=TENANT_MEMBERSHIP_INTERNAL_PATH,
            query=query,
            json_body=json_body,
            tenant_id=str(tenant_scope),
        )
        response = await self._client.call(request)
        if not 200 <= response.status_code < 300:
            _LOGGER.warning("tenant_membership_contract_failed", method=method, status=response.status_code)
            raise ServiceUnavailableError(f"关系数据源契约调用失败（{response.status_code}）")
        return response


def _parse_targets(response: ServiceResponse) -> ConcurrentStableList[TenantMembershipTarget]:
    """解析内部端点响应为有效目标集合。

    Args:
        response: 调用响应。

    Returns:
        ConcurrentStableList[TenantMembershipTarget]: 目标集合。

    Raises:
        ServiceUnavailableError: 响应体非法（10007）。
    """
    raw = response.payload()
    body = cast("Mapping[str, object]", raw) if isinstance(raw, Mapping) else None
    data: object = body.get("data") if body is not None else None
    if not isinstance(data, Mapping):
        raise ServiceUnavailableError("关系数据源契约响应缺少 data")
    targets: object = cast("Mapping[str, object]", data).get("targets")
    if not isinstance(targets, list):
        raise ServiceUnavailableError("关系数据源契约响应缺少 targets")
    items: ConcurrentStableList[TenantMembershipTarget] = ConcurrentStableList()
    for item in cast("list[object]", targets):
        if not isinstance(item, Mapping):
            raise ServiceUnavailableError("关系数据源契约目标条目非法")
        try:
            items.add(TenantMembershipTarget.model_validate(dict(cast("Mapping[str, object]", item))))
        except Exception as exc:  # 契约漂移：条目字段非法
            raise ServiceUnavailableError(f"关系数据源契约目标条目非法：{exc!r}") from exc
    return items


def register_remote_tenant_membership_store() -> None:
    """登记 `remote` 关系数据源实现（模块导入即调用；装配点见 `application.py`）。"""

    def _factory(
        *,
        settings: Settings,
        registry: EngineRegistry,
        session_factory: SessionFactory | None,
        service_client: BaseServiceClient | None,
    ) -> RemoteTenantMembershipStore:
        """构造远端关系数据源（服务客户端经应用装配注入）。"""
        del settings, registry, session_factory  # 远端实现无需本地库与会话
        if service_client is None:
            raise ConfigError("远端关系数据源缺少 service_client 装配")
        return RemoteTenantMembershipStore(client=service_client)

    register_tenant_membership_store(REMOTE_TENANT_MEMBERSHIP_STORE, _factory)


register_remote_tenant_membership_store()
