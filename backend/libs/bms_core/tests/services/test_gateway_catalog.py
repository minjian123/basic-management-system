"""网关声明式配置生成器测试（服务目录 → APISIX apisix.yaml）。Kiwi 2165。"""

import re
from typing import Any, cast

import pytest
import yaml

from bms_core.services import gateway_catalog as gc

_EXPECTED_SERVICES = (
    "platform",
    "identity",
    "tenant",
    "org",
    "file",
    "notification",
    "search",
    "ai",
    "report",
)


@pytest.mark.kiwi_id(2165)
def test_gateway_services_only_enabled_with_service_key() -> None:
    """仅启用且带服务标识的服务参与；planned（wf）与纯模块行排除。"""
    records = gc.gateway_services()
    assert tuple(record.service_key for record in records) == _EXPECTED_SERVICES
    assert all(record.status == "enabled" for record in records)


@pytest.mark.kiwi_id(2165)
def test_render_upstreams_shape() -> None:
    """上游段：id=service_key、节点=DNS名:端口、roundrobin。"""
    upstreams = gc.render_upstreams()
    assert [item["id"] for item in upstreams] == list(_EXPECTED_SERVICES)
    for item in upstreams:
        key = item["id"]
        assert item["type"] == "roundrobin"
        assert item["nodes"] == {f"{key}:{gc.SERVICE_PORT}": 1}
        assert gc.upstream_node(str(key)) == f"{key}:{gc.SERVICE_PORT}"


@pytest.mark.kiwi_id(2165)
def test_render_routes_shape_and_rewrite() -> None:
    """路由段：外部前缀 + 前缀重写；绑定存在的上游；重写还原为 /api/v1/...。"""
    upstream_ids = {item["id"] for item in gc.render_upstreams()}
    routes = gc.render_routes()
    assert [item["id"] for item in routes] == [f"route-{key}" for key in _EXPECTED_SERVICES]
    for route, key in zip(routes, _EXPECTED_SERVICES, strict=True):
        prefix = f"/api/{key}/v1"
        assert route["uris"] == [prefix, f"{prefix}/*"]
        assert route["upstream_id"] == key
        assert route["upstream_id"] in upstream_ids
        plugins = cast("dict[str, Any]", route["plugins"])
        rewrite = cast("dict[str, Any]", plugins["proxy-rewrite"])
        pattern, replacement = cast("list[str]", rewrite["regex_uri"])
        assert (pattern, replacement) == (f"^{prefix}(.*)$", "/api/v1$1")
        # APISIX regex_uri 的替换用 OpenResty 的 `$1` 语法（非 Python `\1`）：
        # 依「/api/v1 + 捕获组」还原，验证前缀剥离后的目标路径。
        samples = ((f"/api/{key}/v1/foo/bar", "/api/v1/foo/bar"), (prefix, "/api/v1"))
        for subject, expected in samples:
            matched = re.fullmatch(pattern, subject)
            assert matched is not None
            assert f"/api/v1{matched.group(1)}" == expected


@pytest.mark.kiwi_id(2165)
def test_render_is_deterministic() -> None:
    """同目录 → 同文本（供 Git 比对与 CI 零漂移）。"""
    assert gc.render_apisix_yaml() == gc.render_apisix_yaml()


@pytest.mark.kiwi_id(2165)
def test_route_plugins_hook_merges(monkeypatch: pytest.MonkeyPatch) -> None:
    """ROUTE_PLUGINS 钩子按 service_key 合并附加插件（认证 07_03 预留）。"""
    monkeypatch.setitem(gc.ROUTE_PLUGINS, "platform", {"openid-connect": {"client_id": "bms"}})
    by_id = {route["id"]: route for route in gc.render_routes()}
    plugins = cast("dict[str, Any]", by_id["route-platform"]["plugins"])
    assert "proxy-rewrite" in plugins
    assert plugins["openid-connect"] == {"client_id": "bms"}
    other = cast("dict[str, Any]", by_id["route-identity"]["plugins"])
    assert "openid-connect" not in other


@pytest.mark.kiwi_id(2165)
def test_render_apisix_yaml_is_valid_and_ends_with_marker() -> None:
    """生成件以 #END 结尾、可被 YAML 解析、结构含 upstreams / routes / global_rules / plugin_metadata。"""
    text = gc.render_apisix_yaml()
    assert text.endswith("#END\n")
    data = yaml.safe_load(text)
    assert set(data) == {"upstreams", "routes", "global_rules", "plugin_metadata"}
    assert len(data["upstreams"]) == len(_EXPECTED_SERVICES)
    assert len(data["routes"]) == len(_EXPECTED_SERVICES) + 1  # 服务路由 + 登录限流路由
    assert data["routes"][0]["upstream_id"] == "platform"


