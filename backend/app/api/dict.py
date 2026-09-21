"""字典路由：`/api/v1/dicts`（登录即可；真实取数 / 缓存 / 高级查询 / 写路径随 02-4-27 落地）。

- 运行时取数：`GET /dicts/{dict_type}`（版本 / 关键字 / 级联父值 / 按值子集 / 上限）与
  `POST /dicts/batch`（多类型合并；既有契约与响应形状不变）。
- 高级查询：`GET /dicts/query-providers`（提供者清单）/ `GET /dicts/{dict_type}/attrs`（属性 schema）/
  `POST /dicts/{dict_type}/advanced-query`（`target=items` 条件引擎 / `target=business` 提供者）。
- 写路径（简化 REST）：类型 / 条目 / 属性 CRUD（先写库后删缓存 + `INCR` 版本）；权限码 `dict:manage` 随 RBAC 阶段
  （当前 `require_auth` 占位）。
- locale：按 `Accept-Language` 解析（`current_dict_locale` 上下文；端点内 `with` 作用域设置与复位）。
- 路由注册顺序：静态段（`batch` / `query-providers` / `types` / `items` / `attrs`）先于 `/{dict_type}` 通配。
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated, cast

from fastapi import Depends, Query, Request

from app.api.base import BaseRouter, require_auth
from app.api.deps import (
    get_dict_query_service,
    get_dict_service,
    get_dict_source,
    get_dict_translator,
    get_query_provider_registry,
)
from app.dict.base import (
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictQuery,
)
from app.dict.models import SysDictAttr, SysDictItem, SysDictType
from app.dict.query import DictAdvQueryPayload, DictQueryProviderInfo, DictQueryService
from app.dict.service import DictAttrPayload, DictItemPayload, DictService, DictTypePayload
from app.dict.sql import current_dict_locale
from app.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from app.query.base import BaseQueryProvider, BaseQueryProviderRegistry
from app.schemas.common import ApiResponse

router = BaseRouter(
    key="dict",
    prefix="/dicts",
    tags=["dict"],
    dependencies=[Depends(require_auth)],
)

SourceDep = Annotated[BaseDictSource, Depends(get_dict_source)]
TranslatorDep = Annotated[BaseDictTranslator, Depends(get_dict_translator)]
ServiceDep = Annotated[DictService, Depends(get_dict_service)]
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


@router.post("/batch")
async def batch_dicts(source: SourceDep, query: DictBatchQuery, request: Request) -> ApiResponse:
    """批量合并取字典（一次请求多类型；版本一致的类型 items 返回 null）。

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
    dict_type: Annotated[str | None, Query(description="按字典类型过滤（空 = 全部）")] = None,
) -> ApiResponse:
    """列可用查询提供者（按 type 过滤；含参数 schema 子集）。

    Args:
        registry: 查询提供者注册表。
        dict_type: 字典类型码（可选）。

    Returns:
        ApiResponse: 统一响应，data 为提供者清单数组。
    """
    items: list[dict[str, object]] = []
    provider_keys = registry.keys()
    for key in provider_keys:
        provider = registry.get(key)
        if provider is None:
            continue
        record = _provider_record(key, provider)
        dict_types = record.get("dict_types")
        if dict_type is not None and isinstance(dict_types, list):
            names = [str(item) for item in cast("list[object]", dict_types)]
            if len(names) > 0 and dict_type not in names:
                continue
        items.append(record)
    return ApiResponse.ok(items)


def _provider_record(key: str, provider: BaseQueryProvider) -> dict[str, object]:
    """提供者 → 清单记录（有 `info()` 用其声明，否则按契约降级）。

    Args:
        key: 提供者键。
        provider: 提供者实例。

    Returns:
        dict[str, object]: 清单记录。
    """
    info = getattr(provider, "info", None)
    if callable(info):
        payload = cast("DictQueryProviderInfo", info())
        return {str(name): value for name, value in payload.model_dump().items()}
    return {
        "key": key,
        "name": provider.describe(),
        "target": "business",
        "dict_types": [],
        "param_schema": {},
    }


@router.post("/types")
async def create_dict_type(service: ServiceDep, payload: DictTypePayload) -> ApiResponse:
    """新增字典类型。

    Args:
        service: 字典写路径服务。
        payload: 类型载荷。

    Returns:
        ApiResponse: 统一响应，data 为类型行。
    """
    row = await service.create_type(payload)
    return ApiResponse.ok(_type_out(row))


@router.put("/types/{type_id}")
async def update_dict_type(service: ServiceDep, type_id: int, payload: DictTypePayload) -> ApiResponse:
    """修改字典类型（乐观锁）。

    Args:
        service: 字典写路径服务。
        type_id: 类型 ID。
        payload: 类型载荷。

    Returns:
        ApiResponse: 统一响应，data 为类型行。
    """
    row = await service.update_type(type_id, payload)
    return ApiResponse.ok(_type_out(row))


@router.delete("/types/{type_id}")
async def delete_dict_type(service: ServiceDep, type_id: int) -> ApiResponse:
    """软删除字典类型。

    Args:
        service: 字典写路径服务。
        type_id: 类型 ID。

    Returns:
        ApiResponse: 统一响应（data 为 null）。
    """
    await service.delete_type(type_id)
    return ApiResponse.ok(None)


@router.post("/types/{dict_type}/items")
async def create_dict_item(service: ServiceDep, dict_type: str, payload: DictItemPayload) -> ApiResponse:
    """新增字典条目（类型内编码唯一）。

    Args:
        service: 字典写路径服务。
        dict_type: 字典类型码。
        payload: 条目载荷。

    Returns:
        ApiResponse: 统一响应，data 为条目行。
    """
    row = await service.create_item(dict_type, payload)
    return ApiResponse.ok(_item_out(row))


