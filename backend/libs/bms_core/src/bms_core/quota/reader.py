"""配额投影只读装载（07D `02_03`）：经服务间契约实时取产品投影，失败即降级 `unavailable`。

**不做的事**：不落库、不缓存、不重试、不双写——平台侧只做「取一次、看一眼、用完即丢」；
产品端点是配额的单一事实源，平台侧不维护第二份值（架构 41 §5.3）。

**失败口径**：超时 / 非 2xx / 结构非法 / 单维度无用量值 → 该维度 `unavailable`（整源失败则整源
不可用），**不返回旧值、不用 0 冒充**。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.datasource.registry import DataSourceRecord
from bms_core.quota.schemas import (
    DEFAULT_QUOTA_CALL_TIMEOUT,
    QuotaProjectionItem,
    QuotaProjectionState,
    judge_quota_state,
)
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest, ServiceResponse

__all__ = ["QuotaProjectionReader"]

_LOGGER = get_logger("bms.quota")


class QuotaProjectionReader(BaseFrameworkObject):
    """配额投影只读取数器（按产品数据源声明逐源实时取）。"""

    def __init__(
        self,
        client_provider: Callable[[], BaseServiceClient],
        *,
        timeout: float = DEFAULT_QUOTA_CALL_TIMEOUT,
    ) -> None:
        """初始化。

        Args:
            client_provider: 服务间调用客户端提供者（惰性取，避免捕获装配期旧实例）。
            timeout: 单次取数超时（秒）；不重试。
        """
        self._client_provider = client_provider
        self._timeout = timeout

    async def read(
        self,
        records: Iterable[DataSourceRecord],
        *,
        tenant_id: int,
    ) -> ConcurrentStableList[QuotaProjectionItem]:
        """读取全部配额投影（逐源；单源失败不影响其它源）。

        Args:
            records: `kind = quota` 的数据源声明。
            tenant_id: 租户主键（取数查询参数）。

        Returns:
            ConcurrentStableList[QuotaProjectionItem]: 投影条目（按声明顺序）。
        """
        items: ConcurrentStableList[QuotaProjectionItem] = ConcurrentStableList()
        for record in records:
            items.update(await self._read_one(record, tenant_id=tenant_id))
        return items

    async def _read_one(
        self,
        record: DataSourceRecord,
        *,
        tenant_id: int,
    ) -> ConcurrentStableList[QuotaProjectionItem]:
        """读取单个产品的投影（失败即整源 `unavailable`）。

        Args:
            record: 数据源声明（`kind = quota`）。
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableList[QuotaProjectionItem]: 该源的投影条目（维度取自声明）。
        """
        request = ServiceRequest(
            service=str(record.data_source).split(".", 1)[0],
            method="GET",
            path=str(record.path),
            query=ConcurrentStableFrozenDict({"tenant_id": str(tenant_id)}),
            tenant_id=str(tenant_id),
            policy=ServiceCallPolicy(timeout=self._timeout, max_retries=0),
        )
        try:
            response = await self._client_provider().call(request)
        except Exception as exc:  # 下游不可达 / 超时 / 熔断：降级不可用，不抛出
            _LOGGER.warning(
                "quota_projection_unavailable",
                data_source_key=record.data_source_key,
                error=type(exc).__name__,
            )
            return _unavailable(record, reason="call_failed")
        if not 200 <= response.status_code < 300:
            _LOGGER.warning(
                "quota_projection_unavailable",
                data_source_key=record.data_source_key,
                status=response.status_code,
            )
            return _unavailable(record, reason="bad_status")
        provided = _provided_items(response, record)
        if provided is None:
            _LOGGER.warning("quota_projection_invalid", data_source_key=record.data_source_key)
            return _unavailable(record, reason="invalid_payload")
        return _project(record, provided)


def _provided_items(
    response: ServiceResponse,
    record: DataSourceRecord,
) -> ConcurrentStableDict[str, ConcurrentStableDict[str, object]] | None:
    """解析产品返回（`{items: [{quota_key, usage, ...}]}` → `quota_key → 条目`）。

    Args:
        response: 调用响应。
        record: 数据源声明（取声明维度做白名单）。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableDict[str, object]] | None: 命中项；结构非法返回 `None`。
    """
    payload = response.payload()
    if not isinstance(payload, Mapping):
        return None
    raw_items = cast("Mapping[str, object]", payload).get("items")
    if not isinstance(raw_items, list):
        return None
    declared = {str(dimension) for dimension in record.quota_dimensions}
    result: ConcurrentStableDict[str, ConcurrentStableDict[str, object]] = ConcurrentStableDict()
    for raw in cast("list[object]", raw_items):
        if not isinstance(raw, Mapping):
            return None
        item = cast("Mapping[str, object]", raw)
        key = str(item.get("quota_key") or "")
        if key not in declared:
            _LOGGER.warning(
                "quota_projection_unknown_dimension",
                data_source_key=record.data_source_key,
                quota_key=key,
            )
            continue
        entry: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        fields = (
            "usage",
            "limit",
            "soft_limit",
            "hard_limit",
            "updated_at",
            "module_key",
            "resource_key",
            "resource_type",
        )
        for name in fields:
            entry.set(name, item.get(name))
        result.set(key, entry)
    return result


def _project(
    record: DataSourceRecord,
    provided: ConcurrentStableDict[str, ConcurrentStableDict[str, object]],
) -> ConcurrentStableList[QuotaProjectionItem]:
    """把产品返回值与声明合成投影条目（缺失维度补 `default`）。

    Args:
        record: 数据源声明。
        provided: 产品返回值（`quota_key → 条目`）。

    Returns:
        ConcurrentStableList[QuotaProjectionItem]: 投影条目（严格按声明维度顺序）。
    """
    items: ConcurrentStableList[QuotaProjectionItem] = ConcurrentStableList()
    for dimension in record.quota_dimensions:
        entry = provided.get(dimension)
        usage = _as_int(entry.get("usage")) if entry is not None else None
        hard_limit = _as_int(entry.get("hard_limit")) if entry is not None else None
        if hard_limit is None:
            hard_limit = record.quota_hard_limit
        soft_limit = _as_int(entry.get("soft_limit")) if entry is not None else None
        if soft_limit is None:
            soft_limit = record.quota_soft_limit
        limit = _as_int(entry.get("limit")) if entry is not None else None
        state = judge_quota_state(provided=entry is not None, usage=usage, hard_limit=hard_limit)
        items.add(
            QuotaProjectionItem(
                quota_key=dimension,
                product_key=str(record.product_key or ""),
                module_key=_module_of(record),
                resource_type=_as_str(entry.get("resource_type")) if entry is not None else None,
                resource_key=_as_str(entry.get("resource_key")) if entry is not None else None,
                limit=limit,
                usage=usage,
                unit=str(record.quota_unit or ""),
                period=str(record.quota_period or ""),
                soft_limit=soft_limit,
                hard_limit=hard_limit,
                updated_at=_as_datetime(entry.get("updated_at")) if entry is not None else None,
                source=f"{record.product_key}.{record.data_source_key}",
                state=state,
            )
        )
    return items


def _unavailable(record: DataSourceRecord, *, reason: str) -> ConcurrentStableList[QuotaProjectionItem]:
    """整源不可用（全部声明维度 `unavailable`）。

    Args:
        record: 数据源声明。
        reason: 失败原因（日志已记录，此处仅占位保持签名一致）。

    Returns:
        ConcurrentStableList[QuotaProjectionItem]: 不可用条目。
    """
    del reason
    items: ConcurrentStableList[QuotaProjectionItem] = ConcurrentStableList()
    for dimension in record.quota_dimensions:
        items.add(
            QuotaProjectionItem(
                quota_key=dimension,
                product_key=str(record.product_key or ""),
                module_key=_module_of(record),
                limit=None,
                usage=None,
                unit=str(record.quota_unit or ""),
                period=str(record.quota_period or ""),
                soft_limit=record.quota_soft_limit,
                hard_limit=record.quota_hard_limit,
                updated_at=None,
                source=f"{record.product_key}.{record.data_source_key}",
                state=QuotaProjectionState.UNAVAILABLE,
            )
        )
    return items


def _module_of(record: DataSourceRecord) -> str:
    """取投影条目的模块键（数据源实现标识首段即服务/模块键）。

    Args:
        record: 数据源声明。

    Returns:
        str: 模块键（`data_source` 首段）。
    """
    return str(record.data_source).split(".", 1)[0]


def _as_int(value: object) -> int | None:
    """宽松取整数（布尔 / 非数值 / 缺失均为 `None`）。

    Args:
        value: 原始值。

    Returns:
        int | None: 整数值。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _as_datetime(value: object) -> datetime | None:
    """取时间（缺省 / 非法均为 `None`）。

    Args:
        value: 原始值（`datetime` 或 ISO 8601 字符串）。

    Returns:
        datetime | None: 时间值。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_str(value: object) -> str | None:
    """取字符串（缺失 / 空串为 `None`）。

    Args:
        value: 原始值。

    Returns:
        str | None: 字符串值。
    """
    if value is None:
        return None
    text = str(value)
    return text or None