@pytest.mark.kiwi_id(2166)
def test_render_global_rules_strips_identity_headers() -> None:
    """全局净化规则：剥除客户端伪造身份头（含网关标记头）；标记置入归路由级。"""
    rules = {rule["id"]: rule for rule in gc.render_global_rules()}
    rule = rules["edge-sanitize"]
    plugin = cast("dict[str, Any]", cast("dict[str, Any]", rule["plugins"])["proxy-rewrite"])
    headers = cast("dict[str, Any]", plugin["headers"])
    assert "set" not in headers
    removed = cast("list[str]", headers["remove"])
    for name in ("X-User-Id", "X-Tenant-Id", "X-User-Scopes", "X-Service-Identity", "X-Gateway-Identity"):
        assert name in removed


@pytest.mark.kiwi_id(2166)
def test_route_headers_inject_marker_and_reserved_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """路由级注入：默认置网关专属标记；`ROUTE_HEADERS_SET` 登记后按服务合并身份头。"""
    default_rewrite = cast("dict[str, Any]", cast("dict[str, Any]", gc.render_routes()[0]["plugins"])["proxy-rewrite"])
    assert default_rewrite["headers"] == {"set": {gc.GATEWAY_IDENTITY_HEADER: gc.GATEWAY_IDENTITY_VALUE}}
    monkeypatch.setitem(gc.ROUTE_HEADERS_SET, "platform", {"X-User-Id": "$jwt_claim_sub"})
    by_id = {route["id"]: route for route in gc.render_routes()}
    rewrite = cast("dict[str, Any]", cast("dict[str, Any]", by_id["route-platform"]["plugins"])["proxy-rewrite"])
    assert rewrite["headers"] == {
        "set": {gc.GATEWAY_IDENTITY_HEADER: gc.GATEWAY_IDENTITY_VALUE, "X-User-Id": "$jwt_claim_sub"}
    }
    other = cast("dict[str, Any]", cast("dict[str, Any]", by_id["route-identity"]["plugins"])["proxy-rewrite"])
    assert other["headers"] == {"set": {gc.GATEWAY_IDENTITY_HEADER: gc.GATEWAY_IDENTITY_VALUE}}


@pytest.mark.kiwi_id(2165)
def test_dump_yaml_covers_collections_and_scalars() -> None:
    """YAML 发出器分支：空集合内联、标量类型与键转义。"""
    assert gc.dump_yaml({"a": {}}) == "a: {}"
    assert gc.dump_yaml({"a": []}) == "a: []"
    assert gc.dump_yaml({"a": [dict[str, object]()]}) == "a:\n  - {}"
    assert gc.dump_yaml({"a": [list[object]()]}) == "a:\n  - []"
    assert gc.dump_yaml({"a": [[1]]}) == "a:\n  -\n    - 1"
    assert gc.dump_yaml({"a": [1]}) == "a:\n  - 1"
    assert gc.dump_yaml([1, 2]) == "- 1\n- 2"
    assert gc.dump_yaml({"a": None}) == "a: null"
    assert gc.dump_yaml({"a": True, "b": False}) == "a: true\nb: false"
    assert gc.dump_yaml({"a": 1, "b": 1.5}) == "a: 1\nb: 1.5"
    assert gc.dump_yaml({"a": "x"}) == "a: x"
    assert gc.dump_yaml({"a": "a:b"}) == "a: 'a:b'"
    assert gc.dump_yaml({"a:b": "x"}) == "'a:b': x"
    assert gc.dump_yaml({"a": "it's"}) == "a: 'it''s'"


@pytest.mark.kiwi_id(2165)
def test_dump_yaml_rejects_unsupported_type() -> None:
    """YAML 发出器对不支持类型抛 TypeError。"""
    with pytest.raises(TypeError):
        gc.dump_yaml(object())


@pytest.mark.kiwi_id(2165)
def test_route_prefix_and_upstream_node() -> None:
    """外部前缀与上游节点约定。"""
    assert gc.route_prefix("identity") == "/api/identity/v1"
    assert gc.upstream_node("identity") == "identity:8000"


