"""服务公开契约：启用服务枚举、快照渲染与契约校验（纯函数，不依赖任何服务包）。

- `enabled_service_records` / `service_enabled`：服务目录（`SERVICE_CATALOG`）视图。
- `render_contract_json`：公开契约（OpenAPI）确定性 JSON（同输入同文本，供 Git 比对与零漂移校验）。
- `validate_contract`：结构 + 契约版本校验（`info.version` 须等于服务目录登记的契约版本）。

快照生成（内存构建各服务应用 OpenAPI）在服务侧 CLI `backend/ops/contract_snapshot.py`
（共享库不得依赖服务包，故构建逻辑不入本模块）。
"""

import json
from collections.abc import Callable, Mapping
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.serialization import normalize_collections
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord, ModuleStatus, ServiceGroup

__all__ = [
    "BASELINE_DIR",
    "CONTRACTS_DIR",
    "EMPTY_SCHEMA_ALLOWLIST",
    "INVISIBLE_ROUTE_WHITELIST",
    "contract_file_name",
    "empty_schema_entries",
    "enabled_service_records",
    "hidden_route_violations",
    "render_contract_json",
    "response_schema_gaps",
    "route_coverage_gaps",
    "service_enabled",
    "service_route_sets",
    "validate_contract",
]

CONTRACTS_DIR = "deploy/contracts"
"""公开契约快照目录（相对仓库根；每启用服务一份 `<service_key>.json`）。"""

BASELINE_DIR = "deploy/contracts/baseline"
"""公开契约基线目录（相对仓库根；每启用服务一份 `<service_key>.json`，入 Git、仅经评审更新）。"""


def contract_file_name(service_key: str) -> str:
    """公开契约快照文件名。

    Args:
        service_key: 服务标识。

    Returns:
        str: 形如 `platform.json` 的文件名。
    """
    return f"{service_key}.json"


def enabled_service_records() -> tuple[ModuleRecord, ...]:
    """启用的**平台服务**登记行（`service_key` 非空 + 状态启用 + **非产品分组**）。

    产品分组服务（如 `org` 归 mdm）的公开契约**由产品侧自持**（不在 bms `deploy/contracts/`，
    也不参与 bms 的快照导出与 oasdiff 门禁，见 12_02 §3），故本视图排除之。

    Returns:
        tuple[ModuleRecord, ...]: 按服务目录原始顺序排列的启用平台服务行。
    """
    return tuple(
        record
        for record in SERVICE_CATALOG
        if record.service_key is not None
        and record.status == ModuleStatus.ENABLED
        and record.service_group != ServiceGroup.PRODUCT
    )


def service_enabled(service_key: str) -> bool:
    """目标服务是否在服务目录登记且启用（服务间调用寻址前置校验）。

    Args:
        service_key: 服务标识。

    Returns:
        bool: 已登记且启用 True。
    """
    return any(
        record.service_key == service_key and record.status == ModuleStatus.ENABLED for record in SERVICE_CATALOG
    )


