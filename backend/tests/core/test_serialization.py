"""稳定序列化测试（Kiwi 14）。"""

import pytest

from app.core.serialization import stable_json_dumps, stable_json_loads


@pytest.mark.kiwi_id(14)
def test_stable_json_dumps() -> None:
    """稳定 JSON：键排序、中文不转义、不可序列化值降级 str。"""
    assert stable_json_dumps({"b": 1, "a": "中"}) == '{"a": "中", "b": 1}'
    assert stable_json_dumps({"b": 1, "a": 2}, sort_keys=False) == '{"b": 1, "a": 2}'
    assert "<object" in stable_json_dumps({"x": object()})


@pytest.mark.kiwi_id(14)
def test_stable_json_loads() -> None:
    """反序列化：str 与 bytes 均支持。"""
    assert stable_json_loads('{"a": 1}') == {"a": 1}
    assert stable_json_loads(b'{"a": 1}') == {"a": 1}