@pytest.mark.kiwi_id(2167)
def test_rate_limit_plugin_shared_redis() -> None:
    """限流插件：Redis 共享计数 + 用户 / 租户身份维度（var_combination）+ 环境变量替换 + 降级放行。"""
    plugin = gc.rate_limit_plugin(count=gc.DEFAULT_RATE_LIMIT_COUNT, window=gc.DEFAULT_RATE_LIMIT_WINDOW)
    assert plugin["count"] == 300
    assert plugin["time_window"] == 60
    assert plugin["key_type"] == gc.RATE_LIMIT_KEY_TYPE == "var_combination"
    assert plugin["key"] == gc.RATE_LIMIT_KEY == "$remote_addr $http_x_tenant_id $http_x_user_subject"
    assert plugin["policy"] == "redis"
    assert plugin["redis_host"] == "${{GATEWAY_REDIS_HOST:=redis}}"
    assert plugin["redis_port"] == 6379
    assert plugin["redis_database"] == 0
    assert plugin["redis_password"] == "${{GATEWAY_REDIS_PASSWORD:=}}"
    assert plugin["rejected_code"] == 429
    assert plugin["allow_degradation"] is True
    assert plugin["show_limit_quota_header"] is True
    # 维度可覆盖（如按纯 IP）
    assert gc.rate_limit_plugin(count=1, window=1, key="$remote_addr")["key"] == "$remote_addr"


@pytest.mark.kiwi_id(2181)
def test_forward_auth_plugin_config() -> None:
    """forward-auth 接线：转调认证服务内部校验端点、转发 / 注入头与 fail-closed。"""
    plugin = gc.forward_auth_plugin()
    assert plugin["uri"] == (
        f"http://${{{{GATEWAY_AUTH_HOST:={gc.DEFAULT_GATEWAY_AUTH_HOST}}}}}:{gc.SERVICE_PORT}{gc.AUTH_INTROSPECT_PATH}"
    )
    assert plugin["request_method"] == "GET"
    assert plugin["request_headers"] == ["Authorization"]
    assert plugin["upstream_headers"] == [
        "Authorization",
        "X-User-Subject",
        "X-User-Id",
        "X-Tenant-Id",
        "X-User-Scopes",
    ]
    assert plugin["client_headers"] == ["WWW-Authenticate"]
    assert plugin["timeout"] == gc.AUTH_TIMEOUT_MS == 3000
    assert plugin["status_on_error"] == gc.AUTH_STATUS_ON_ERROR == 503


@pytest.mark.kiwi_id(2181)
def test_all_routes_include_forward_auth() -> None:
    """每条服务路由与登录路由均挂 forward-auth，且 proxy-rewrite 仍置网关标记。"""
    for route in [*gc.render_routes(), *gc.render_login_routes()]:
        plugins = cast("dict[str, Any]", route["plugins"])
        assert plugins[gc.FORWARD_AUTH_PLUGIN] == gc.forward_auth_plugin()
        rewrite = cast("dict[str, Any]", plugins["proxy-rewrite"])
        assert rewrite["headers"] == {"set": {gc.GATEWAY_IDENTITY_HEADER: gc.GATEWAY_IDENTITY_VALUE}}


@pytest.mark.kiwi_id(2167)
def test_service_routes_include_rate_limit_and_prometheus() -> None:
    """每条服务路由注入限流（通用档）与观测出口（prometheus）。"""
    for route in gc.render_routes():
        plugins = cast("dict[str, Any]", route["plugins"])
        assert plugins["limit-count"]["count"] == gc.DEFAULT_RATE_LIMIT_COUNT
        assert plugins["limit-count"]["policy"] == "redis"
        assert plugins["prometheus"] == {}


@pytest.mark.kiwi_id(2167)
def test_login_route_stricter_and_prioritized() -> None:
    """登录限流路由：精确认证敏感路径 + 显式更高优先级 + 更严档位 + 同上游重写。"""
    routes = gc.render_login_routes()
    assert len(routes) == 1
    route = routes[0]
    assert route["id"] == gc.LOGIN_ROUTE_ID
    assert route["uris"] == list(gc.LOGIN_PATHS)
    assert "/api/identity/v1/auth/login" in gc.LOGIN_PATHS
    assert route["priority"] == gc.LOGIN_ROUTE_PRIORITY > 0
    assert route["upstream_id"] == gc.LOGIN_SERVICE_KEY
    plugins = cast("dict[str, Any]", route["plugins"])
    assert plugins["limit-count"]["count"] == gc.LOGIN_RATE_LIMIT_COUNT == 10
    assert plugins["limit-count"]["time_window"] == gc.LOGIN_RATE_LIMIT_WINDOW == 60
    assert plugins["prometheus"] == {}
    rewrite = cast("dict[str, Any]", plugins["proxy-rewrite"])
    assert rewrite["regex_uri"] == ["^/api/identity/v1(.*)$", "/api/v1$1"]
    # 登录路由并入完整配置的路由段
    ids = [item["id"] for item in cast("list[Any]", gc.render_apisix_config()["routes"])]
    assert gc.LOGIN_ROUTE_ID in ids


