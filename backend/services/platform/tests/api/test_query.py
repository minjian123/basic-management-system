"""通用查询参数解析用例（`parse_id_list`，msg 06-7 协同）。"""

import pytest

from bms_core.core.exceptions import ParamError
from bms_platform.api.query import MAX_ID_FILTER, parse_id_list


def test_parse_id_list_normalizes_and_dedupes() -> None:
    """空值 / 空白 / 去重 / 保序。"""
    assert list(parse_id_list(None)) == []
    assert list(parse_id_list("")) == []
    assert list(parse_id_list(" , , ")) == []
    assert list(parse_id_list(" 3, 1 ,3, 2 ")) == [3, 1, 2]


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "1,x", "1.5"])
def test_parse_id_list_rejects_non_positive_integers(raw: str) -> None:
    """非正整数立即 10001。"""
    with pytest.raises(ParamError):
        parse_id_list(raw)


def test_parse_id_list_rejects_too_many_items() -> None:
    """超过单次上限立即 10001。"""
    raw = ",".join(str(value) for value in range(1, MAX_ID_FILTER + 2))
    with pytest.raises(ParamError):
        parse_id_list(raw)
