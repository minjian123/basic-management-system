"""帮助锚点 `help_key` 格式 / 形状 / 归一（08_01；Kiwi 2520）。

被测对象是**唯一校验实现** `bms_core/help/anchors.py`：五段冒号式、按节点类型的非空段位置、
字符集 / 长度、空值归一与产品段约束。纯函数，不触库。
"""

import pytest

from bms_core.core.exceptions import MenuHelpKeyInvalidError
from bms_core.help.anchors import (
    HELP_KEY_MAX_LENGTH,
    HELP_KEY_MAX_SEGMENT_LENGTH,
    HelpAnchorKind,
    help_key_segment,
    help_key_segments,
    normalize_help_key,
    validate_help_key,
)


@pytest.mark.kiwi_id(2520)
def test_normalize_help_key() -> None:
    """空值语义：None 原样、空串 / 纯空白归一为 None、正常值去首尾空白。"""
    assert normalize_help_key(None) is None
    assert normalize_help_key("") is None
    assert normalize_help_key("   ") is None
    assert normalize_help_key("  platform:platform::: ") == "platform:platform:::"


@pytest.mark.kiwi_id(2520)
def test_valid_shapes_for_every_kind() -> None:
    """五类节点各自接受本级形状（本级段非空、右侧留空）。"""
    assert validate_help_key("platform:platform:::", kind=HelpAnchorKind.MENU) == "platform:platform:::"
    assert validate_help_key("platform:platform:user::", kind=HelpAnchorKind.FORM) == "platform:platform:user::"
    assert (
        validate_help_key("platform:platform:user:username:", kind=HelpAnchorKind.FIELD)
        == "platform:platform:user:username:"
    )
    assert (
        validate_help_key("platform:platform:user::create", kind=HelpAnchorKind.BUTTON)
        == "platform:platform:user::create"
    )
    assert validate_help_key("platform::::create", kind=HelpAnchorKind.ACTION) == "platform::::create"


@pytest.mark.kiwi_id(2520)
def test_none_passes_through_as_unregistered() -> None:
    """未登记（None / 空串）不报错，返回 None。"""
    assert validate_help_key(None, kind=HelpAnchorKind.MENU) is None
    assert validate_help_key("  ", kind=HelpAnchorKind.FIELD) is None


@pytest.mark.kiwi_id(2520)
def test_segments_and_single_segment_accessor() -> None:
    """分段读取：保留下标与空段；越界与段数错误均报 40211。"""
    segments = help_key_segments("platform:platform:user::create")
    assert segments.to_list() == ["platform", "platform", "user", "", "create"]
    assert help_key_segment("platform:platform:user::create", 3) is None
    assert help_key_segment("platform:platform:user::create", 4) == "create"
    with pytest.raises(MenuHelpKeyInvalidError):
        help_key_segment("platform:platform:user::create", 5)
    with pytest.raises(MenuHelpKeyInvalidError):
        help_key_segment("platform:platform:user::create", -1)
    with pytest.raises(MenuHelpKeyInvalidError):
        help_key_segments("platform:platform")


@pytest.mark.kiwi_id(2520)
def test_rejects_invalid_segment_count() -> None:
    """段数不是五段即拒。"""
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        validate_help_key("platform:platform", kind=HelpAnchorKind.MENU)
    assert "段数" in str(exc.value)


@pytest.mark.kiwi_id(2520)
def test_rejects_segment_charset_and_length() -> None:
    """非空段字符集 / 单段长度非法即拒。"""
    with pytest.raises(MenuHelpKeyInvalidError) as charset:
        validate_help_key("Platform:platform:::", kind=HelpAnchorKind.MENU)
    assert "格式非法" in str(charset.value)
    with pytest.raises(MenuHelpKeyInvalidError) as long_segment:
        validate_help_key(f"platform:{'a' * (HELP_KEY_MAX_SEGMENT_LENGTH + 1)}:::", kind=HelpAnchorKind.MENU)
    assert "超长" in str(long_segment.value)


@pytest.mark.kiwi_id(2520)
def test_rejects_overall_length() -> None:
    """整串超过 255 字符即拒（即使每段都在 64 以内）。"""
    value = ":".join(["platform"] + ["a" * 64] * 3 + ["b" * 64])
    assert len(value) > HELP_KEY_MAX_LENGTH
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        validate_help_key(value, kind=HelpAnchorKind.FIELD)
    assert "超长" in str(exc.value)


@pytest.mark.kiwi_id(2520)
def test_rejects_shape_mismatch() -> None:
    """形状与节点类型不符即拒（如字段级键塞进菜单）。"""
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        validate_help_key("platform:platform:user:username:", kind=HelpAnchorKind.MENU)
    assert "形状非法" in str(exc.value)


@pytest.mark.kiwi_id(2520)
def test_declaring_product_must_match() -> None:
    """装载声明的首段必须等于声明方产品。"""
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        validate_help_key("biz:biz:::", kind=HelpAnchorKind.MENU, declaring_product="platform")
    assert "与声明方不一致" in str(exc.value)
    assert validate_help_key("biz:biz:::", kind=HelpAnchorKind.MENU, declaring_product="biz") == "biz:biz:::"


@pytest.mark.kiwi_id(2520)
def test_action_product_segment_must_be_platform() -> None:
    """动作码是全局动词兜底，产品段只允许 platform。"""
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        validate_help_key("biz::::create", kind=HelpAnchorKind.ACTION, declaring_product="biz")
    assert "platform" in str(exc.value)
