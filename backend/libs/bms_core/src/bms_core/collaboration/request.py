"""由能力取用结果构造服务间调用请求（消费方不自拼服务键 / 路径）。

**落点说明**：构造逻辑放在本包而非 `servicecall/base.py`——本包的过渡拓扑实现要引用 `servicecall` 的
基址模板（`DEFAULT_BASE_URL_TEMPLATE`），若反向在 `servicecall` 里引用本包即形成导入环；此处保持
单向依赖（`collaboration → servicecall`）。

**集合口径**：入参一律基座不可变集合（`ConcurrentStableFrozenDict`），与 `ServiceRequest` 字段同口径，
避免消费方在契约边界上再转一次裸字典。

失败语义：`codes` 类能力无访问面 → 抛 `ParamError`（10001），不得发起调用；路径参数缺失 / 多余同样即拒。
"""

from dataclasses import replace

from bms_core.collaboration.base import CapabilityEndpoint, CapabilityMode
from bms_core.collaboration.grant import granted_scopes
from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ParamError
from bms_core.servicecall.base import ServiceCallPolicy, ServiceRequest
from bms_core.services.module_registry import render_capability_path

__all__ = ["build_capability_request"]


def build_capability_request(
    endpoint: CapabilityEndpoint,
    *,
    method: str,
    params: ConcurrentStableFrozenDict[str, object] | None = None,
    query: ConcurrentStableFrozenDict[str, str] | None = None,
    headers: ConcurrentStableFrozenDict[str, str] | None = None,
    json_body: ConcurrentStableFrozenDict[str, object] | None = None,
    tenant_id: str | None = None,
    policy: ServiceCallPolicy | None = None,
) -> ServiceRequest:
    """按取用结果构造服务间调用请求（目标服务取 `target.service_key`，路径按模板填充）。

    Args:
        endpoint: 能力取用结果（`resolve_capability` 返回值）。
        method: HTTP 方法（GET / POST / ...）。
        params: 访问面路径参数（键须与模板占位名一致）。
        query: 查询参数（可选）。
        json_body: JSON 请求体（可选）。
        tenant_id: 调用方租户主键（可选；随服务 JWT 的 `tenant_id` claim 传递）。
        policy: 调用韧性策略（None 时取缺省策略，并按当前服务**有效授权**自动填 `scopes`）。

    Returns:
        ServiceRequest: 服务间调用请求（`service` 为承载服务标识，`base_url` 为第二段解析出的单元地址）。

    Raises:
        ParamError: 能力无访问面（`codes` 类）或路径参数缺失 / 多余（10001）。
    """
    if endpoint.path is None:
        raise ParamError(f"能力无访问面（kind={endpoint.kind}）：{endpoint.name}（不得据此发起调用）")
    path = render_capability_path(endpoint.path, subject=endpoint.name, **dict(params or {}))
    request = ServiceRequest(
        service=endpoint.target.service_key,
        method=method,
        path=path,
        base_url=endpoint.target.base_url,
        local=endpoint.target.mode == CapabilityMode.LOCAL,
        query=query,
        headers=headers,
        json_body=json_body,
        tenant_id=tenant_id,
    )
    if policy is None:
        # 出站 scope 由授权派生（07B `02_04`）：消费方零感知，杜绝漏填；显式传入的 policy 原样尊重
        policy = ServiceCallPolicy(scopes=granted_scopes(get_settings().app.service))
    return replace(request, policy=policy)
