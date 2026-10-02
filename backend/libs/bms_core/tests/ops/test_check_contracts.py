"""契约护栏测试（Kiwi 2227 / 2228）：路由覆盖 / 不可见白名单 / 响应 schema 完整性 / CLI 退出码。"""

from types import SimpleNamespace

import pytest

import ops.check_contracts as check_contracts
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList


def _leaf(path: str, *, include_in_schema: bool) -> SimpleNamespace:
    """构造实现路由叶子桩（模拟 FastAPI `APIRoute` / `_EffectiveRouteContext`）。"""
    return SimpleNamespace(path=path, include_in_schema=include_in_schema)


def _stub_app(paths: ConcurrentStableList[str], routes: ConcurrentStableList[object]) -> SimpleNamespace:
    """构造桩应用：`openapi()` 返回给定 `paths`，`routes` 给定实现路由。"""

    def openapi() -> ConcurrentStableDict[str, object]:
        return ConcurrentStableDict(
            {"paths": ConcurrentStableDict({path: ConcurrentStableDict[str, object]() for path in paths})}
        )

    return SimpleNamespace(routes=routes, openapi=openapi)


@pytest.mark.kiwi_id(2227)
def test_check_service_passes_when_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """实现路由全部在契约、不可见路由全在白名单 → 无违规。"""
    app = _stub_app(
        ConcurrentStableList(["/api/v1/a"]),
        ConcurrentStableList([_leaf("/api/v1/a", include_in_schema=True), _leaf("/metrics", include_in_schema=False)]),
    )
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: app)
    assert list(check_contracts.check_service("stub")) == []


@pytest.mark.kiwi_id(2227)
def test_check_service_reports_missing_contract_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """实现路由未进入契约 `paths` → 报「未进入公开契约」（断言 A）。"""
    app = _stub_app(
        ConcurrentStableList(["/api/v1/a"]),
        ConcurrentStableList([_leaf("/api/v1/a", include_in_schema=True), _leaf("/api/v1/b", include_in_schema=True)]),
    )
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: app)
    errors = check_contracts.check_service("stub")
    assert any("未进入公开契约" in message and "/api/v1/b" in message for message in errors)


@pytest.mark.kiwi_id(2227)
def test_check_service_reports_hidden_business_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """业务端点被排除出契约且不在白名单 → 报「不在白名单」（断言 B）。"""
    app = _stub_app(
        ConcurrentStableList([]),
        ConcurrentStableList([_leaf("/api/v1/secret", include_in_schema=False)]),
    )
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: app)
    errors = check_contracts.check_service("stub")
    assert any("不在白名单" in message and "/api/v1/secret" in message for message in errors)


@pytest.mark.kiwi_id(2227)
def test_check_service_reports_empty_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """未提取到任何实现路由 → 判失败（防漏检）。"""
    empty = _stub_app(ConcurrentStableList(), ConcurrentStableList())
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: empty)
    errors = check_contracts.check_service("stub")
    assert any("未提取到任何实现路由" in message for message in errors)


@pytest.mark.kiwi_id(2227)
def test_check_service_reports_build_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用构建失败 → 报「应用构建失败」（不静默放过）。"""

    def _boom(service_key: str) -> object:
        raise RuntimeError("服务包缺失")

    monkeypatch.setattr(check_contracts, "build_app", _boom)
    errors = check_contracts.check_service("ghost")
    assert any("应用构建失败" in message for message in errors)


@pytest.mark.kiwi_id(2227)
def test_check_all_aggregates_and_main_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`check_all` 聚合明细；`main` 通过 0 / 失败 1。"""
    good = _stub_app(
        ConcurrentStableList(["/api/v1/a"]),
        ConcurrentStableList([_leaf("/api/v1/a", include_in_schema=True)]),
    )
    bad = _stub_app(ConcurrentStableList(), ConcurrentStableList([_leaf("/api/v1/b", include_in_schema=True)]))

    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: good)
    monkeypatch.setattr(check_contracts, "enabled_service_keys", lambda: ("a", "b"))
    assert len(check_contracts.check_all(ConcurrentStableList(["a", "b"]))) == 0
    assert check_contracts.main(ConcurrentStableList(["--service", "a"])) == 0

    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: bad)
    assert check_contracts.main(ConcurrentStableList(["--service", "b"])) == 1


def _contract_app(contract: ConcurrentStableDict[str, object]) -> SimpleNamespace:
    """构造桩应用：`openapi()` 返回完整契约样本，实现路由与契约一致。"""
    return SimpleNamespace(
        routes=ConcurrentStableList([_leaf("/api/v1/a", include_in_schema=True)]),
        openapi=lambda: contract,
    )


def _contract(
    operations: ConcurrentStableDict[str, object],
    schemas: ConcurrentStableDict[str, object],
) -> ConcurrentStableDict[str, object]:
    """构造含单路径与 `components.schemas` 的契约样本。"""
    return ConcurrentStableDict[str, object](
        {
            "paths": ConcurrentStableDict({"/api/v1/a": operations}),
            "components": ConcurrentStableDict({"schemas": schemas}),
        }
    )


def _json_operation(schema: object) -> ConcurrentStableDict[str, object]:
    """构造含 200 `application/json` 响应的 GET 操作。"""
    media = ConcurrentStableDict[str, object]({"schema": schema})
    response = ConcurrentStableDict[str, object]({"content": ConcurrentStableDict({"application/json": media})})
    return ConcurrentStableDict({"get": ConcurrentStableDict({"responses": ConcurrentStableDict({"200": response})})})


@pytest.mark.kiwi_id(2228)
def test_check_service_reports_empty_schema_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """公开契约存在空 schema 条目 → 报「空 schema 条目」（断言 C）。"""
    contract = _contract(
        ConcurrentStableDict[str, object](),
        ConcurrentStableDict({"Empty": ConcurrentStableDict[str, object]()}),
    )
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: _contract_app(contract))
    errors = check_contracts.check_service("stub")
    assert any("空 schema 条目" in message and "Empty" in message for message in errors)


@pytest.mark.kiwi_id(2228)
def test_check_service_reports_unresolvable_response_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功响应 schema 引用未解析 → 报「成功响应 schema 不可用」（断言 D）。"""
    contract = _contract(
        _json_operation(ConcurrentStableDict({"$ref": "#/components/schemas/Ghost"})),
        ConcurrentStableDict[str, object](),
    )
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: _contract_app(contract))
    errors = check_contracts.check_service("stub")
    assert any("成功响应 schema 不可用" in message and "/api/v1/a" in message for message in errors)


@pytest.mark.kiwi_id(2228)
def test_check_service_passes_when_response_schema_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功响应引用可解析且非空、无空 schema 条目 → 无违规；`main` 退出码 0。"""
    contract = _contract(
        _json_operation(ConcurrentStableDict({"$ref": "#/components/schemas/Ok"})),
        ConcurrentStableDict({"Ok": ConcurrentStableDict({"properties": ConcurrentStableDict({"x": "s"})})}),
    )
    monkeypatch.setattr(check_contracts, "build_app", lambda service_key: _contract_app(contract))
    assert list(check_contracts.check_service("stub")) == []
    assert check_contracts.main(ConcurrentStableList(["--service", "stub"])) == 0