def render_contract_json(openapi: ConcurrentStableDict[str, object]) -> str:
    """把公开契约（OpenAPI 映射）渲染为确定性 JSON 文本。

    Args:
        openapi: `app.openapi()` 产物（插入序；渲染前经 `normalize_collections` 规整）。

    Returns:
        str: 确定性 JSON（缩进 2 / 键排序 / 非 ASCII 直出 + 末尾换行）。
    """
    return json.dumps(normalize_collections(openapi), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def validate_contract(
    service_key: str, openapi: ConcurrentStableDict[str, object], record: ModuleRecord
) -> ConcurrentStableList[str]:
    """校验公开契约结构与契约版本（与登记值一致）。

    Args:
        service_key: 服务标识。
        openapi: 公开契约映射（插入序）。
        record: 服务目录登记行。

    Returns:
        ConcurrentStableList[str]: 违规明细；空列表表示通过。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    if not isinstance(openapi.get("openapi"), str):
        errors.add(f"{service_key}：OpenAPI 缺少 openapi 版本字段")
    info = openapi.get("info")
    if not isinstance(info, Mapping):
        errors.add(f"{service_key}：OpenAPI 缺少 info 段")
    else:
        info_map = cast("Mapping[str, object]", info)
        if not info_map.get("title"):
            errors.add(f"{service_key}：OpenAPI info.title 为空")
        version = info_map.get("version")
        if version != record.contract_version:
            errors.add(f"{service_key}：契约版本不一致（OpenAPI {version!r}，登记 {record.contract_version!r}）")
    paths = openapi.get("paths")
    if not isinstance(paths, Mapping) or not paths:
        errors.add(f"{service_key}：OpenAPI paths 为空")
    return errors


INVISIBLE_ROUTE_WHITELIST: ConcurrentStableSet[str] = ConcurrentStableSet(
    {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/metrics"}
)
"""不可见路由白名单：允许被排除出公开契约的实现路由。

仅框架内置文档端点（`/docs` / `/redoc` / `/openapi.json` / `/docs/oauth2-redirect`）与平台可观测
端点（`/metrics`）；**业务端点一律不得加入**——新增白名单项须在设计 / 规范侧说明理由（需求 06-3）。
"""


EMPTY_SCHEMA_ALLOWLIST: ConcurrentStableSet[str] = ConcurrentStableSet()
"""空 schema 白名单：允许在公开契约 `components.schemas` 中为空对象的条目名。

缺省为**空集**——公开契约不得缺失字段信息（响应体 schema 为空即响应契约失真、前端生成类型
退化为 `unknown`）。新增白名单项须在设计 / 规范侧说明理由；**业务 schema 一律不得入白名单**
（需求 06-4，与 `INVISIBLE_ROUTE_WHITELIST` 同纪律）。
"""


def _as_mapping(value: object) -> ConcurrentStableDict[str, object]:
    """把值规整为字符串键插入序映射（非映射时为空映射）。

    Args:
        value: 待规整值（契约段 / 响应 / 媒体类型等）。

    Returns:
        ConcurrentStableDict[str, object]: 规整后的映射（键统一字符串化）。
    """
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if not isinstance(value, Mapping):
        return result
    mapping = cast("Mapping[object, object]", value)
    for key, item in mapping.items():
        result.set(str(key), item)
    return result


def _component_schemas(openapi: ConcurrentStableDict[str, object]) -> ConcurrentStableDict[str, object]:
    """取公开契约 `components.schemas`（缺失 / 非映射时为空映射）。

    Args:
        openapi: 公开契约映射（`app.openapi()` 产物）。

    Returns:
        ConcurrentStableDict[str, object]: `components.schemas` 映射。
    """
    components = _as_mapping(openapi.get("components"))
    return _as_mapping(components.get("schemas"))


def _is_success_status(status: object) -> bool:
    """是否成功响应状态码（`2xx` 具体码或 `2XX` 通配）。

    Args:
        status: 响应状态码键。

    Returns:
        bool: 成功响应 True。
    """
    text = str(status).upper()
    return text == "2XX" or (len(text) == 3 and text.startswith("2"))


def _json_schema_gap(response: ConcurrentStableDict[str, object], schemas: ConcurrentStableDict[str, object]) -> str:
    """取响应体 JSON schema 的**引用**问题描述（非引用型 schema 不判定）。

    只判定 `$ref` 型响应 schema：引用必须可解析到**非空**的 `components.schemas` 条目。
    内联 schema（含空对象）不判定——它来自「原始 `Response` 端点未声明响应模型」（探针 / OIDC /
    SSO 回调等），与本域的「模型派生响应 schema 塌陷」是不同缺陷类，登记为后续任务归口。

    Args:
        response: 单个响应对象。
        schemas: 公开契约 `components.schemas` 映射。

    Returns:
        str: 问题描述；空串表示该响应无可判定问题。
    """
    content = _as_mapping(response.get("content"))
    media = _as_mapping(content.get("application/json"))
    schema_value = media.get("schema")
    if not isinstance(schema_value, Mapping):
        return ""
    ref = cast("Mapping[str, object]", schema_value).get("$ref")
    if not isinstance(ref, str):
        return ""
    name = ref.rsplit("/", 1)[-1]
    target = schemas.get(name)
    if not isinstance(target, Mapping):
        return f"响应 schema 引用未解析（{ref}）"
    if not target:
        return f"响应 schema 引用目标为空（{name}）"
    return ""


def empty_schema_entries(openapi: ConcurrentStableDict[str, object]) -> ConcurrentStableList[str]:
    """断言 C：公开契约 `components.schemas` 中为空对象的条目名。

    空对象即「无任何字段信息」——一旦出现在 `components.schemas`，说明契约丢失了该模型的
    结构（响应体 schema 失真、前端生成类型退化为 `unknown`）。

    Args:
        openapi: 公开契约映射（`app.openapi()` 产物）。

    Returns:
        ConcurrentStableList[str]: 违规条目名（升序，白名单命中者除外）；空列表表示通过。
    """
    violations: ConcurrentStableList[str] = ConcurrentStableList()
    for name, schema in _component_schemas(openapi).items():
        if isinstance(schema, Mapping) and not schema and name not in EMPTY_SCHEMA_ALLOWLIST:
            violations.add(name)
    return ConcurrentStableList(sorted(violations))


def response_schema_gaps(openapi: ConcurrentStableDict[str, object]) -> ConcurrentStableList[str]:
    """断言 D：成功响应（2xx）的**引用型** `application/json` schema 必须可解析且非空。

    配合断言 C（`components.schemas` 无空对象）锁定「模型派生响应 schema 塌陷」缺陷类：
    模型响应经 `$ref` 引用 `components.schemas`，引用可达且非空即说明模型契约未缺失字段信息。

    Args:
        openapi: 公开契约映射（`app.openapi()` 产物）。

    Returns:
        ConcurrentStableList[str]: 违规明细（升序，含方法 / 路径 / 状态码与原因）；空列表表示通过。
    """
    schemas = _component_schemas(openapi)
    gaps: ConcurrentStableList[str] = ConcurrentStableList()
    paths = _as_mapping(openapi.get("paths"))
    for path, operations in paths.items():
        for method, operation in _as_mapping(operations).items():
            responses = _as_mapping(_as_mapping(operation).get("responses"))
            for status, response in responses.items():
                if not _is_success_status(status):
                    continue
                reason = _json_schema_gap(_as_mapping(response), schemas)
                if reason:
                    gaps.add(f"{method.upper()} {path} [{status}]：{reason}")
    return ConcurrentStableList(sorted(gaps))


def _route_entries(routes: ConcurrentStableList[object]) -> ConcurrentStableList[tuple[str, bool]]:
    """递归展开应用路由树，收集 `(path, include_in_schema)` 实现路由条目。

    兼容 FastAPI 惰性路由：具备 `effective_candidates()` 可调用者遍历其返回值；具备 `routes`
    属性者继续下钻；同时具备 `path`（str）与 `include_in_schema`（bool）者即一条实现路由。

    Args:
        routes: 路由集合（应用 `routes` 或下钻得到的子集合）。

    Returns:
        ConcurrentStableList[tuple[str, bool]]: 实现路由条目（顺序稳定，未去重）。
    """
    entries: ConcurrentStableList[tuple[str, bool]] = ConcurrentStableList()
    for route in routes:
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            effective = cast("Callable[[], ConcurrentStableList[object]]", candidates)
            entries.update(_route_entries(effective()))
            continue
        sub_routes = getattr(route, "routes", None)
        if sub_routes is not None:
            entries.update(_route_entries(ConcurrentStableList(sub_routes)))
            continue
        path = getattr(route, "path", None)
        in_schema = getattr(route, "include_in_schema", None)
        if isinstance(path, str) and isinstance(in_schema, bool):
            entries.add((path, in_schema))
    return entries


def service_route_sets(app: object) -> tuple[ConcurrentStableSet[str], ConcurrentStableSet[str]]:
    """提取服务的实现路由集合，按是否计入公开契约分为两组。

    Args:
        app: 服务应用对象（`ApplicationFactory().create(None)` 产物）。

    Returns:
        tuple[ConcurrentStableSet[str], ConcurrentStableSet[str]]:
        `(计入契约的实现路由, 被排除出契约的实现路由)`，均为去重集合。
    """
    visible: ConcurrentStableSet[str] = ConcurrentStableSet()
    invisible: ConcurrentStableSet[str] = ConcurrentStableSet()
    for path, in_schema in _route_entries(ConcurrentStableList(getattr(app, "routes", []))):
        if in_schema:
            visible.add(path)
        else:
            invisible.add(path)
    return visible, invisible


def route_coverage_gaps(
    implemented: ConcurrentStableSet[str],
    paths: ConcurrentStableSet[str],
) -> ConcurrentStableList[str]:
    """断言 A：计入契约的实现路由中，未出现在公开契约 `paths` 的路径。

    Args:
        implemented: 计入契约的实现路由集合。
        paths: 公开契约 `paths` 键集合。

    Returns:
        ConcurrentStableList[str]: 缺失路径（升序）；空列表表示无漏登。
    """
    gaps: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(implemented):
        if path not in paths:
            gaps.add(path)
    return gaps


def hidden_route_violations(
    hidden: ConcurrentStableSet[str],
    *,
    whitelist: ConcurrentStableSet[str] | None = None,
) -> ConcurrentStableList[str]:
    """断言 B：被排除出契约的实现路由中，超出白名单的路径。

    Args:
        hidden: 被排除出公开契约的实现路由集合。
        whitelist: 白名单（缺省 `INVISIBLE_ROUTE_WHITELIST`）。

    Returns:
        ConcurrentStableList[str]: 越界路径（升序）；空列表表示无违规。
    """
    allowed = whitelist if whitelist is not None else INVISIBLE_ROUTE_WHITELIST
    violations: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(hidden):
        if path not in allowed:
            violations.add(path)
    return violations
