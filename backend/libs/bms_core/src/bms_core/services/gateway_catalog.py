"""服务目录 → APISIX 声明式配置生成（网关路由 / 上游的单一来源）。

- 依据服务目录 `SERVICE_CATALOG`（`module_registry.py`）生成 APISIX **standalone 文件驱动**
  配置的 `upstreams` / `routes` 段：仅**启用**且带服务标识的行参与（服务 / 模块同源登记）。
- 外部路径 `/api/{service_key}/v1/...` 经 `proxy-rewrite` 还原为服务内 `/api/v1/...`
  （服务内前缀 `API_PREFIX` 不变；网关只做前缀剥离）。
- 上游按服务标识经 Compose DNS 寻址（`{service_key}:{SERVICE_PORT}`），迁 K8s 平移为 Service 名。
- 认证插件按服务附加（07_03）：每条服务路由与认证敏感登录路由挂 `forward-auth`，转调认证服务
  内部校验端点（`{GATEWAY_AUTH_HOST}:8000/api/v1/auth/introspect`）——用户 JWT 由认证服务按 `aud=api`
  全校验，公开路径由认证端点判定；校验通过后网关按 `upstream_headers` 注入契约身份头并覆盖
  `Authorization` 为网关服务 JWT（`aud=service`），后端只信任有效服务 JWT。
- 边缘请求净化：`global_rules` 统一剥除客户端伪造身份头；网关专属标记 + 身份注入落
  路由级 `proxy-rewrite.headers.set`（`ROUTE_HEADERS_SET` 钩子保留；认证身份头改由 `forward-auth`
  的 `upstream_headers` 注入，见 `forward_auth_plugin`）——真机实测
  global 规则 `headers.set` 会被路由级 `proxy-rewrite` 丢弃，故标记统一落路由级（04_02）。
- 边缘限流（04_03）：每条路由注入 `limit-count`（`policy: redis` 共享多副本计数，默认按真实
  客户端 IP、通用档 300/60s）；认证敏感路径生成独立路由（更严 10/60s、显式优先级）；Redis 主机 /
  密码经 `${{GATEWAY_REDIS_HOST:=redis}}` / `${{GATEWAY_REDIS_PASSWORD:=}}` 环境变量替换
  （端口 / 库用整数字面量——真机实测 `limit-count` schema 要求整数，环境变量替换产出字符串会校验失败）。
- 服务发现护栏（04_03）：`validate_service_discovery` 断言上游节点为服务名、不得为 IP 字面量。
- 边缘观测出口（04_03）：路由挂 `prometheus`，指标端点与访问日志配置见 `deploy/gateway/config.yaml`
  （真实采集 / 展示归 08 可观测性栈）。
- 灰度预留（04_03）：`GRAY_TRAFFIC` 钩子按服务合并 `traffic-split` 加权配置（默认空）。
- 输出确定性（同目录 → 同文本），供 Git 比对与 CI 零漂移校验。

生成入口见 `backend/ops/gateway_config.py`；配置语义与 K8s 平移口径见任务 04_01 / 04_02 详细设计。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from bms_core.edge.headers import (
    GATEWAY_IDENTITY_HEADER,
    GATEWAY_IDENTITY_VALUE,
    STRIPPED_HEADERS,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    USER_SCOPES_HEADER,
    USER_SUBJECT_HEADER,
)
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord, ModuleStatus

__all__ = [
    "API_PREFIX",
    "AUTH_CLIENT_HEADERS",
    "AUTH_INTROSPECT_PATH",
    "AUTH_REQUEST_HEADERS",
    "AUTH_STATUS_ON_ERROR",
    "AUTH_TIMEOUT_MS",
    "AUTH_UPSTREAM_HEADERS",
    "DEFAULT_GATEWAY_AUTH_HOST",
    "DEFAULT_RATE_LIMIT_COUNT",
    "DEFAULT_RATE_LIMIT_WINDOW",
    "FORWARD_AUTH_PLUGIN",
    "GATEWAY_AUTH_HOST_VAR",
    "GATEWAY_PATH_PREFIX",
    "GRAY_TRAFFIC",
    "LOGIN_PATHS",
    "LOGIN_RATE_LIMIT_COUNT",
    "LOGIN_RATE_LIMIT_WINDOW",
    "LOGIN_ROUTE_ID",
    "LOGIN_ROUTE_PRIORITY",
    "RATE_LIMIT_KEY_TYPE",
    "ROUTE_HEADERS_SET",
    "ROUTE_PLUGINS",
    "SERVICE_PORT",
    "dump_yaml",
    "env_var",
    "forward_auth_plugin",
    "gateway_services",
    "rate_limit_plugin",
    "render_apisix_config",
    "render_apisix_yaml",
    "render_global_rules",
    "render_login_routes",
    "render_plugin_metadata",
    "render_routes",
    "render_upstreams",
    "route_prefix",
    "upstream_node",
    "validate_service_discovery",
]

API_PREFIX = "/api/v1"
"""服务内统一接口前缀（与 `bms_core/api/base.py::API_PREFIX` 同值，网关重写目标）。"""

GATEWAY_PATH_PREFIX = "/api"
"""网关外部路径前缀（外部形态 `/api/{service_key}/v1/...`）。"""

SERVICE_PORT = 8000
"""上游默认端口；每服务端口随「每服务独立配置」（06_需求）回改本常量来源。"""

ROUTE_PLUGINS: dict[str, dict[str, object]] = {}
"""路由级插件钩子（按 `service_key` 合并）。

