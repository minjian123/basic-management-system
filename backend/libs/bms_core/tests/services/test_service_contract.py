"""服务公开契约工具测试（Kiwi 2168 / 2227）：启用服务枚举 / 确定性渲染 / 契约校验 / 路由覆盖护栏。"""

import json
from types import SimpleNamespace

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.services.service_contract import (
    contract_file_name,
    enabled_service_records,
    hidden_route_violations,
    render_contract_json,
    route_coverage_gaps,
    service_enabled,
    service_route_sets,
    validate_contract,
)


@pytest.mark.kiwi_id(2168)
def test_contract_file_name() -> None:
    """快照文件名由服务标识派生。"""
    assert contract_file_name("platform") == "platform.json"


@pytest.mark.kiwi_id(2168)
def test_enabled_services_and_lookup() -> None:
    """启用服务枚举只含 service_key 非空且启用的行；planned 服务不可用。"""
    records = enabled_service_records()
    keys = {record.service_key for record in records}
    assert "platform" in keys and "identity" in keys
    assert "workflow" not in keys  # planned
    assert service_enabled("platform") is True
    assert service_enabled("workflow") is False
    assert service_enabled("ghost") is False


@pytest.mark.kiwi_id(2168)
def test_render_contract_deterministic() -> None:
    """渲染确定性：键序无关，产出同一文本。"""
    first = render_contract_json(ConcurrentStableDict({"b": 1, "a": {"y": 2, "x": 3}}))
    second = render_contract_json(ConcurrentStableDict({"a": {"x": 3, "y": 2}, "b": 1}))
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == {"a": {"x": 3, "y": 2}, "b": 1}


@pytest.mark.kiwi_id(2168)
def test_validate_contract() -> None:
    """契约校验：版本一致 / 结构齐备通过；版本不符 / 结构缺失报错。"""
    record = enabled_service_records()[0]
    good: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "openapi": "3.1.0",
            "info": ConcurrentStableDict({"title": "服务", "version": record.contract_version}),
            "paths": ConcurrentStableDict({"/api/v1/x": ConcurrentStableDict[str, object]()}),
        }
    )
    assert validate_contract("platform", good, record) == []

    bad_version: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "openapi": "3.1.0",
            "info": ConcurrentStableDict({"title": "服务", "version": "9.9.9"}),
            "paths": ConcurrentStableDict({"/api/v1/x": ConcurrentStableDict[str, object]()}),
        }
    )
    errors = validate_contract("platform", bad_version, record)
    assert any("契约版本不一致" in message for message in errors)

    missing: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "openapi": "3.1.0",
            "info": ConcurrentStableDict({"title": "", "version": record.contract_version}),
        }
    )
    errors = validate_contract("platform", missing, record)
    assert any("paths 为空" in message for message in errors)
    assert any("title 为空" in message for message in errors)

    empty: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    errors = validate_contract("platform", empty, record)
    assert any("缺少 openapi 版本字段" in message for message in errors)
    assert any("缺少 info 段" in message for message in errors)
    assert any("paths 为空" in message for message in errors)


def _leaf(path: str, *, include_in_schema: bool) -> SimpleNamespace:
    """构造实现路由叶子桩（模拟 FastAPI `APIRoute` / `_EffectiveRouteContext`）。"""
    return SimpleNamespace(path=path, include_in_schema=include_in_schema)


def _lazy_router(*routes: object) -> SimpleNamespace:
    """构造惰性路由容器桩（模拟 FastAPI `_IncludedRouter`：仅暴露 `effective_candidates()`）。"""
    return SimpleNamespace(effective_candidates=lambda: list(routes))


@pytest.mark.kiwi_id(2227)
def test_service_route_sets_extracts_nested_routes() -> None:
    """实现路由提取：惰性容器与路由器均下钻，按 `include_in_schema` 分组并去重。"""
    lazy = _lazy_router(_leaf("/api/v1/a", include_in_schema=True), _leaf("/docs", include_in_schema=False))
    mounted = SimpleNamespace(
        routes=ConcurrentStableList(
            [_leaf("/api/v1/b", include_in_schema=True), _leaf("/api/v1/a", include_in_schema=True)]
        )
    )
    app = SimpleNamespace(routes=ConcurrentStableList([lazy, mounted, _leaf("/healthz", include_in_schema=True)]))

    visible, invisible = service_route_sets(app)

    assert sorted(visible) == ["/api/v1/a", "/api/v1/b", "/healthz"]
    assert sorted(invisible) == ["/docs"]


@pytest.mark.kiwi_id(2227)
def test_service_route_sets_empty_is_detectable() -> None:
    """无路由的桩应用返回两空集（上层据此判失败，防漏检）。"""
    visible, invisible = service_route_sets(SimpleNamespace(routes=ConcurrentStableList()))

    assert len(visible) == 0
    assert len(invisible) == 0


@pytest.mark.kiwi_id(2227)
def test_route_coverage_gaps() -> None:
    """断言 A：实现路由（计入契约）多于契约 `paths` 时报缺失；完全覆盖时为空。"""
    implemented = ConcurrentStableSet({"/api/v1/a", "/api/v1/b"})

    assert list(route_coverage_gaps(implemented, ConcurrentStableSet({"/api/v1/a", "/api/v1/b", "/api/v1/c"}))) == []
    assert list(route_coverage_gaps(implemented, ConcurrentStableSet({"/api/v1/a"}))) == ["/api/v1/b"]


@pytest.mark.kiwi_id(2227)
def test_hidden_route_violations() -> None:
    """断言 B：不可见路由命中白名单通过；业务路径不可见报越界；支持自定义白名单。"""
    assert list(hidden_route_violations(ConcurrentStableSet({"/docs", "/metrics"}))) == []
    assert list(hidden_route_violations(ConcurrentStableSet({"/api/v1/a"}))) == ["/api/v1/a"]
    assert (
        list(
            hidden_route_violations(
                ConcurrentStableSet({"/api/v1/a"}),
                whitelist=ConcurrentStableSet({"/api/v1/a"}),
            )
        )
        == []
    )
