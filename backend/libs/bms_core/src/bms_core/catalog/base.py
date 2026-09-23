"""服务目录快照契约客户端（06_03）：`GET /api/v1/modules/snapshot` → `list[ModuleRecord]`。

- 消费方：全部服务的**启动接库校验**（`application.py::_validate_service_catalog`）；
- 提供方：`platform` 服务（服务目录单一权威，`sys_module` 所有者）；
- 失败：不可达 / 响应非法 → `ServiceUnavailableError`（调用方按降级口径处置，见详细设计 §5）。
"""

from collections.abc import Mapping, Sequence
from dataclasses import fields
from typing import cast

from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.services.module_registry import ModuleRecord

__all__ = ["CATALOG_SERVICE_KEY", "CATALOG_SNAPSHOT_PATH", "fetch_catalog_snapshot"]

CATALOG_SERVICE_KEY = "platform"
"""服务目录提供方服务标识。"""

CATALOG_SNAPSHOT_PATH = "/api/v1/modules/snapshot"
"""服务目录快照只读契约路径。"""

_MODULE_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(ModuleRecord))


async def fetch_catalog_snapshot(
    client: BaseServiceClient,
    *,
    service: str = CATALOG_SERVICE_KEY,
) -> list[ModuleRecord]:
    """取服务目录快照（全量清单，不分页）。

    Args:
        client: 服务间调用客户端（`service_client` 能力域）。
        service: 提供方服务标识。

    Returns:
        list[ModuleRecord]: 服务目录清单。

    Raises:
        ServiceUnavailableError: 契约不可达、非 2xx 或响应体非法。
    """
    request = ServiceRequest(service=service, method="GET", path=CATALOG_SNAPSHOT_PATH)
    response = await client.call(request)
    if not 200 <= response.status_code < 300:
        raise ServiceUnavailableError(f"服务目录快照契约调用失败（{response.status_code}）")
    return [_to_record(row) for row in _payload_rows(response)]


def _payload_rows(response: ServiceResponse) -> Sequence[Mapping[str, object]]:
    """取统一响应包裹的 `data` 数组。

    Args:
        response: 契约响应。

    Returns:
        Sequence[Mapping[str, object]]: 清单行序列。

    Raises:
        ServiceUnavailableError: 响应体非法。
    """
    raw = response.payload()
    body = cast("Mapping[str, object]", raw) if isinstance(raw, Mapping) else None
    data: object = body.get("data") if body is not None else None
    if not isinstance(data, list):
        raise ServiceUnavailableError("服务目录快照响应缺少 data 数组")
    rows: list[Mapping[str, object]] = []
    for item in cast("list[object]", data):
        if not isinstance(item, Mapping):
            raise ServiceUnavailableError("服务目录快照响应行须为对象")
        rows.append(cast("Mapping[str, object]", item))
    return rows


def _to_record(row: Mapping[str, object]) -> ModuleRecord:
    """清单行 → `ModuleRecord`（仅取登记字段）。

    Args:
        row: 清单行。

    Returns:
        ModuleRecord: 登记记录。

    Raises:
        ServiceUnavailableError: 必填字段缺失。
    """
    try:
        return ModuleRecord(**{name: row[name] for name in _MODULE_FIELDS})  # type: ignore[arg-type]
    except KeyError as exc:
        raise ServiceUnavailableError(f"服务目录快照响应缺字段：{exc}") from exc