认证（`forward-auth`）/ 限流（`limit-count`）/ 观测（`prometheus`）/ 灰度（`traffic-split`）
由本模块直接产出；本钩子暂空（保留声明式扩展点）。
"""

ROUTE_HEADERS_SET: dict[str, dict[str, str]] = {}
"""路由级请求头注入钩子（按 `service_key` 合并到路由 `proxy-rewrite.headers.set`）。

07_03 起「网关验证过的身份头」改由 `forward-auth.upstream_headers` 注入（认证服务产出、网关覆盖
`Authorization`），本钩子保留为空；`proxy-rewrite.headers.set` 仍置网关专属标记 `X-Gateway-Identity`。
"""

GRAY_TRAFFIC: dict[str, dict[str, object]] = {}
"""灰度路由钩子（按 `service_key` 合并为路由级 `traffic-split` 插件配置，04_03 预留）。

默认空 = 不启用灰度、流量不变；配置形如
`{"weighted_upstreams": [{"upstream_id": "tenant-v2", "weight": 1}, {"upstream_id": "tenant", "weight": 9}]}`
（按版本 / 权重灰度，规则声明式入 Git、迁 K8s 平移 HTTPRoute `backendRefs` 权重）。
"""

DEFAULT_RATE_LIMIT_COUNT = 300
"""边缘限流通用档：窗口内允许次数（按真实客户端 IP）。"""

DEFAULT_RATE_LIMIT_WINDOW = 60
"""边缘限流通用档：窗口秒数。"""

LOGIN_RATE_LIMIT_COUNT = 10
"""登录限流档：认证敏感路径窗口内允许次数（更严，防爆破）。"""

LOGIN_RATE_LIMIT_WINDOW = 60
"""登录限流档：窗口秒数。"""

RATE_LIMIT_REJECTED_CODE = 429
"""超限响应码（与《API接口规范》「429 限流」一致）。"""

RATE_LIMIT_KEY = "$remote_addr $http_x_tenant_id $http_x_user_subject"
"""限流维度（`var_combination`：真实客户端 IP + 网关注入的租户 / 用户主体；07_03 由纯 IP 扩展）。

