"""契约版本解析测试（Kiwi 2163）：`contract_major` 合法 / 非法形态。"""

import pytest

from bms_core.core.version import contract_major


@pytest.mark.kiwi_id(2163)
def test_contract_major_parses_and_rejects() -> None:
    """主版本解析：三段 semver 取首段；非三段 / 带前缀后缀一律 None。"""
    assert contract_major("0.1.0") == 0
    assert contract_major("1.2.3") == 1
    assert contract_major("12.3.4") == 12
    assert contract_major("01.0.0") == 1
    assert contract_major("0.1") is None
    assert contract_major("1.0.0.1") is None
    assert contract_major("v1.0.0") is None
    assert contract_major("1.0.0-rc1") is None
    assert contract_major("") is None
