"""契约响应 schema 完整性判定测试（Kiwi 2228）：空 schema 条目 / 悬空引用 / 正常契约。"""

import pytest

import bms_core.services.service_contract as service_contract
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.services.service_contract import empty_schema_entries, response_schema_gaps


def _schema_entry(name: str) -> ConcurrentStableDict[str, object]:
    """构造一条正常（非空）schema 条目。"""
    return ConcurrentStableDict[str, object]({"name": name, "properties": ConcurrentStableDict({"x": "s"})})


def _contract(
    operations: object = None,
    schemas: object = None,
) -> ConcurrentStableDict[str, object]:
    """构造契约样本（缺省无路径、无 `components`）。"""
    contract: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if operations is not None:
        contract.set("paths", operations)
    if schemas is not None:
        contract.set("components", ConcurrentStableDict({"schemas": schemas}))
    return contract


def _json_response(schema: object, status: str = "200") -> ConcurrentStableDict[str, object]:
    """构造含 `application/json` 响应的操作对象。"""
    media = ConcurrentStableDict[str, object]({"schema": schema})
    response = ConcurrentStableDict[str, object]({"content": ConcurrentStableDict({"application/json": media})})
    return ConcurrentStableDict[str, object]({"responses": ConcurrentStableDict({status: response})})


def _paths(operation: object) -> ConcurrentStableDict[str, object]:
    """构造单路径多方法映射。"""
    return ConcurrentStableDict({"api/v1/x": ConcurrentStableDict({"post": operation})})


def _response_without_schema() -> ConcurrentStableDict[str, object]:
    """构造声明了 `application/json` 但未给 `schema` 的响应对象。"""
    return ConcurrentStableDict(
        {"content": ConcurrentStableDict({"application/json": ConcurrentStableDict[str, object]()})}
    )


@pytest.mark.kiwi_id(2228)
def test_empty_schema_entries_reports_and_allows_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    """断言 C：空对象条目被报出；白名单命中即通过。"""
    schemas = ConcurrentStableDict(
        {"Ok": _schema_entry("Ok"), "Bad": ConcurrentStableDict[str, object]()},
    )
    contract = _contract(schemas=schemas)
    assert list(empty_schema_entries(contract)) == ["Bad"]

    monkeypatch.setattr(service_contract, "EMPTY_SCHEMA_ALLOWLIST", ConcurrentStableSet({"Bad"}))
    assert list(empty_schema_entries(contract)) == []
    assert list(empty_schema_entries(_contract(schemas=ConcurrentStableDict({"Ok": _schema_entry("Ok")})))) == []


@pytest.mark.kiwi_id(2228)
def test_response_schema_gaps_accepts_resolvable_ref() -> None:
    """断言 D：成功响应引用可解析且非空 → 通过；非 2xx 与无 JSON 响应不判定。"""
    schemas = ConcurrentStableDict({"Ok": _schema_entry("Ok")})
    good = _contract(_paths(_json_response(ConcurrentStableDict({"$ref": "#/components/schemas/Ok"}))), schemas)
    assert list(response_schema_gaps(good)) == []

    no_content = _contract(
        _paths(ConcurrentStableDict({"responses": ConcurrentStableDict[str, object]()})),
        schemas,
    )
    assert list(response_schema_gaps(no_content)) == []

    non_success_only = _contract(
        _paths(
            ConcurrentStableDict(
                {
                    "responses": ConcurrentStableDict(
                        {"404": ConcurrentStableDict({"content": ConcurrentStableDict[str, object]()})}
                    )
                }
            )
        ),
        schemas,
    )
    assert list(response_schema_gaps(non_success_only)) == []

    media_without_schema = _contract(
        _paths(ConcurrentStableDict({"responses": ConcurrentStableDict({"200": _response_without_schema()})})),
        schemas,
    )
    assert list(response_schema_gaps(media_without_schema)) == []


@pytest.mark.kiwi_id(2228)
def test_response_schema_gaps_reports_dangling_and_empty_target() -> None:
    """断言 D：引用目标为空 / 引用未解析被报出；内联 schema（含空对象）不判定。"""
    schemas = ConcurrentStableDict({"Empty": ConcurrentStableDict[str, object]()})
    empty_target = _contract(
        _paths(_json_response(ConcurrentStableDict({"$ref": "#/components/schemas/Empty"}))), schemas
    )
    assert any("引用目标为空" in gap for gap in response_schema_gaps(empty_target))

    dangling = _contract(_paths(_json_response(ConcurrentStableDict({"$ref": "#/components/schemas/Ghost"}))), schemas)
    assert any("引用未解析" in gap for gap in response_schema_gaps(dangling))

    inline_empty = _contract(_paths(_json_response(ConcurrentStableDict[str, object]())), schemas)
    assert list(response_schema_gaps(inline_empty)) == []