用户维度取**当前可用的入站用户标识** `X-User-Subject`（网关注入的外部主体）；阶段六外部身份映射
填充 `X-User-Id`（内部数字 id）后可再纳入，不改结构。
"""

RATE_LIMIT_KEY_TYPE = "var_combination"
"""限流键类型（多变量组合；未注入身份时该段为空、仍按客户端 IP 计数）。"""

GATEWAY_REDIS_HOST_VAR = "GATEWAY_REDIS_HOST"
"""限流共享 Redis 主机环境变量名（默认 Compose DNS `redis`）。"""

GATEWAY_REDIS_PASSWORD_VAR = "GATEWAY_REDIS_PASSWORD"
"""限流共享 Redis 密码环境变量名（默认空 = 无鉴权；凭据经 `.env` 注入，不入库）。"""

GATEWAY_TRUSTED_CIDR_VAR = "GATEWAY_TRUSTED_CIDR"
"""可信代理网段环境变量名（`real-ip` 用，默认 Docker 私网 `172.16.0.0/12`）。"""

DEFAULT_GATEWAY_REDIS_HOST = "redis"
DEFAULT_GATEWAY_REDIS_PASSWORD = ""
DEFAULT_GATEWAY_TRUSTED_CIDR = "172.16.0.0/12"

RATE_LIMIT_REDIS_PORT = 6379
"""限流共享 Redis 端口（字面量整数：真机实测 `limit-count` schema 要求整数，环境变量替换产出字符串会校验失败）。"""

RATE_LIMIT_REDIS_DATABASE = 0
"""限流共享 Redis 库（字面量整数，同上）。"""

GATEWAY_AUTH_HOST_VAR = "GATEWAY_AUTH_HOST"
"""认证服务主机环境变量名（forward-auth 转调；默认 Compose DNS `identity`）。"""

DEFAULT_GATEWAY_AUTH_HOST = "identity"
"""认证服务默认主机（Compose DNS 服务名；非 Compose 环境经环境变量覆盖）。"""

AUTH_INTROSPECT_PATH = "/api/v1/auth/introspect"
"""认证服务内部校验端点路径（与 `bms_identity/api/auth.py` 同源约定）。"""

FORWARD_AUTH_PLUGIN = "forward-auth"
"""认证接线插件名（网关转调认证服务校验用户 JWT 并注入身份头）。"""

AUTH_REQUEST_HEADERS: tuple[str, ...] = ("Authorization",)
"""转发给认证服务的客户端头（用户 JWT）。"""

AUTH_UPSTREAM_HEADERS: tuple[str, ...] = (
    "Authorization",
    USER_SUBJECT_HEADER,
    USER_ID_HEADER,
    TENANT_ID_HEADER,
    USER_SCOPES_HEADER,
)
"""认证服务响应头中注入上游的头（覆盖 Authorization 为网关服务 JWT + 契约身份头）。"""

AUTH_CLIENT_HEADERS: tuple[str, ...] = ("WWW-Authenticate",)
"""认证失败时回传客户端的头。"""

AUTH_TIMEOUT_MS = 3000
"""认证子请求超时（毫秒）。"""

AUTH_STATUS_ON_ERROR = 503
"""认证服务不可达时的响应码（fail-closed；不降级放行）。"""

LOGIN_SERVICE_KEY = "identity"
"""认证敏感路径所属服务标识（登录限流独立路由的上游）。"""

LOGIN_PATHS: tuple[str, ...] = (
    f"{GATEWAY_PATH_PREFIX}/{LOGIN_SERVICE_KEY}/v1/auth/login",
    f"{GATEWAY_PATH_PREFIX}/{LOGIN_SERVICE_KEY}/v1/auth/refresh",
)
"""认证敏感路径（登录 / 刷新；限流更严，可随认证阶段扩展）。"""

LOGIN_ROUTE_ID = f"route-{LOGIN_SERVICE_KEY}-auth-login"
"""登录限流独立路由 id。"""

LOGIN_ROUTE_PRIORITY = 10
"""登录路由优先级（高于服务路由默认 0，保证精确路由优先命中）。"""

_GLOBAL_RULE_ID = "edge-sanitize"
"""全局请求净化规则 id（剥除客户端伪造身份头）。"""

_REAL_IP_RULE_ID = "edge-real-ip"
"""全局真实客户端 IP 规则 id（`real-ip`，供经 nginx 入口的限流按真实 IP 计数）。"""

_PROMETHEUS_PLUGIN = "prometheus"
"""边缘观测插件（路由挂载后按路由采集指标，导出端点见 `config.yaml` `plugin_attr.prometheus`）。"""

_LIMIT_COUNT_PLUGIN = "limit-count"
"""边缘限流插件（共享 Redis 多副本一致计数）。"""

_ROUTE_ID_PREFIX = "route-"
_REWRITE_SUFFIX = "$1"
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_PLAIN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def env_var(name: str, default: str) -> str:
    """APISIX 环境变量替换占位（`${{name:=default}}`）。

    APISIX 在 config.yaml 与 standalone apisix.yaml 均支持；缺省值保证生成件可独立跑通。

    Args:
        name: 环境变量名。
        default: 未设置时的回退值。

    Returns:
        str: 形如 `${{GATEWAY_REDIS_HOST:=redis}}` 的占位串。
    """
    return "${{" + name + ":=" + default + "}}"


def rate_limit_plugin(*, count: int, window: int, key: str = RATE_LIMIT_KEY) -> dict[str, object]:
    """构造 `limit-count` 插件配置（共享 Redis，多副本一致计数）。

    Args:
        count: 窗口内允许的最大请求次数。
        window: 窗口秒数。
        key: 限流维度（默认 `var_combination`：真实客户端 IP + 租户 / 用户）。

    Returns:
        dict[str, object]: APISIX `limit-count` 插件配置。
    """
    return {
        "count": count,
        "time_window": window,
        "key_type": RATE_LIMIT_KEY_TYPE,
        "key": key,
        "policy": "redis",
        "redis_host": env_var(GATEWAY_REDIS_HOST_VAR, DEFAULT_GATEWAY_REDIS_HOST),
        "redis_port": RATE_LIMIT_REDIS_PORT,
        "redis_database": RATE_LIMIT_REDIS_DATABASE,
        "redis_password": env_var(GATEWAY_REDIS_PASSWORD_VAR, DEFAULT_GATEWAY_REDIS_PASSWORD),
        "rejected_code": RATE_LIMIT_REJECTED_CODE,
        "allow_degradation": True,
        "show_limit_quota_header": True,
    }


def forward_auth_plugin() -> dict[str, object]:
    """构造 `forward-auth` 插件配置（转调认证服务校验用户 JWT 并注入身份头）。

    Returns:
        dict[str, object]: APISIX `forward-auth` 插件配置（认证服务主机经环境变量替换）。
    """
    host = env_var(GATEWAY_AUTH_HOST_VAR, DEFAULT_GATEWAY_AUTH_HOST)
    return {
        "uri": f"http://{host}:{SERVICE_PORT}{AUTH_INTROSPECT_PATH}",
        "request_method": "GET",
        "request_headers": list(AUTH_REQUEST_HEADERS),
        "upstream_headers": list(AUTH_UPSTREAM_HEADERS),
        "client_headers": list(AUTH_CLIENT_HEADERS),
        "timeout": AUTH_TIMEOUT_MS,
        "status_on_error": AUTH_STATUS_ON_ERROR,
    }


def _gray_plugins(service_key: str) -> dict[str, object]:
    """按服务合并灰度插件（`traffic-split`）；未配置返回空。"""
    gray = GRAY_TRAFFIC.get(service_key)
    if not gray:
        return {}
    return {"traffic-split": gray}


def validate_service_discovery(config: Mapping[str, object]) -> list[str]:
    """校验「服务发现按名寻址、禁硬编码 IP」。

    上游节点主机必须为服务名，`redis_host` 不得为 IP 字面量；违规以字符串清单返回。

    Args:
        config: 生成配置映射（`render_apisix_config()` 产物）。

    Returns:
        list[str]: 违规描述清单（空表示通过）。
    """
    violations: list[str] = []
    upstreams = config.get("upstreams")
    if isinstance(upstreams, list):
        for upstream in cast("list[object]", upstreams):
            if not isinstance(upstream, dict):
                continue
            record = cast("dict[str, object]", upstream)
            nodes = record.get("nodes")
            if not isinstance(nodes, dict):
                continue
            for node in cast("dict[str, object]", nodes):
                host = str(node).rsplit(":", 1)[0]
                if _IPV4_RE.match(host) is not None:
                    violations.append(f"上游 {record.get('id')} 节点为硬编码 IP：{node}")
    routes = config.get("routes")
    if isinstance(routes, list):
        for route in cast("list[object]", routes):
            if not isinstance(route, dict):
                continue
            record = cast("dict[str, object]", route)
            plugins = record.get("plugins")
            if not isinstance(plugins, dict):
                continue
            limit_count = cast("dict[str, object]", plugins).get(_LIMIT_COUNT_PLUGIN)
            if isinstance(limit_count, dict):
                host = str(cast("dict[str, object]", limit_count).get("redis_host", ""))
                if _IPV4_RE.match(host) is not None:
                    violations.append(f"路由 {record.get('id')} 限流 redis_host 为硬编码 IP：{host}")
    return violations


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
    """路由段（每启用服务一条，含前缀重写、限流、观测与插件钩子合并）。

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
        plugins: dict[str, object] = {
            "proxy-rewrite": rewrite,
            FORWARD_AUTH_PLUGIN: forward_auth_plugin(),
            _LIMIT_COUNT_PLUGIN: rate_limit_plugin(
                count=DEFAULT_RATE_LIMIT_COUNT,
                window=DEFAULT_RATE_LIMIT_WINDOW,
            ),
            _PROMETHEUS_PLUGIN: {},
        }
        plugins.update(_gray_plugins(service_key))
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