@router.post("/types/{dict_type}/attrs")
async def upsert_dict_attr(service: ServiceDep, dict_type: str, payload: DictAttrPayload) -> ApiResponse:
    """新增 / 更新字典扩展属性（按 `attr_key` upsert）。

    Args:
        service: 字典写路径服务。
        dict_type: 字典类型码。
        payload: 属性载荷。

    Returns:
        ApiResponse: 统一响应，data 为属性行。
    """
    row = await service.upsert_attr(dict_type, payload)
    return ApiResponse.ok(_attr_out(row))


@router.put("/items/{item_id}")
async def update_dict_item(service: ServiceDep, item_id: int, payload: DictItemPayload) -> ApiResponse:
    """修改字典条目（乐观锁）。

    Args:
        service: 字典写路径服务。
        item_id: 条目 ID。
        payload: 条目载荷。

    Returns:
        ApiResponse: 统一响应，data 为条目行。
    """
    row = await service.update_item(item_id, payload)
    return ApiResponse.ok(_item_out(row))


@router.delete("/items/{item_id}")
async def delete_dict_item(service: ServiceDep, item_id: int) -> ApiResponse:
    """软删除字典条目。

    Args:
        service: 字典写路径服务。
        item_id: 条目 ID。

    Returns:
        ApiResponse: 统一响应（data 为 null）。
    """
    await service.delete_item(item_id)
    return ApiResponse.ok(None)


@router.delete("/attrs/{attr_id}")
async def delete_dict_attr(service: ServiceDep, attr_id: int) -> ApiResponse:
    """软删除字典扩展属性。

    Args:
        service: 字典写路径服务。
        attr_id: 属性 ID。

    Returns:
        ApiResponse: 统一响应（data 为 null）。
    """
    await service.delete_attr(attr_id)
    return ApiResponse.ok(None)


@router.get("/{dict_type}/attrs")
async def get_dict_attrs(query_service: QueryServiceDep, dict_type: str, request: Request) -> ApiResponse:
    """取字典类型属性 schema（供高级查询条件构建）。

    Args:
        query_service: 高级查询服务。
        dict_type: 字典类型码。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse: 统一响应，data 为属性清单。
    """
    with _locale_scope(request):
        attrs = await query_service.load_attrs(dict_type)
    return ApiResponse.ok([attr.model_dump() for attr in attrs])


@router.post("/{dict_type}/advanced-query")
async def advanced_query_dict(
    query_service: QueryServiceDep,
    registry: RegistryDep,
    dict_type: str,
    payload: DictAdvQueryPayload,
    request: Request,
) -> ApiResponse:
    """字典高级查询（items 条件引擎 / business 提供者）。

    Args:
        query_service: 高级查询服务。
        registry: 查询提供者注册表。
        dict_type: 字典类型码。
        payload: 查询请求体。
        request: 请求对象（语言解析）。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    with _locale_scope(request):
        result = await query_service.advanced_query(dict_type, payload, registry=registry)
    return ApiResponse.ok(result.model_dump())


@router.get("/{dict_type}")
async def get_dict_by_type(
    source: SourceDep,
    dict_type: str,
    request: Request,
    version: Annotated[int | None, Query(description="客户端本地版本号（一致时 items 返回 null）")] = None,
    keyword: Annotated[str | None, Query(description="关键字（label / value / code）")] = None,
    parent_id: Annotated[str | None, Query(description="级联父值（引用父条目 value；空串 = 顶层）")] = None,
    values: Annotated[str | None, Query(description="指定 value 子集（逗号分隔）")] = None,
    limit: Annotated[int | None, Query(ge=1, description="返回条数上限（探针传 2001）")] = None,
) -> ApiResponse:
    """按类型取字典（版本比对 / 关键字 / 级联 / 按值子集 / 上限）。

    Args:
        source: 字典取数契约。
        dict_type: 字典类型码。
        request: 请求对象（语言解析）。
        version: 客户端本地版本号。
        keyword: 关键字。
        parent_id: 级联父值（空串 = 顶层）。
        values: 逗号分隔的 value 子集。
        limit: 返回条数上限。

    Returns:
        ApiResponse: 统一响应，data 为单类型取数结果。
    """
    query = DictQuery(
        dict_type=dict_type,
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


def _type_out(row: SysDictType) -> dict[str, object]:
    """类型行 → 响应字典。

    Args:
        row: 类型行。

    Returns:
        dict[str, object]: 响应数据。
    """
    return {
        "id": row.id,
        "type": row.type,
        "name": row.name,
        "sort": row.sort,
        "status": row.status,
    }


def _item_out(row: SysDictItem) -> dict[str, object]:
    """条目行 → 响应字典。

    Args:
        row: 条目行。

    Returns:
        dict[str, object]: 响应数据。
    """
    return {
        "id": row.id,
        "type_id": row.type_id,
        "code": row.code,
        "label": row.label,
        "value": row.value,
        "parent_id": row.parent_id,
        "color": row.color,
        "sort": row.sort,
        "status": row.status,
    }


def _attr_out(row: SysDictAttr) -> dict[str, object]:
    """属性行 → 响应字典。

    Args:
        row: 属性行。

    Returns:
        dict[str, object]: 响应数据。
    """
    return {
        "id": row.id,
        "type_id": row.type_id,
        "attr_key": row.attr_key,
        "name": row.name,
        "data_type": row.data_type,
        "operators": list(row.operators) if row.operators is not None else None,
        "widget": row.widget,
        "options": list(row.options) if row.options is not None else None,
        "sort": row.sort,
        "status": row.status,
        "scope": row.scope,
    }
