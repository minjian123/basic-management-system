"""字典路由：`/api/v1/dicts`（登录即可；2026-10-11 02_09 口径返工）。

- 运行时取数：`GET /dicts/{data_source_key}`（版本 / 关键字 / 级联 / 按条目 id 子集 / 上限）与
  `POST /dicts/batch`（多标识合并）；**取数经统一数据源出口**（平台内建数据源），契约形状不变。
- 登记清单：`GET /api/v1/data-sources`（统一数据源登记清单；供数据权限左列 / 通用页面）——02_10 已由
  字典专用 `GET /dicts` **迁至** `api/data_source.py`。
- 高级查询：`GET /dicts/query-providers`（提供者清单）/ `GET /dicts/{data_source_key}/attrs`（属性 schema）/
  `POST /dicts/{data_source_key}/advanced-query`（`target=items` 条件引擎 / `target=business` 提供者）。
- **维护 / 属性端点已删除**（字典类型 / 条目 / 属性一套剔除，写路径随表拆除）。
- locale：按 `Accept-Language` 解析（`current_dict_locale` 上下文；端点内 `with` 作用域设置与复位）。
- 路由注册顺序：静态段（`batch` / `query-providers`）先于 `/{data_source_key}` 通配。
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated, cast

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_data_source,
    get_dict_query_service,
    get_query_provider_registry,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.dict.base import (
    BaseDataSource,
    DictBatchQuery,
    DictBatchResult,
    DictQuery,
    DictTypeResult,
    current_dict_locale,
)
from bms_core.dict.query import (
    DictAdvQueryPayload,
    DictAdvQueryResult,
    DictAttrListResponse,
    DictQueryProviderInfo,
    DictQueryProviderListResponse,
    DictQueryService,
)
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.query.base import BaseQueryProvider, BaseQueryProviderRegistry
from bms_core.schemas.common import ApiResponse

router = BaseRouter(
    key="dict",
    prefix="/dicts",
    tags=["dict"],
    dependencies=[Depends(require_auth)],
)

SourceDep = Annotated[BaseDataSource, Depends(get_data_source)]
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


def parse_ids(raw: str) -> ConcurrentStableList[int]:
    """解析逗号分隔的条目 id 列表（`ids=1,2,3`；须为正整数）。

    Args:
        raw: 逗号分隔字符串。

    Returns:
        ConcurrentStableList[int]: 条目 id 列表（去空白项、保序）。

    Raises:
        ParamError: 含非整数或非正数项（400 语义，由统一处理器转响应）。
    """
    ids: ConcurrentStableList[int] = ConcurrentStableList()
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        if not text.isdigit() or int(text) <= 0:
            raise ParamError(f"ids 需为正整数：{text}")
        ids.add(int(text))
    return ids


@router.post("/batch")
async def batch_dicts(source: SourceDep, query: DictBatchQuery, request: Request) -> ApiResponse[DictBatchResult]:
    """批量合并取字典（一次请求多标识；版本一致的标识 items 返回 null）。

    Args:
        source: 字典取数契约。
        query: 批量取数参数（types / version / locale）。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse[DictBatchResult]: 统一响应，data 为批量结果。
    """
    with _locale_scope(request):
        return ApiResponse.ok(await source.batch(query))


@router.get("/query-providers")
async def list_query_providers(
    registry: RegistryDep,
    data_source_key: Annotated[str | None, Query(description="按字典标识过滤（空 = 全部）")] = None,
) -> ApiResponse[DictQueryProviderListResponse]:
    """列可用查询提供者（按标识过滤；含参数 schema 子集）。

    Args:
        registry: 查询提供者注册表。
        data_source_key: 字典标识（可选）。

    Returns:
        ApiResponse[DictQueryProviderListResponse]: 统一响应，data 为提供者清单（`items` 保序）。
    """
    items: ConcurrentStableList[DictQueryProviderInfo] = ConcurrentStableList()
    provider_keys = registry.keys()
    for key in provider_keys:
        provider = registry.get(key)
        if provider is None:
            continue
        record = _provider_info(key, provider)
        if (
            data_source_key is not None
            and len(record.data_source_keys) > 0
            and data_source_key not in record.data_source_keys
        ):
            continue
        items.add(record)
    return ApiResponse.ok(DictQueryProviderListResponse(items=items))


def _provider_info(key: str, provider: BaseQueryProvider) -> DictQueryProviderInfo:
    """提供者 → 清单项（有 `info()` 用其声明，否则按契约降级）。

    Args:
        key: 提供者键。
        provider: 提供者实例。

    Returns:
        DictQueryProviderInfo: 清单项。
    """
    info = getattr(provider, "info", None)
    if callable(info):
        return cast("DictQueryProviderInfo", info())
    return DictQueryProviderInfo(
        key=key,
        name=provider.describe(),
        target="business",
        data_source_keys=ConcurrentStableList(()),
        param_schema=ConcurrentStableDict(),
    )


@router.get("/{data_source_key}/attrs")
async def get_dict_attrs(
    query_service: QueryServiceDep, data_source_key: str, request: Request
) -> ApiResponse[DictAttrListResponse]:
    """取字典查询字段 schema（供高级查询条件构建；本期为固定字段）。

    Args:
        query_service: 高级查询服务。
        data_source_key: 字典标识。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse[DictAttrListResponse]: 统一响应，data 为字段清单（`items` 保序）。
    """
    with _locale_scope(request):
        attrs = await query_service.load_attrs(data_source_key)
    return ApiResponse.ok(DictAttrListResponse(items=ConcurrentStableList(attrs)))


@router.post("/{data_source_key}/advanced-query")
async def advanced_query_dict(
    query_service: QueryServiceDep,
    registry: RegistryDep,
    data_source_key: str,
    payload: DictAdvQueryPayload,
    request: Request,
) -> ApiResponse[DictAdvQueryResult]:
    """字典高级查询（items 条件引擎 / business 提供者）。

    Args:
        query_service: 高级查询服务。
        registry: 查询提供者注册表。
        data_source_key: 字典标识。
        payload: 查询请求体。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse[DictAdvQueryResult]: 统一响应，data 为分页结果。
    """
    with _locale_scope(request):
        result = await query_service.advanced_query(data_source_key, payload, registry=registry)
    return ApiResponse.ok(result)


@router.get("/{data_source_key}")
async def get_dict_by_type(
    source: SourceDep,
    data_source_key: str,
    request: Request,
    version: Annotated[int | None, Query(description="客户端本地版本号（一致时 items 返回 null）")] = None,
    keyword: Annotated[str | None, Query(description="关键字（label / value / code）")] = None,
    parent_id: Annotated[int | None, Query(ge=0, description="上级条目 ID（0 = 顶层；不传 = 不按父过滤）")] = None,
    ids: Annotated[str | None, Query(description="指定条目 id 子集（逗号分隔的正整数）")] = None,
    limit: Annotated[int | None, Query(ge=1, description="返回条数上限（探针传 2001）")] = None,
) -> ApiResponse[DictTypeResult]:
    """按字典标识取字典（版本比对 / 关键字 / 级联 / 按条目 id 子集 / 上限）。

    Args:
        source: 字典取数契约。
        data_source_key: 字典标识。
        request: 请求对象（语言解析）。
        version: 客户端本地版本号。
        keyword: 关键字。
        parent_id: 上级条目 ID（0 = 顶层）。
        ids: 逗号分隔的条目 id 子集（正整数）。
        limit: 返回条数上限。

    Returns:
        ApiResponse[DictTypeResult]: 统一响应，data 为单标识取数结果。
    """
    query = DictQuery(
        data_source_key=data_source_key,
        version=version,
        keyword=keyword,
        parent_id=parent_id,
        ids=parse_ids(ids) if ids else None,
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
