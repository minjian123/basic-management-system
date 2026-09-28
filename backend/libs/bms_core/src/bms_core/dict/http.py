"""字典跨服务读出口（06_02 承接 06_03 遗留 3）：经 `service_client` 读 `platform` 服务的字典接口。

- **提供者**：`dict_source:http` / `dict_translator:http`（`[dict_source].provider = "http"`）——非
  `platform` 服务使用：字典数据的**权威侧是 `platform` 服务**（其租户库存字典六表），其余服务不直连
  字典表、也不复制缓存实现，统一经公开契约读取（服务间只经 `/api/v1` 公开面，东西向直连不经网关）。
- **契约**（复用平台服务**既有**接口，不新增端点）：
  - 单类型取数：`GET /api/v1/dicts/{dict_type}`（`version` / `keyword` / `parent_id` / `values` / `limit`）；
  - 批量合并：`POST /api/v1/dicts/batch`（`types` / `version` / `locale`）；
  - 语言：`Accept-Language` 头（平台端点按该头解析 locale）；租户：`X-Tenant-Id` 头（租户上下文透传，
    否则平台侧按子域名 / 令牌解析）。
- **失败语义（降级，不抛业务错）**：不可达 / 超时 / 重试耗尽 / 熔断断开 / 非 2xx / 响应体非法 →
  取数返回**空结果**（`items=()`、`version=0`）、翻译**回退原值**；与 `null` 实现同语义，调用方无需
  区分（`/readyz` 的依赖状态仍由 `service_client` 的熔断 / 降级策略反映）。
- **翻译实现**：按「取子集 → 本地映射」分批（`values` 子集，避免超大字典全量拉取）；可选复用已装配的
  字典缓存域（`dict_cache_region`）缓存 value → label 子集映射。
- **不含**：字典 / 查询方案的**真实数据、写路径与缓存实现迁出**（归阶段八）——本模块只落跨服务读出口。
"""

from collections.abc import Mapping, Sequence
from typing import cast
from urllib.parse import quote

from bms_core.core.context import get_current_tenant
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION
from bms_core.dict.base import (
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictCacheRegion,
    DictItem,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
)
from bms_core.dict.sql import current_dict_locale
from bms_core.edge.headers import TENANT_ID_HEADER
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = [
    "ACCEPT_LANGUAGE_HEADER",
    "DICT_BATCH_PATH",
    "DICT_SERVICE_KEY",
    "HTTP_DICT_PROVIDER",
    "TRANSLATE_VALUES_CHUNK",
    "HttpDictSource",
    "HttpDictTranslator",
    "dict_type_path",
]

HTTP_DICT_PROVIDER = "http"
"""跨服务读出口提供者名（`[dict_source].provider` / `[dict_translator].provider`）。"""

DICT_SERVICE_KEY = "platform"
"""字典数据权威服务标识（`sys_dict_*` 所有者）。"""

DICT_TYPE_PATH = "/api/v1/dicts/{dict_type}"
"""单类型取数契约路径模板。"""

DICT_BATCH_PATH = "/api/v1/dicts/batch"
"""批量合并取数契约路径。"""

ACCEPT_LANGUAGE_HEADER = "Accept-Language"
"""语言请求头（平台端点据此解析 locale）。"""

TRANSLATE_VALUES_CHUNK = 200
"""翻译按值子集的单批上限（避免一次请求过大）。"""


def dict_type_path(dict_type: str) -> str:
    """拼单类型取数契约路径（URL 编码字典类型码）。

    Args:
        dict_type: 字典类型码。

    Returns:
        str: 契约路径。
    """
    return DICT_TYPE_PATH.format(dict_type=quote(dict_type, safe=""))


def _headers(locale: str) -> dict[str, str]:
    """构造调用头（语言 + 租户上下文透传）。

    Args:
        locale: 语言标识。

    Returns:
        dict[str, str]: 请求头。
    """
    headers = {ACCEPT_LANGUAGE_HEADER: locale}
    tenant = get_current_tenant()
    if tenant:
        headers[TENANT_ID_HEADER] = tenant
    return headers


