"""keyset 游标契约测试（Kiwi 1078）：编解码往返、规格指纹校验与非法游标拒绝。"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from bms_core.core.exceptions import ParamError
from bms_core.schemas.cursor import (
    CURSOR_VERSION,
    CursorPayload,
    decode_cursor,
    decode_cursor_for,
    encode_cursor,
    spec_fingerprint,
)
from bms_core.schemas.sorting import SortDirection, SortSpec


@pytest.mark.kiwi_id(1078)
def test_cursor_roundtrip_scalar_values() -> None:
    """标量键值（None / bool / int / float / str）编解码往返一致。"""
    sort = [
        SortSpec(field="rank", direction=SortDirection.ASC),
        SortSpec(field="name", direction=SortDirection.DESC),
    ]
    token = encode_cursor(sort, [None, "甲"], 42)
    payload = decode_cursor(token)
    assert isinstance(payload, CursorPayload)
    assert payload.specs == spec_fingerprint(sort)
    assert payload.values == (None, "甲")
    assert payload.item_id == 42
    assert payload.matches(sort) is True


@pytest.mark.kiwi_id(1078)
def test_cursor_roundtrip_temporal_values() -> None:
    """时间类键值带类型标记往返（datetime / date 还原为原类型）。"""
    sort = [SortSpec(field="created_at", direction=SortDirection.DESC)]
    moment = datetime(2026, 9, 22, 12, 30, 45)
    token = encode_cursor(sort, [moment], 7)
    assert decode_cursor(token).values == (moment,)

    day = date(2026, 9, 22)
    day_token = encode_cursor(sort, [day], 8)
    assert decode_cursor(day_token).values == (day,)


@pytest.mark.kiwi_id(1078)
def test_cursor_rejects_unsupported_value_type() -> None:
    """不支持的键值类型（如 `Decimal`）明确拒绝，不静默降级。"""
    sort = [SortSpec(field="amount", direction=SortDirection.ASC)]
    with pytest.raises(ParamError):
        encode_cursor(sort, [Decimal("1.23")], 1)


@pytest.mark.kiwi_id(1078)
@pytest.mark.parametrize(
    "token",
    [
        "not-a-cursor",
        "====",
    ],
)
def test_cursor_rejects_malformed_token(token: str) -> None:
    """编码 / JSON 非法一律 `ParamError`。"""
    with pytest.raises(ParamError):
        decode_cursor(token)


@pytest.mark.kiwi_id(1078)
def test_cursor_rejects_version_and_shape_errors() -> None:
    """载荷版本不符 / 形态不完整 / 排序规格非法 → `ParamError`。"""
    import base64
    import json

    def _encode(payload: dict[str, object]) -> str:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION + 1, "specs": [], "values": [], "id": 1}))
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [], "values": [1], "id": 1}))
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [["rank", "sideways"]], "values": [1], "id": 1}))
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [["rank"]], "values": [1], "id": 1}))
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [["rank", "asc"]], "values": [{"x": 1}], "id": 1}))


@pytest.mark.kiwi_id(1078)
def test_decode_cursor_for_rejects_spec_mismatch() -> None:
    """游标规格指纹与本次生效排序不一致 → `ParamError`（防跨排序复用游标）。"""
    token = encode_cursor([SortSpec(field="rank", direction=SortDirection.ASC)], [1], 1)
    assert decode_cursor_for(token, [SortSpec(field="rank", direction=SortDirection.ASC)]).item_id == 1
    with pytest.raises(ParamError):
        decode_cursor_for(token, [SortSpec(field="rank", direction=SortDirection.DESC)])
    with pytest.raises(ParamError):
        decode_cursor_for(token, [SortSpec(field="name", direction=SortDirection.ASC)])


@pytest.mark.kiwi_id(1078)
def test_cursor_rejects_non_object_and_bad_value_markers() -> None:
    """载荷非对象 / 规格项长度错 / 时间标记非法 / 值类型非法 → `ParamError`。"""
    import base64
    import json

    def _encode(raw: object) -> str:
        text = json.dumps(raw, ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(text).decode("ascii").rstrip("=")

    with pytest.raises(ParamError):
        decode_cursor(_encode(["not", "an", "object"]))
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [["rank"]], "values": [1], "id": 1}))
    with pytest.raises(ParamError):
        decode_cursor(
            _encode(
                {
                    "version": CURSOR_VERSION,
                    "specs": [["created_at", "asc"]],
                    "values": [{"__type__": "unknown", "value": "x"}],
                    "id": 1,
                }
            )
        )
    with pytest.raises(ParamError):
        decode_cursor(
            _encode(
                {
                    "version": CURSOR_VERSION,
                    "specs": [["created_at", "asc"]],
                    "values": [{"__type__": "datetime", "value": "not-a-date"}],
                    "id": 1,
                }
            )
        )
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [["rank", "asc"]], "values": [[1, 2]], "id": 1}))


@pytest.mark.kiwi_id(1078)
def test_cursor_rejects_incomplete_payload_and_non_list_spec() -> None:
    """载荷缺字段（id 非整数）与规格项非列表 → `ParamError`。"""
    import base64
    import json

    def _encode(raw: object) -> str:
        text = json.dumps(raw, ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(text).decode("ascii").rstrip("=")

    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": [], "values": [], "id": "1"}))
    with pytest.raises(ParamError):
        decode_cursor(_encode({"version": CURSOR_VERSION, "specs": ["rank"], "values": [1], "id": 1}))
