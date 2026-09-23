"""服务目录 → APISIX 声明式配置生成（网关路由 / 上游的单一来源）。

- 依据服务目录 `SERVICE_CATALOG`（`module_registry.py`）生成 APISIX **standalone 文件驱动**
  配置的 `upstreams` / `routes` 段：仅**启用**且带服务标识的行参与（服务 / 模块同源登记）。
- 外部路径 `/api/{service_key}/v1/...` 经 `proxy-rewrite` 还原为服务内 `/api/v1/...`
  （服务内前缀 `API_PREFIX` 不变；网关只做前缀剥离）。
- 上游按服务标识经 Compose DNS 寻址（`{service_key}:{SERVICE_PORT}`），迁 K8s 平移为 Service 名。
- 认证 / 限流插件经 `ROUTE_PLUGINS` 钩子按服务附加（04_02 / 04_03 填充；默认不启用）。
- 边缘请求净化：`global_rules` 统一剥除客户端伪造身份头；网关专属标记 + 身份注入落
  路由级 `proxy-rewrite.headers.set`（`ROUTE_HEADERS_SET` 钩子预留，07_03 填充）——真机实测
  global 规则 `headers.set` 会被路由级 `proxy-rewrite` 丢弃，故标记与身份统一落路由级（04_02）。
- 输出确定性（同目录 → 同文本），供 Git 比对与 CI 零漂移校验。

生成入口见 `backend/ops/gateway_config.py`；配置语义与 K8s 平移口径见任务 04_01 / 04_02 详细设计。
"""

from __future__ import annotations

import re
from typing import cast

from bms_core.edge.headers import GATEWAY_IDENTITY_HEADER, GATEWAY_IDENTITY_VALUE, STRIPPED_HEADERS
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord, ModuleStatus

__all__ = [
    "API_PREFIX",
    "GATEWAY_PATH_PREFIX",
    "ROUTE_HEADERS_SET",
    "ROUTE_PLUGINS",
    "SERVICE_PORT",
    "dump_yaml",
    "gateway_services",
    "render_apisix_config",
    "render_apisix_yaml",
    "render_global_rules",
    "render_routes",
    "render_upstreams",
    "route_prefix",
    "upstream_node",
]

API_PREFIX = "/api/v1"
"""服务内统一接口前缀（与 `bms_core/api/base.py::API_PREFIX` 同值，网关重写目标）。"""

GATEWAY_PATH_PREFIX = "/api"
"""网关外部路径前缀（外部形态 `/api/{service_key}/v1/...`）。"""

SERVICE_PORT = 8000
"""上游默认端口；每服务端口随「每服务独立配置」（06_需求）回改本常量来源。"""

ROUTE_PLUGINS: dict[str, dict[str, object]] = {}
"""路由级插件钩子（按 `service_key` 合并）。

04_03（限流：`limit-count`）与 07_03（认证：`openid-connect`）在此登记，
无需改动生成结构；默认空 = 不启用任何附加插件。
"""

ROUTE_HEADERS_SET: dict[str, dict[str, str]] = {}
"""路由级请求头注入钩子（按 `service_key` 合并到路由 `proxy-rewrite.headers.set`）。

07_03 填入网关验证过的身份头（如 `{"X-User-Id": "$jwt_claim_sub"}`）即完成「注入身份」，
无需改动生成结构；默认空 = 不注入（本任务只交付结构，不启用认证）。
"""

_GLOBAL_RULE_ID = "edge-sanitize"
"""全局请求净化规则 id（剥除客户端伪造身份头 + 置网关专属标记）。"""

_ROUTE_ID_PREFIX = "route-"
_REWRITE_SUFFIX = "$1"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_PLAIN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

_HEADER = (
    "# 本文件由 backend/ops/gateway_config.py render 生成，请勿手工修改。",
    "# 来源：服务目录 SERVICE_CATALOG（bms_core/services/module_registry.py）。",
    "# 重新生成：uv run python -m ops.gateway_config render",
    "# 零漂移校验：uv run python -m ops.gateway_config check",
)


def gateway_services() -> tuple[ModuleRecord, ...]:
    """参与网关路由的服务行（`service_key` 非空且 `status=enabled`）。

    Returns:
        tuple[ModuleRecord, ...]: 按服务目录原始顺序排列的服务登记行。
    """
    return tuple(
        record for record in SERVICE_CATALOG if record.service_key is not None and record.status == ModuleStatus.ENABLED
    )


def _enabled_service_keys() -> list[str]:
    """启用服务的标识列表（顺序与目录一致）。

    Returns:
        list[str]: 服务标识（`service_key`）。
    """
    return [cast("str", record.service_key) for record in gateway_services()]


def route_prefix(service_key: str) -> str:
    """服务的外部路径前缀（`/api/{service_key}/v1`）。

    Args:
        service_key: 服务标识。

    Returns:
        str: 外部路径前缀。
    """
    return f"{GATEWAY_PATH_PREFIX}/{service_key}/v1"


def upstream_node(service_key: str) -> str:
    """上游节点地址（Compose DNS 名 + 端口）。

    Args:
        service_key: 服务标识。

    Returns:
        str: 形如 `identity:8000` 的节点地址。
    """
    return f"{service_key}:{SERVICE_PORT}"


def _rewrite_regex(service_key: str) -> str:
    """前缀剥离正则：`^/api/{service_key}/v1(.*)$`。"""
    return f"^{route_prefix(service_key)}(.*)$"


def render_upstreams() -> list[dict[str, object]]:
    """上游段（每启用服务一条，`roundrobin`）。

    Returns:
        list[dict[str, object]]: APISIX `upstreams` 列表。
    """
    return [
        {
            "id": service_key,
            "type": "roundrobin",
            "nodes": {upstream_node(service_key): 1},
        }
        for service_key in _enabled_service_keys()
    ]