@pytest.mark.kiwi_id(2167)
def test_real_ip_global_rule() -> None:
    """全局 real-ip 规则：取 nginx 覆写的 X-Real-IP、限定可信网段（环境变量替换）。"""
    rules = {rule["id"]: rule for rule in gc.render_global_rules()}
    plugin = cast("dict[str, Any]", cast("dict[str, Any]", rules["edge-real-ip"]["plugins"])["real-ip"])
    assert plugin["source"] == "http_x_real_ip"
    assert plugin["trusted_addresses"] == ["${{GATEWAY_TRUSTED_CIDR:=172.16.0.0/12}}"]


@pytest.mark.kiwi_id(2167)
def test_gray_traffic_hook_merges(monkeypatch: pytest.MonkeyPatch) -> None:
    """灰度钩子：默认不注入；登记后按 service_key 合并 traffic-split 加权配置。"""
    by_id = {route["id"]: route for route in gc.render_routes()}
    assert "traffic-split" not in cast("dict[str, Any]", by_id["route-tenant"]["plugins"])
    monkeypatch.setitem(
        gc.GRAY_TRAFFIC,
        "tenant",
        {"rules": [{"weighted_upstreams": [{"upstream_id": "tenant-v2", "weight": 1}]}]},
    )
    routes = {route["id"]: route for route in gc.render_routes()}
    plugins = cast("dict[str, Any]", routes["route-tenant"]["plugins"])
    assert plugins["traffic-split"] == {"rules": [{"weighted_upstreams": [{"upstream_id": "tenant-v2", "weight": 1}]}]}
    other = cast("dict[str, Any]", routes["route-identity"]["plugins"])
    assert "traffic-split" not in other


@pytest.mark.kiwi_id(2167)
def test_plugin_metadata_declared() -> None:
    """限流响应头名以 plugin_metadata 声明（声明式扩展点）。"""
    metadata = gc.render_plugin_metadata()
    assert metadata == [
        {
            "id": "limit-count",
            "limit_header": "X-RateLimit-Limit",
            "remaining_header": "X-RateLimit-Remaining",
            "reset_header": "X-RateLimit-Reset",
        }
    ]


@pytest.mark.kiwi_id(2167)
def test_validate_service_discovery_flags_hardcoded_ip() -> None:
    """服务发现护栏：正常生成件通过；上游节点 / 限流 redis_host 为 IP 时报违规。"""
    assert gc.validate_service_discovery(gc.render_apisix_config()) == []
    bad_upstream = {
        "upstreams": [{"id": "platform", "type": "roundrobin", "nodes": {"10.0.0.5:8000": 1}}],
        "routes": [],
    }
    assert gc.validate_service_discovery(bad_upstream) == ["上游 platform 节点为硬编码 IP：10.0.0.5:8000"]
    bad_redis = {
        "upstreams": [],
        "routes": [
            {"id": "route-a", "plugins": {"limit-count": {"redis_host": "192.168.1.1"}}},
        ],
    }
    assert gc.validate_service_discovery(bad_redis) == ["路由 route-a 限流 redis_host 为硬编码 IP：192.168.1.1"]


@pytest.mark.kiwi_id(2167)
def test_validate_service_discovery_tolerates_malformed_config() -> None:
    """护栏对畸形结构（非 dict 项 / 非 dict nodes 或 plugins / 无 redis_host）容错放行。"""
    malformed: dict[str, object] = {
        "upstreams": ["not-a-dict", {"id": "x", "nodes": "not-a-dict"}],
        "routes": ["not-a-dict", {"id": "r", "plugins": "not-a-dict"}, {"id": "r2", "plugins": {"limit-count": "x"}}],
    }
    assert gc.validate_service_discovery(malformed) == []
    assert gc.validate_service_discovery({}) == []


@pytest.mark.kiwi_id(2167)
def test_login_route_absent_when_service_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """认证服务未启用时不生成登录限流路由（避免悬空上游）。"""
    monkeypatch.setattr(gc, "LOGIN_SERVICE_KEY", "wf")
    assert gc.render_login_routes() == []
