"""命名空间助手用例（04-6-1 / Kiwi 2399）：前缀派生 / 编码生成 / 断言限定 / 相对增量。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bms_core.testing import namespace as ns_module
from bms_core.testing.namespace import Namespace, assert_delta, assert_scoped, prefix_for, scoped

pytestmark = pytest.mark.kiwi_id(2399)


def test_prefix_shape_and_worker_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """前缀带 worker 位与 nodeid 摘要；同 nodeid 稳定、不同 nodeid 不同。"""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    first = prefix_for("tests/test_a.py::test_x")
    assert first.startswith("w0") and len(first) == 10
    assert first == prefix_for("tests/test_a.py::test_x")
    assert first != prefix_for("tests/test_a.py::test_y")

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    assert prefix_for("tests/test_a.py::test_x").startswith("w3")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw13")
    assert prefix_for("tests/test_a.py::test_x").startswith("w3")


def test_code_like_owns_and_invalid_inputs() -> None:
    """编码生成 / LIKE 模式 / 归属判断；非法前缀与后缀直接抛错（不静默截断）。"""
    ns = Namespace("w0a1b2c3d4")
    assert ns.code("acme") == "w0a1b2c3d4-acme"
    assert ns.like() == "w0a1b2c3d4%"
    assert ns.owns("w0a1b2c3d4-acme") is True
    assert ns.owns("acme") is False and ns.owns(None) is False
    assert repr(ns) == "Namespace('w0a1b2c3d4')"

    with pytest.raises(ValueError):
        Namespace("bad-prefix")
    with pytest.raises(ValueError):
        Namespace("w0" + "a" * 20)
    with pytest.raises(ValueError):
        ns.code("")
    with pytest.raises(ValueError):
        ns.code("Bad Suffix")


def test_scoped_appends_filter() -> None:
    """查询过滤：对语句追加 LIKE 条件。"""

    class _Column:
        def __init__(self) -> None:
            self.patterns: list[str] = []

        def like(self, pattern: str) -> str:
            self.patterns.append(pattern)
            return pattern

    class _Statement:
        def __init__(self) -> None:
            self.wheres: list[str] = []

        def where(self, condition: str) -> _Statement:
            self.wheres.append(condition)
            return self

    column = _Column()
    statement: Any = _Statement()
    ns = Namespace("w0a1b2c3d4")
    result = scoped(statement, column, ns)
    assert result.wheres == ["w0a1b2c3d4%"]
    assert column.patterns == ["w0a1b2c3d4%"]


def test_assert_scoped_and_delta() -> None:
    """断言限定：本命名空间数据通过，混入他人数据报错并提示写法；增量断言正负两例。"""
    ns = Namespace("w0a1b2c3d4")
    assert_scoped([{"code": ns.code("a")}, {"code": ns.code("b")}], ns)
    with pytest.raises(AssertionError, match="非本命名空间"):
        assert_scoped([{"code": "acme"}], ns)

    assert_delta(10, 11)
    with pytest.raises(AssertionError, match="计数增量不符"):
        assert_delta(10, 13)


def test_assert_scoped_supports_orm_rows() -> None:
    """断言限定同时支持 ORM 对象（属性取值）与字典。"""
    ns = Namespace("w0a1b2c3d4")

    class _Row:
        def __init__(self, code: str) -> None:
            self.code = code

    assert_scoped([_Row(ns.code("a"))], ns)
    with pytest.raises(AssertionError, match="非本命名空间"):
        assert_scoped([_Row("acme")], ns)


def test_for_test_records_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`for_test` 按 nodeid 生成命名空间，并把映射追加到 `.cache/test/namespace-map.jsonl`。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

    class _Node:
        nodeid = "tests/test_demo.py::test_x"

    class _Request:
        node = _Node()

    namespace = ns_module.for_test(_Request())  # type: ignore[arg-type]
    assert namespace.prefix == prefix_for("tests/test_demo.py::test_x")

    lines = (tmp_path / ".cache/test/namespace-map.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record == {"prefix": namespace.prefix, "nodeid": "tests/test_demo.py::test_x"}


def test_record_swallows_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """映射写失败不影响用例结论（排查辅助，不参与判定）。"""
    monkeypatch.chdir(tmp_path)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr(ns_module, "map_path", _boom)
    ns_module._record("w0a1b2c3d4", "tests/test_demo.py::test_x")
