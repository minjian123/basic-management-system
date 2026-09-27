"""系统参数跨服务读出口（`http` 实现）：经 `service_client` 读 `platform` 服务内部端点。

- **权威侧是 `platform` 服务**（其租户库存 `sys_config`），其余服务不直连其库、统一经服务间契约读取。
- **契约**：`POST /api/v1/platform/internal/configs/resolve`（服务 JWT，`X-Tenant-Id` 透传租户）。
- **降级（不抛业务错）**：不可达 / 超时 / 熔断 / 非 2xx / 响应体非法 → 返回空结果（调用方回落代码默认表）。
"""

from collections.abc import Mapping, Sequence
from typing import cast

from bms_core.config.base import BaseConfigSource
from bms_core.core.context import get_current_tenant
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION
from bms_core.edge.headers import TENANT_ID_HEADER
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = ["CONFIG_RESOLVE_PATH", "CONFIG_SERVICE_KEY", "HttpConfigSource"]

CONFIG_SERVICE_KEY = "platform"
"""系统参数数据权威服务标识（`sys_config` 所有者）。"""

CONFIG_RESOLVE_PATH = "/api/v1/platform/internal/configs/resolve"
"""内部批量取参数契约路径。"""

_LOGGER = get_logger("bms")


class HttpConfigSource(BaseConfigSource):
    """跨服务系统参数取数（经 `service_client` 读 `platform` 服务；不可达返回空结果）。"""

    plugin_name: str = "http"
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def get_many(self, keys: Sequence[str]) -> Mapping[str, str]:
        """批量取参数值（契约调用 + 降级）。

        Args:
            keys: 参数键序列。

        Returns:
            Mapping[str, str]: 命中键 → 值；调用失败返回空映射（降级）。
        """
        unique = [key for key in dict.fromkeys(keys) if key]
        if not unique:
            return {}
        headers: dict[str, str] = {}
        tenant = get_current_tenant()
        if tenant:
            headers[TENANT_ID_HEADER] = tenant
        request = ServiceRequest(
            service=CONFIG_SERVICE_KEY,
            method="POST",
            path=CONFIG_RESOLVE_PATH,
            headers=headers,
            json_body={"keys": unique},
        )
        try:
            response = await self._client.call(request)
        except ServiceUnavailableError:
            _LOGGER.warning("系统参数跨服务取数降级", keys=len(unique))
            return {}
        if not 200 <= response.status_code < 300:
            return {}
        payload = response.payload()
        if not isinstance(payload, Mapping):
            return {}
        data = cast("Mapping[str, object]", payload).get("data")
        if not isinstance(data, Mapping):
            return {}
        values = cast("Mapping[str, object]", data).get("values")
        if not isinstance(values, Mapping):
            return {}
        allowed = set(unique)
        return {
            str(key): str(value) for key, value in cast("Mapping[str, object]", values).items() if str(key) in allowed
        }
