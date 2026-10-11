"""字典路由：`/api/v1/dicts`（登录即可；2026-10-11 02_09 口径返工）。

- 运行时取数：`GET /dicts/{dict_key}`（版本 / 关键字 / 级联 / 按值子集 / 上限）与
  `POST /dicts/batch`（多标识合并）；**取数经字典统一出口**（平台内建数据源），契约形状不变。
- 登记清单：`GET /dicts`（可用字典登记清单；供数据权限左列 / 字典页）。
- 高级查询：`GET /dicts/query-providers`（提供者清单）/ `GET /dicts/{dict_key}/attrs`（属性 schema）/
  `POST /dicts/{dict_key}/advanced-query`（`target=items` 条件引擎 / `target=business` 提供者）。
- **维护 / 属性端点已删除**（字典类型 / 条目 / 属性一套剔除，写路径随表拆除）。
- locale：按 `Accept-Language` 解析（`current_dict_locale` 上下文；端点内 `with` 作用域设置与复位）。
- 路由注册顺序：静态段（`batch` / `query-providers`）先于 `/{dict_key}` 通配。
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated, cast

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_dict_query_service,
    get_dict_source,
    get_dict_translator,
    get_query_provider_registry,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.dict.base import (
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictQuery,
    current_dict_locale,
)
from bms_core.dict.outlet import build_dict_outlet
from bms_core.dict.query import DictAdvQueryPayload, DictQueryProviderInfo, DictQueryService
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.query.base import BaseQueryProvider, BaseQueryProviderRegistry
from bms_core.schemas.common import ApiResponse

router = BaseRouter(
    key="dict",
    prefix="/dicts",
    tags=["dict"],
    dependencies=[Depends(require_auth)],
)

SourceDep = Annotated[BaseDictSource, Depends(get_dict_source)]
TranslatorDep = Annotated[BaseDictTranslator, Depends(get_dict_translator)]
QueryServiceDep = Annotated[DictQueryService, Depends(get_dict_query_service)]
RegistryDep = Annotated[BaseQueryProviderRegistry, Depends(get_query_provider_registry)]


@contextmanager
def _locale_scope(request: Request) -> Generator[None]:
    """请求语言作用域：设置 `current_dict_locale` 上下文，退出复位。

    Args:
        request: 请求对象（取 `Accept-Language`）。

    Yields:
        None: 作用域内语言生效。
    """
    token = current_dict_locale.set(_accept_locale(request))
    try:
        yield
    finally:
        current_dict_locale.reset(token)


def parse_values(raw: str) -> tuple[str, ...]:
    """解析逗号分隔的 value 列表（`values=a,b,c`）。

    Args:
        raw: 逗号分隔字符串。

    Returns:
        tuple[str, ...]: value 元组（去空白项）。
    """
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@router.get("")
async def list_dicts(translator: TranslatorDep) -> ApiResponse:
    """列可用字典登记清单（供数据权限左列 / 字典页）。

    Args:
        translator: 字典翻译契约（占位注入以固定鉴权依赖顺序，未使用）。

    Returns:
        ApiResponse: 统一响应，data 为登记清单数组。
    """
    records: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for record in build_dict_outlet().registry.catalog_records():
        records.add(
            ConcurrentStableDict(
                {
                    "dict_key": record.dict_key,
                    "name": record.name,
                    "origin": record.origin,
                    "product_key": record.product_key,
                    "path": record.path,
                    "allowlist": list(record.allowlist),
                    "cascade": record.cascade,
                    "strategies": list(record.strategies),
                    "status": record.status,
                }
            )
        )
    return ApiResponse.ok([dict(record) for record in records])


@router.post("/batch")
async def batch_dicts(source: SourceDep, query: DictBatchQuery, request: Request) -> ApiResponse:
    """批量合并取字典（一次请求多标识；版本一致的标识 items 返回 null）。

    Args:
        source: 字典取数契约。
        query: 批量取数参数（types / version / locale）。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse: 统一响应，data 为批量结果。
    """
    with _locale_scope(request):
        return ApiResponse.ok(await source.batch(query))


@router.get("/query-providers")
async def list_query_providers(
    registry: RegistryDep,
    dict_key: Annotated[str | None, Query(description="按字典标识过滤（空 = 全部）")] = None,
) -> ApiResponse:
    """列可用查询提供者（按标识过滤；含参数 schema 子集）。

    Args:
        registry: 查询提供者注册表。
        dict_key: 字典标识（可选）。

    Returns:
        ApiResponse: 统一响应，data 为提供者清单数组。
    """
    items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    provider_keys = registry.keys()
    for key in provider_keys:
        provider = registry.get(key)
        if provider is None:
            continue
        record = _provider_record(key, provider)
        dict_keys = record.get("dict_keys")
        if dict_key is not None and isinstance(dict_keys, list):
            names = [str(item) for item in cast("list[object]", dict_keys)]
            if len(names) > 0 and dict_key not in names:
                continue
        items.add(record)
    return ApiResponse.ok([dict(record) for record in items])


def _provider_record(key: str, provider: BaseQueryProvider) -> ConcurrentStableDict[str, object]:
    """提供者 → 清单记录（有 `info()` 用其声明，否则按契约降级）。

    Args:
        key: 提供者键。
        provider: 提供者实例。

    Returns:
        ConcurrentStableDict[str, object]: 清单记录。
    """
    info = getattr(provider, "info", None)
    if callable(info):
        payload = cast("DictQueryProviderInfo", info())
        return ConcurrentStableDict({str(name): value for name, value in payload.model_dump(mode="json").items()})
    return ConcurrentStableDict(
        {
            "key": key,
            "name": provider.describe(),
            "target": "business",
            "dict_keys": [],
            "param_schema": {},
        }
    )


@router.get("/{dict_key}/attrs")
async def get_dict_attrs(query_service: QueryServiceDep, dict_key: str, request: Request) -> ApiResponse:
    """取字典查询字段 schema（供高级查询条件构建；本期为固定字段）。

    Args:
        query_service: 高级查询服务。
        dict_key: 字典标识。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse: 统一响应，data 为字段清单。
    """
    with _locale_scope(request):
        attrs = await query_service.load_attrs(dict_key)
    return ApiResponse.ok([attr.model_dump(mode="json") for attr in attrs])


@router.post("/{dict_key}/advanced-query")
async def advanced_query_dict(
    query_service: QueryServiceDep,
    registry: RegistryDep,
    dict_key: str,
    payload: DictAdvQueryPayload,
    request: Request,
) -> ApiResponse:
    """字典高级查询（items 条件引擎 / business 提供者）。

    Args:
        query_service: 高级查询服务。
        registry: 查询提供者注册表。
        dict_key: 字典标识。
        payload: 查询请求体。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    with _locale_scope(request):
        result = await query_service.advanced_query(dict_key, payload, registry=registry)
    return ApiResponse.ok(result.model_dump(mode="json"))


