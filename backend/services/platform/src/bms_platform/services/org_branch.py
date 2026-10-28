"""组织域事务分支的公共换算（07B `03_01`）：分支三要素与内部写请求。

用户保存编排与角色保存编排共用同一套换算，避免两处各写一份导致口径漂移：

- **分支三要素**（分支标识 / 承载服务 / 库键）：全部取自已解析的能力声明；库键在拓扑未给值时
  回退按承载服务键派生（与收编前逐字一致）；
- **内部写请求**：方法 + 路径模板 + 承载服务均取自声明，幂等键经请求头透传。

本模块不写产品标识与对端路径；能力名由调用方传入（集中常量见 `bms_platform.capabilities`）。
"""

from __future__ import annotations

from bms_core.collaboration.base import CapabilityEndpoint
from bms_core.collaboration.request import build_capability_request
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.db.keys import TENANT_DB_KEY_PREFIX, build_tenant_db_key
from bms_core.servicecall.base import ServiceRequest

__all__ = ["branch_op", "branch_target", "internal_write_request"]


def branch_target(
    endpoints: ConcurrentStableList[CapabilityEndpoint],
    *,
    platform_db_key: str,
) -> tuple[str, str, str]:
    """取组织域分支三要素（分支标识 / 承载服务 / 租户库键）。

    同一保存请求的多段（如岗位 + 部门）须落在**同一分支**：声明若漂移（分支标识或承载服务不唯一）
    即 fail-closed，避免把一条事务拆成两个参与者、或在同一事务内撞标识。

    Args:
        endpoints: 本次参与的组织域能力取用结果（非空）。
        platform_db_key: 平台租户库键（库键回退派生的基准）。

    Returns:
        tuple[str, str, str]: （分支标识, 承载服务键, 租户库键）。

    Raises:
        CatalogError: 声明不一致或缺少分支标识。
    """
    branch_ids = sorted({endpoint.branch_id or "" for endpoint in endpoints})
    service_keys = sorted({endpoint.target.service_key for endpoint in endpoints})
    if len(branch_ids) != 1 or len(service_keys) != 1:
        raise CatalogError(
            "组织域能力声明不一致（同一保存请求的各段须同一分支与承载服务）："
            f"branch_id={branch_ids}，service_key={service_keys}"
        )
    branch_id = branch_ids[0]
    if not branch_id:
        raise CatalogError("组织域能力声明缺少 branch_id（写 / 强一致能力须声明事务分支标识）")
    return branch_id, service_keys[0], _db_key(endpoints[0], platform_db_key=platform_db_key)


def branch_op(endpoint: CapabilityEndpoint) -> str:
    """取能力声明的分支动作名（缺失即声明不全，fail-closed）。

    Args:
        endpoint: 能力取用结果。

    Returns:
        str: 分支动作名。

    Raises:
        CatalogError: 声明缺少 `branch_op`。
    """
    if not endpoint.branch_op:
        raise CatalogError(f"能力声明缺少 branch_op：{endpoint.name}（写 / 强一致能力须声明分支动作名）")
    return endpoint.branch_op


def internal_write_request(
    endpoint: CapabilityEndpoint,
    *,
    params: ConcurrentStableFrozenDict[str, object],
    body: ConcurrentStableDict[str, object],
    idempotency_key: str | None,
    tenant_id: str | None,
) -> ServiceRequest:
    """构造组织域内部写通道请求（`provider=null` 顺序提交路径）。

    Args:
        endpoint: 能力取用结果（承载服务与路径模板均取自声明）。
        params: 路径模板参数（如 `{user_id}` / `{role_id}`）。
        body: 请求体。
        idempotency_key: 业务幂等键（可空；非空时经 `Idempotency-Key` 头透传）。
        tenant_id: 调用方租户主键（可空）。

    Returns:
        ServiceRequest: 内部写请求（方法固定 PUT，与提供方内部写通道一致）。
    """
    headers: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if idempotency_key:
        headers.set("Idempotency-Key", idempotency_key)
    return build_capability_request(
        endpoint,
        method="PUT",
        params=params,
        json_body=ConcurrentStableFrozenDict(body),
        # 与收编前一致：即使无幂等键也传空头集合（不传 None），调用侧语义与断言口径不变
        headers=ConcurrentStableFrozenDict(headers),
        tenant_id=tenant_id,
    )


def _db_key(endpoint: CapabilityEndpoint, *, platform_db_key: str) -> str:
    """组织域租户库键：拓扑解析有值取之，空集回退按承载服务键派生（与收编前逐字一致）。

    Args:
        endpoint: 能力取用结果。
        platform_db_key: 平台租户库键。

    Returns:
        str: 组织域租户库键。
    """
    if endpoint.target.db_keys:
        return endpoint.target.db_keys[0]
    return build_tenant_db_key(platform_db_key[len(TENANT_DB_KEY_PREFIX) :], service=endpoint.target.service_key)