def render_login_routes() -> list[dict[str, object]]:
    """认证敏感路径的独立限流路由（登录限流优先，04_03）。

    仅当认证服务（`identity`）启用时生成；显式更高 `priority` 保证精确路由优先命中，
    挂更严档位并复用服务上游与路径重写。

    Returns:
        list[dict[str, object]]: APISIX `routes` 列表（0 或 1 条）。
    """
    if LOGIN_SERVICE_KEY not in _enabled_service_keys():
        return []
    headers_set: dict[str, str] = {GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE}
    headers_set.update(ROUTE_HEADERS_SET.get(LOGIN_SERVICE_KEY) or {})
    rewrite: dict[str, object] = {
        "regex_uri": [_rewrite_regex(LOGIN_SERVICE_KEY), f"{API_PREFIX}{_REWRITE_SUFFIX}"],
        "headers": {"set": headers_set},
    }
    plugins: dict[str, object] = {
        "proxy-rewrite": rewrite,
        FORWARD_AUTH_PLUGIN: forward_auth_plugin(),
        _LIMIT_COUNT_PLUGIN: rate_limit_plugin(
            count=LOGIN_RATE_LIMIT_COUNT,
            window=LOGIN_RATE_LIMIT_WINDOW,
        ),
        _PROMETHEUS_PLUGIN: {},
    }
    plugins.update(_gray_plugins(LOGIN_SERVICE_KEY))
    plugins.update(ROUTE_PLUGINS.get(LOGIN_SERVICE_KEY) or {})
    return [
        {
            "id": LOGIN_ROUTE_ID,
            "uris": list(LOGIN_PATHS),
            "priority": LOGIN_ROUTE_PRIORITY,
            "upstream_id": LOGIN_SERVICE_KEY,
            "plugins": plugins,
        }
    ]


