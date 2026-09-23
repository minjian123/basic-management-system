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
    """ROUTE_PLUGINS 钩子按 service_key 合并附加插件（认证 / 限流预留）。"""
    monkeypatch.setitem(gc.ROUTE_PLUGINS, "platform", {"limit-count": {"count": 10}})
    by_id = {route["id"]: route for route in gc.render_routes()}
    plugins = cast("dict[str, Any]", by_id["route-platform"]["plugins"])
    assert "proxy-rewrite" in plugins
    assert plugins["limit-count"] == {"count": 10}
    other = cast("dict[str, Any]", by_id["route-identity"]["plugins"])
    assert "limit-count" not in other


@pytest.mark.kiwi_id(2165)
def test_render_apisix_yaml_is_valid_and_ends_with_marker() -> None:
    """生成件以 #END 结尾、可被 YAML 解析、结构含 upstreams / routes。"""
    text = gc.render_apisix_yaml()
    assert text.endswith("#END\n")
    data = yaml.safe_load(text)
    assert set(data) == {"upstreams", "routes"}
    assert len(data["upstreams"]) == len(_EXPECTED_SERVICES)
    assert len(data["routes"]) == len(_EXPECTED_SERVICES)
    assert data["routes"][0]["upstream_id"] == "platform"


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