def _current_locale() -> str:
    """取当前请求语言（字典链路上下文；缺省 `zh-CN`）。

    Returns:
        str: 语言标识。
    """
    return current_dict_locale.get() or DEFAULT_LOCALE


async def _fetch_type(
    client: BaseServiceClient,
    *,
    dict_type: str,
    locale: str,
    version: int | None = None,
    keyword: str | None = None,
    parent_id: str | None = None,
    values: Sequence[str] | None = None,
    limit: int | None = None,
) -> DictTypeResult | None:
    """取单类型字典（契约调用 + 降级；失败返回 None 由调用方处置）。

    Args:
        client: 服务间调用客户端。
        dict_type: 字典类型码。
        locale: 语言标识（经 `Accept-Language` 透传）。
        version: 客户端本地版本号（一致时平台侧返回 `items=None`）。
        keyword: 关键字。
        parent_id: 级联父值。
        values: 指定 value 子集。
        limit: 条数上限。

    Returns:
        DictTypeResult | None: 取数结果；调用失败 / 响应非法返回 None。
    """
    query: dict[str, str] = {}
    if version is not None:
        query["version"] = str(version)
    if keyword:
        query["keyword"] = keyword
    if parent_id is not None:
        query["parent_id"] = parent_id
    if values is not None:
        query["values"] = ",".join(values)
    if limit is not None:
        query["limit"] = str(limit)
    request = ServiceRequest(
        service=DICT_SERVICE_KEY,
        method="GET",
        path=dict_type_path(dict_type),
        query=query,
        headers=_headers(locale),
    )
    data = await _call(client, request)
    return None if data is None else _to_type_result(data)


async def _call(client: BaseServiceClient, request: ServiceRequest) -> Mapping[str, object] | None:
    """发起契约调用并取统一响应的 `data` 对象（不可达 / 非 2xx / 非法响应 → None）。

    Args:
        client: 服务间调用客户端。
        request: 调用请求。

    Returns:
        Mapping[str, object] | None: 响应 `data` 对象；降级返回 None。
    """
    try:
        response = await client.call(request)
    except ServiceUnavailableError:
        return None
    if not 200 <= response.status_code < 300:
        return None
    payload = response.payload()
    if not isinstance(payload, Mapping):
        return None
    data = cast("Mapping[str, object]", payload).get("data")
    return cast("Mapping[str, object]", data) if isinstance(data, Mapping) else None


def _to_type_result(data: Mapping[str, object]) -> DictTypeResult:
    """响应 `data` → `DictTypeResult`（缺失字段按契约缺省）。

    Args:
        data: 单类型取数响应 `data`。

    Returns:
        DictTypeResult: 取数结果。
    """
    raw_items = data.get("items")
    items: tuple[DictItem, ...] | None = None
    if isinstance(raw_items, list):
        items = tuple(
            _to_item(cast("Mapping[str, object]", item))
            for item in cast("list[object]", raw_items)
            if isinstance(item, Mapping)
        )
    return DictTypeResult(
        version=_as_int(data.get("version")),
        items=items,
        has_more=bool(data.get("has_more", False)),
        total=_as_int(data.get("total")),
    )


def _to_item(row: Mapping[str, object]) -> DictItem:
    """响应行 → `DictItem`。

    Args:
        row: 条目行。

    Returns:
        DictItem: 条目。
    """
    parent = row.get("parent_id")
    color = row.get("color")
    return DictItem(
        value=str(row.get("value", "")),
        label=str(row.get("label", "")),
        code=str(row.get("code", "")),
        parent_id=None if parent is None else str(parent),
        sort=_as_int(row.get("sort")),
        status=str(row.get("status", "enabled")),
        color=None if color is None else str(color),
    )