def render_global_rules() -> list[dict[str, object]]:
    """全局规则：伪造身份头剥除（04_02）+ 真实客户端 IP 还原（04_03）。

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
        },
        {
            "id": _REAL_IP_RULE_ID,
            "plugins": {
                "real-ip": {
                    "source": "http_x_real_ip",
                    "trusted_addresses": [env_var(GATEWAY_TRUSTED_CIDR_VAR, DEFAULT_GATEWAY_TRUSTED_CIDR)],
                }
            },
        },
    ]


def render_plugin_metadata() -> list[dict[str, object]]:
    """插件元数据段（限流响应头名，声明式扩展点）。

    Returns:
        list[dict[str, object]]: APISIX `plugin_metadata` 列表。
    """
    return [
        {
            "id": _LIMIT_COUNT_PLUGIN,
            "limit_header": "X-RateLimit-Limit",
            "remaining_header": "X-RateLimit-Remaining",
            "reset_header": "X-RateLimit-Reset",
        }
    ]


def render_apisix_config() -> dict[str, object]:
    """完整配置映射（可扩展 `consumers` / `plugin_metadata`）。

    Returns:
        dict[str, object]: APISIX 配置映射。
    """
    return {
        "upstreams": render_upstreams(),
        "routes": [*render_routes(), *render_login_routes()],
        "global_rules": render_global_rules(),
        "plugin_metadata": render_plugin_metadata(),
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
