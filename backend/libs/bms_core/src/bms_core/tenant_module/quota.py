"""租户配额内部契约客户端（跨服务消费方共用；任务 `04_01`）。

- 契约：tenant 服务 `POST /api/v1/tenant/internal/quotas/{consume,release}`。
- **消费先行、失败释放**：无跨服务事务时的折中口径（调用方成功后不回滚；失败调用 `release`）。
- 无配额行 / 无租户上下文：空操作（不限制）。
"""

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ServiceUnavailableError, TenantQuotaExceededError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest, ServiceResponse

__all__ = ["TenantQuotaClient"]

_LOGGER = get_logger("bms.tenant_quota")

_TENANT_SERVICE = "tenant"
_SCOPES: tuple[str, ...] = ("tenant_quota",)


class TenantQuotaClient(BaseFrameworkObject):
    """租户配额占用 / 释放客户端。"""

    def __init__(self, client: BaseServiceClient, *, tenant_id: str | None, tenant_code: str | None) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端。
            tenant_id: 当前租户主键（无租户上下为空 → 空操作）。
            tenant_code: 当前租户编码（服务 JWT 租户位）。
        """
        self._client = client
        self._tenant_id = tenant_id
        self._tenant_code = tenant_code

    async def consume(self, quota_key: str, amount: int, *, ref: str = "") -> None:
        """占用配额（超限 82005；下游不可用 10007）。

        Args:
            quota_key: 配额维度（`user_count` / `storage_bytes` / `open_calls`）。
            amount: 占用数量（正数）。
            ref: 业务引用（日志用，可选）。

        Raises:
            TenantQuotaExceededError: 配额超限（82005 / 409）。
            ServiceUnavailableError: 下游不可达 / 响应非法（10007 / 503）。
        """
        await self._post("consume", quota_key, amount, ref)

    async def release(self, quota_key: str, amount: int) -> None:
        """释放配额（失败仅告警，不阻断业务回滚路径）。

        Args:
            quota_key: 配额维度。
            amount: 释放数量（正数）。
        """
        try:
            await self._post("release", quota_key, amount, "")
        except Exception:
            return

    async def _post(self, action: str, quota_key: str, amount: int, ref: str) -> None:
        """发起内部契约调用。

        Args:
            action: `consume` / `release`。
            quota_key: 配额维度。
            amount: 数量。
            ref: 业务引用。

        Raises:
            TenantQuotaExceededError: 配额超限（82005 / 409）。
            ServiceUnavailableError: 下游不可达 / 响应非法（10007 / 503）。
        """
        if not self._tenant_id or not self._tenant_id.isdigit():
            return
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"tenant_id": int(self._tenant_id), "quota_key": quota_key, "amount": amount}
        )
        if ref:
            body.set("ref", ref)
        response = await self._client.call(
            ServiceRequest(
                service=_TENANT_SERVICE,
                method="POST",
                path=f"/api/v1/tenant/internal/quotas/{action}",
                tenant_id=self._tenant_code,
                json_body=body,
                policy=ServiceCallPolicy(scopes=_SCOPES),
            )
        )
        try:
            _raise_if_failed(response)
        except ServiceUnavailableError as exc:  # 配额服务不可用：fail-open + 告警（不阻断业务写入）
            _LOGGER.warning("tenant_quota_unavailable", quota_key=quota_key, action=action, error=type(exc).__name__)


def _raise_if_failed(response: ServiceResponse) -> None:
    """解析响应：82005 转配额超限；其它非 2xx / 非法响应转服务不可用。

    Args:
        response: 服务间调用响应。

    Raises:
        TenantQuotaExceededError: 配额超限（82005 / 409）。
        ServiceUnavailableError: 非 2xx / 响应非法（10007 / 503）。
    """
    payload = response.payload()
    body = cast("dict[str, object]", payload) if isinstance(payload, dict) else None
    if body is not None and body.get("code") == 82005:
        data = body.get("data")
        raise TenantQuotaExceededError(
            "租户配额超限", data=cast("dict[str, object]", data) if isinstance(data, dict) else None
        )
    if response.status_code != 200:
        raise ServiceUnavailableError(f"租户配额服务不可用（HTTP {response.status_code}）")
    if body is None or body.get("code") != 0:
        raise ServiceUnavailableError("租户配额服务返回非法响应")