def render_routes() -> list[dict[str, object]]:
    """路由段（每启用服务一条，含前缀重写与插件钩子合并）。

    Returns:
        list[dict[str, object]]: APISIX `routes` 列表。
    """
    routes: list[dict[str, object]] = []
    for service_key in _enabled_service_keys():
        headers_set: dict[str, str] = {GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE}
        headers_set.update(ROUTE_HEADERS_SET.get(service_key) or {})
        rewrite: dict[str, object] = {
            "regex_uri": [_rewrite_regex(service_key), f"{API_PREFIX}{_REWRITE_SUFFIX}"],
            "headers": {"set": headers_set},
        }
        plugins: dict[str, object] = {"proxy-rewrite": rewrite}
        plugins.update(ROUTE_PLUGINS.get(service_key) or {})
        prefix = route_prefix(service_key)
        routes.append(
            {
                "id": f"{_ROUTE_ID_PREFIX}{service_key}",
                "uris": [prefix, f"{prefix}/*"],
                "upstream_id": service_key,
                "plugins": plugins,
            }
        )
    return routes


def render_global_rules() -> list[dict[str, object]]:
    """全局请求净化规则：剥除客户端伪造身份头（04_02）。

    网关专属标记的置入**归路由级** `proxy-rewrite.headers.set`（见 `render_routes`）：
    真机实测（mjbk，2026-09-23）global 规则的 `headers.remove` 生效、`headers.set` 在路由级
    `proxy-rewrite` 执行后被丢弃，故标记与身份注入统一落路由级；剥头保留在 global 规则（集中、一次生效）。

    Returns:
        list[dict[str, object]]: APISIX `global_rules` 列表。
    """
    return [
        {
            "id": _GLOBAL_RULE_ID,
            "plugins": {"proxy-rewrite": {"headers": {"remove": list(STRIPPED_HEADERS)}}},
        }
    ]


def render_apisix_config() -> dict[str, object]:
    """完整配置映射（可扩展 `consumers` / `plugin_metadata`）。

    Returns:
        dict[str, object]: APISIX 配置映射。
    """
    return {
        "upstreams": render_upstreams(),
        "routes": render_routes(),
        "global_rules": render_global_rules(),
    }


def render_apisix_yaml() -> str:
    """确定性 YAML 文本（末尾 `#END`，APISIX 文件驱动必需结束标记）。

    Returns:
        str: 完整 `apisix.yaml` 内容。
    """
    return "\n".join([*_HEADER, dump_yaml(render_apisix_config()), "#END", ""])


def dump_yaml(value: object) -> str:
    """把映射 / 序列 / 标量渲染为最小 YAML 文本（公开展出以复用与单测）。

    Args:
        value: 待序列化的值（仅支持 dict / list / 标量）。

    Returns:
        str: YAML 文本（无末尾换行）。
    """
    return "\n".join(_dump(value, 0))


def _dump(value: object, indent: int) -> list[str]:
    """最小 YAML 发出器（仅覆盖本模块使用的 dict / list / 标量结构）。

    Args:
        value: 待序列化值。
        indent: 当前缩进空格数。

    Returns:
        list[str]: YAML 行。

    Raises:
        TypeError: 遇到不支持的值类型。
    """
    if isinstance(value, dict):
        return _dump_mapping(cast("dict[object, object]", value), indent)
    if isinstance(value, list):
        return _dump_sequence(cast("list[object]", value), indent)
    raise TypeError(f"不支持的 YAML 值类型：{type(value)!r}")


def _dump_mapping(mapping: dict[object, object], indent: int) -> list[str]:
    """映射序列化（值非空 dict / list 走子块，空集合内联）。"""
    pad = " " * indent
    lines: list[str] = []
    for raw_key, item in mapping.items():
        key = _key(str(raw_key))
        if isinstance(item, dict):
            inner = cast("dict[object, object]", item)
            if inner:
                lines.append(f"{pad}{key}:")
                lines.extend(_dump_mapping(inner, indent + 2))
            else:
                lines.append(f"{pad}{key}: {{}}")
        elif isinstance(item, list):
            values = cast("list[object]", item)
            if values:
                lines.append(f"{pad}{key}:")
                lines.extend(_dump_sequence(values, indent + 2))
            else:
                lines.append(f"{pad}{key}: []")
        else:
            lines.append(f"{pad}{key}: {_scalar(item)}")
    return lines


def _dump_sequence(sequence: list[object], indent: int) -> list[str]:
    """序列序列化（列表项为映射时首键与 `- ` 同行）。"""
    pad = " " * indent
    lines: list[str] = []
    for item in sequence:
        if isinstance(item, dict):
            inner = cast("dict[object, object]", item)
            if not inner:
                lines.append(f"{pad}- {{}}")
                continue
            rendered = _dump_mapping(inner, indent + 2)
            lines.append(f"{pad}- {rendered[0][indent + 2 :]}")
            lines.extend(rendered[1:])
        elif isinstance(item, list):
            values = cast("list[object]", item)
            if not values:
                lines.append(f"{pad}- []")
                continue
            lines.append(f"{pad}-")
            lines.extend(_dump_sequence(values, indent + 2))
        else:
            lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _scalar(value: object) -> str:
    """标量序列化（安全标识符裸写，其余单引号包裹）。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    if _PLAIN_RE.fullmatch(text) is not None:
        return text
    return "'" + text.replace("'", "''") + "'"


def _key(text: str) -> str:
    """映射键序列化（不安全键单引号包裹）。"""
    if _KEY_RE.fullmatch(text) is not None:
        return text
    return "'" + text.replace("'", "''") + "'"