def _as_int(value: object) -> int:
    """宽松取整数（非法回落 0）。

    Args:
        value: 原始值。

    Returns:
        int: 整数。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return 0


def _empty_result() -> DictTypeResult:
    """降级空结果（`items=()`，与 `null` 实现「确无数据」同形）。

    Returns:
        DictTypeResult: 空取数结果。
    """
    return DictTypeResult(version=0, items=(), has_more=False, total=0)


class HttpDictSource(BaseDictSource):
    """跨服务字典取数（经 `service_client` 读 `platform` 服务；不可达返回空结果）。"""

    plugin_name: str = HTTP_DICT_PROVIDER
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按类型取字典（版本比对 / 关键字 / 级联 / 按值子集 / 上限）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果；平台侧不可达时返回空结果（降级）。
        """
        result = await _fetch_type(
            self._client,
            dict_type=query.dict_type,
            locale=_current_locale(),
            version=query.version,
            keyword=query.keyword,
            parent_id=query.parent_id,
            values=query.values,
            limit=query.limit,
        )
        return _empty_result() if result is None else result

    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        """批量合并取字典（一次请求多类型）。

        Args:
            query: 批量取数参数对象。

        Returns:
            DictBatchResult: 批量结果；平台侧不可达时各类型返回空结果（降级）。
        """
        body: dict[str, object] = {
            "types": list(query.types),
            "version": query.version,
            "locale": query.locale,
        }
        request = ServiceRequest(
            service=DICT_SERVICE_KEY,
            method="POST",
            path=DICT_BATCH_PATH,
            headers=_headers(query.locale),
            json_body=body,
        )
        data = await _call(self._client, request)
        if data is None:
            return DictBatchResult(version=0, items={name: _empty_result() for name in query.types})
        raw_items = data.get("items")
        items: dict[str, DictTypeResult | None] = {}
        if isinstance(raw_items, Mapping):
            for name, value in cast("Mapping[str, object]", raw_items).items():
                if value is None:
                    items[str(name)] = None
                elif isinstance(value, Mapping):
                    items[str(name)] = _to_type_result(cast("Mapping[str, object]", value))
        for name in query.types:
            items.setdefault(name, _empty_result())
        return DictBatchResult(version=_as_int(data.get("version")), items=items)


class HttpDictTranslator(BaseDictTranslator):
    """跨服务字典翻译（按值子集分批取数 → 本地映射；不可达回退原值）。"""

    plugin_name: str = HTTP_DICT_PROVIDER
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, client: BaseServiceClient, cache: DictCacheRegion | None = None) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端。
            cache: 字典缓存域（可选；用于 value → label 子集映射的本地复用）。
        """
        self._client = client
        self._cache = cache

    async def translate(self, query: DictTranslateQuery) -> Mapping[str, str]:
        """按 value 批量翻译为 label（未命中回退原值；平台侧不可达同样回退原值）。

        Args:
            query: 翻译参数对象。

        Returns:
            Mapping[str, str]: value → label（未命中项映射为原值）。
        """
        mapping: dict[str, str] = {value: value for value in query.values}
        pending: list[str] = list(query.values)
        tenant = get_current_tenant()
        if self._cache is not None and pending:
            cached = await self._cache.avalue_subset(tenant, query.locale, query.dict_type, pending)
            if cached:
                mapping.update({value: label for value, label in cached.items()})
                pending = [value for value in pending if value not in cached]
        fresh: dict[str, str] = {}
        for chunk in _chunks(pending, TRANSLATE_VALUES_CHUNK):
            result = await _fetch_type(
                self._client,
                dict_type=query.dict_type,
                locale=query.locale,
                values=chunk,
            )
            if result is None or result.items is None:
                continue
            for item in result.items:
                if item.value in mapping:
                    fresh[item.value] = item.label
        mapping.update(fresh)
        if self._cache is not None and fresh:
            await self._cache.aset_value_subset(tenant, query.locale, query.dict_type, fresh)
        return mapping


def _chunks(values: Sequence[str], size: int) -> list[tuple[str, ...]]:
    """按批大小切分 value 序列（空序列返回空列表）。

    Args:
        values: value 序列。
        size: 单批上限。

    Returns:
        list[tuple[str, ...]]: 分批结果。
    """
    if size <= 0 or not values:
        return []
    return [tuple(values[index : index + size]) for index in range(0, len(values), size)]
