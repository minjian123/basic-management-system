"""手机号脱敏回接用例（Kiwi 2225）：口径委托基座 `phone` 策略纯函数后与回接前逐字节一致。"""

import pytest

from bms_core.captcha.base import mask_phone


@pytest.mark.kiwi_id(2225)
@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("13812345678", "138****5678"),
        ("12345678", "123****5678"),
        ("1234567", "123****"),
        ("1", "****"),
        ("", "****"),
    ],
)
def test_mask_phone_matches_previous_rule(phone: str, expected: str) -> None:
    """前 3 后 4 与长度退化口径不变（空串 / 单字符退化为纯掩码串，绝不通原值）。"""
    assert mask_phone(phone) == expected