@router.get("/{dict_key}")
async def get_dict_by_type(
    source: SourceDep,
    dict_key: str,
    request: Request,
    version: Annotated[int | None, Query(description="客户端本地版本号（一致时 items 返回 null）")] = None,
    keyword: Annotated[str | None, Query(description="关键字（label / value / code）")] = None,
    parent_id: Annotated[int | None, Query(ge=0, description="上级条目 ID（0 = 顶层；不传 = 不按父过滤）")] = None,
    values: Annotated[str | None, Query(description="指定 value 子集（逗号分隔）")] = None,
    limit: Annotated[int | None, Query(ge=1, description="返回条数上限（探针传 2001）")] = None,
) -> ApiResponse:
    """按字典标识取字典（版本比对 / 关键字 / 级联 / 按值子集 / 上限）。

    Args:
        source: 字典取数契约。
        dict_key: 字典标识。
        request: 请求对象（语言解析）。
        version: 客户端本地版本号。
        keyword: 关键字。
        parent_id: 上级条目 ID（0 = 顶层）。
        values: 逗号分隔的 value 子集。
        limit: 返回条数上限。

    Returns:
        ApiResponse: 统一响应，data 为单标识取数结果。
    """
    query = DictQuery(
        dict_key=dict_key,
        version=version,
        keyword=keyword,
        parent_id=parent_id,
        values=parse_values(values) if values else None,
        limit=limit,
    )
    with _locale_scope(request):
        return ApiResponse.ok(await source.by_type(query))


def _accept_locale(request: Request) -> str:
    """解析 `Accept-Language`（支持清单内匹配；缺省默认语言）。

    Args:
        request: 请求对象。

    Returns:
        str: 生效语言。
    """
    raw = request.headers.get("accept-language", "")
    for part in raw.split(","):
        tag = part.split(";")[0].strip()
        if not tag:
            continue
        if tag in SUPPORTED_LOCALES:
            return tag
        prefix = tag.split("-")[0].lower()
        for supported in SUPPORTED_LOCALES:
            if supported.split("-")[0].lower() == prefix:
                return supported
    return DEFAULT_LOCALE
