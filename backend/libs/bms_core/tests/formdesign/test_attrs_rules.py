"""字段属性归一与规则编译（Kiwi 2526）：必填 / 长度 / 范围 / 正则 / 选项集 + 六类拒收。"""

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import FormAttrInvalidError
from bms_core.formdesign.attrs import (
    MAX_PATTERN_LENGTH,
    FieldAttrs,
    compile_rules,
    dump_attrs,
    dump_attrs_config,
    normalize_attrs,
    parse_attrs_config,
    resolve_default,
    validate_attrs,
)

pytestmark = pytest.mark.kiwi_id(2526)

_OPTION_VALUES = ConcurrentStableFrozenList[str](("active", "disabled"))


def test_normalize_attrs_drops_unknown_and_keeps_rules() -> None:
    """未知键丢弃、非法规则种类过滤、`required` 与规则双通道合并。"""
    attrs = normalize_attrs(
        {
            "required": True,
            "placeholder": "请输入",
            "defaultValue": "active",
            "rules": [
                {"kind": "length", "min": 1, "max": 8},
                {"kind": "pattern", "pattern": "^[a-z]+$"},
                {"kind": "bogus"},
            ],
            "optionSetKey": "bms.user.status",
            "readonly": True,
            "unknownKey": 1,
        }
    )
    assert attrs.required is True
    assert attrs.placeholder == "请输入"
    assert [(rule.kind, rule.min, rule.max) for rule in attrs.rules] == [("length", 1.0, 8.0), ("pattern", None, None)]
    assert attrs.option_set_key == "bms.user.status"
    assert attrs.readonly is True


def test_attrs_roundtrip() -> None:
    """属性序列化 / 反序列化等值。"""
    attrs = normalize_attrs({"required": True, "rules": [{"kind": "range", "min": 1, "max": 5}]})
    assert parse_attrs_config(dump_attrs_config(attrs)) == attrs


def test_parse_attrs_config_tolerates_broken_json() -> None:
    """库内坏 JSON 回落空属性（渲染不白屏），不抛错。"""
    parsed = parse_attrs_config("{broken")
    assert parsed.required is False
    assert len(parsed.rules) == 0


def test_compile_rules_puts_required_first_and_adds_options() -> None:
    """规则编译：必填在首位、枚举类型自动补 `options`、规则里的 required 不重复。"""
    attrs = normalize_attrs({"required": True, "rules": [{"kind": "required"}, {"kind": "length", "min": 1}]})
    compiled = compile_rules(attrs, "option")
    assert [rule.kind for rule in compiled] == ["required", "length", "options"]


def test_resolve_default() -> None:
    """默认值取属性值（未配置为 None）。"""
    assert resolve_default(normalize_attrs({"defaultValue": "x"})) == "x"
    assert resolve_default(normalize_attrs({})) is None


def test_validate_attrs_accepts_valid_config() -> None:
    """合法属性通过并归一回写。"""
    attrs = validate_attrs(
        {"required": True, "optionSetKey": "bms.user.status", "defaultValue": "active"},
        field_type="option",
        is_option_registered=True,
        option_values=_OPTION_VALUES,
    )
    assert attrs.required is True


@pytest.mark.parametrize(
    ("raw", "field_type", "registered", "reason"),
    [
        ({"rules": [{"kind": "pattern", "pattern": "("}]}, "text", False, "非法正则"),
        ({"rules": [{"kind": "pattern", "pattern": "(a+)+"}]}, "text", False, "嵌套量词回溯风险"),
        ({"rules": [{"kind": "pattern", "pattern": "a" * (MAX_PATTERN_LENGTH + 1)}]}, "text", False, "正则超长"),
        ({"optionSetKey": None}, "option", False, "枚举字段缺选项集"),
        ({"optionSetKey": "bms.x.y"}, "text", True, "非枚举字段带选项集"),
        ({"optionSetKey": "bms.x.y"}, "option", False, "选项集未注册"),
        ({"optionSetKey": "bms.x.y", "defaultValue": "zzz"}, "option", True, "默认值越域"),
        ({"rules": [{"kind": "length", "min": 5, "max": 2}]}, "text", False, "下限大于上限"),
        ({"rules": [{"kind": "range"}]}, "text", False, "范围规则缺上下限"),
        ({"rules": [{"kind": "length", "min": -1}]}, "text", False, "长度下限为负"),
        ({"placeholder": "x" * 300}, "text", False, "提示超长"),
    ],
)
def test_validate_attrs_rejects(raw: object, field_type: str, registered: bool, reason: str) -> None:
    """十一类非法属性全部拒收（40408）。"""
    with pytest.raises(FormAttrInvalidError):
        validate_attrs(
            raw,
            field_type=field_type,
            is_option_registered=registered,
            option_values=_OPTION_VALUES,
        )


def test_validate_attrs_checks_default_against_domain() -> None:
    """默认值须落在值域内（多选逐项、长度 / 范围规则同样约束默认值）。"""
    with pytest.raises(FormAttrInvalidError):
        validate_attrs(
            {"optionSetKey": "bms.x.y", "defaultValue": ["active", "zzz"]},
            field_type="option_multi",
            is_option_registered=True,
            option_values=_OPTION_VALUES,
        )
    with pytest.raises(FormAttrInvalidError):
        validate_attrs(
            {"optionSetKey": "bms.x.y", "defaultValue": ["zzz"]},
            field_type="option_multi",
            is_option_registered=True,
            option_values=_OPTION_VALUES,
        )
    with pytest.raises(FormAttrInvalidError):
        validate_attrs(
            {"defaultValue": "abcdef", "rules": [{"kind": "length", "max": 3}]},
            field_type="text",
            is_option_registered=False,
            option_values=_OPTION_VALUES,
        )
    with pytest.raises(FormAttrInvalidError):
        validate_attrs(
            {"defaultValue": 99, "rules": [{"kind": "range", "max": 10}]},
            field_type="number",
            is_option_registered=False,
            option_values=_OPTION_VALUES,
        )


def test_dump_attrs_emits_camel_case_keys() -> None:
    """属性下发用前端既有 camelCase 键（与 `FieldRenderAttrs` 同形）。"""
    dumped = dump_attrs(normalize_attrs({"defaultValue": 1, "optionSetKey": "bms.a.b", "readonly": True}))
    assert dumped["defaultValue"] == 1
    assert dumped["optionSetKey"] == "bms.a.b"
    assert dumped["readonly"] is True


def test_normalize_attrs_accepts_scalar_and_non_mapping_forms() -> None:
    """`required` 认字符串 / 数值形态；规则参数认字符串数值；非映射输入回落空属性；`FieldAttrs` 原样返回。"""
    assert normalize_attrs({"required": "yes"}).required is True
    assert normalize_attrs({"required": 1}).required is True
    numeric_raw = cast("dict[str, object]", {"rules": [{"kind": "length", "min": "2", "max": "abc", "pattern": {}}]})
    numeric = normalize_attrs(numeric_raw)
    assert numeric.rules[0].min == 2.0
    assert numeric.rules[0].max is None
    kept_raw = cast("dict[str, object]", {"rules": [1, {"kind": "length", "max": 3}]})
    kept = normalize_attrs(kept_raw)
    assert [rule.kind for rule in kept.rules] == ["length"]
    original = FieldAttrs(required=True)
    assert normalize_attrs(original) is original
    assert normalize_attrs(12345).required is False
    assert normalize_attrs("not-a-mapping").required is False


def test_dump_attrs_emits_rule_message_widget_and_hidden() -> None:
    """规则自带文案 / 控件覆盖 / 隐藏标记一并下发（前端按需取用）。"""
    dumped = dump_attrs(
        normalize_attrs({"rules": [{"kind": "required", "message": "必填"}], "widget": "textarea", "hidden": True})
    )
    rules = dumped["rules"]
    assert isinstance(rules, list)
    assert rules[0]["message"] == "必填"
    assert dumped["widget"] == "textarea"
    assert dumped["hidden"] is True


def test_validate_attrs_rejects_pattern_default_and_range_edges() -> None:
    """正则规则空 pattern / 多选默认值非数组 / 默认值长度不足 / 默认值低于下限 均拒收。"""
    cases = (
        ({"rules": [{"kind": "pattern"}]}, "text"),
        ({"optionSetKey": "bms.x.y", "defaultValue": 5}, "option_multi"),
        ({"defaultValue": "ab", "rules": [{"kind": "length", "min": 3}]}, "text"),
        ({"defaultValue": 1, "rules": [{"kind": "range", "min": 5}]}, "number"),
    )
    for raw, field_type in cases:
        with pytest.raises(FormAttrInvalidError):
            validate_attrs(
                raw,
                field_type=field_type,
                is_option_registered=True,
                option_values=_OPTION_VALUES,
            )


def test_validate_attrs_accepts_in_domain_defaults() -> None:
    """默认值在值域内 / 长度下限满足 / 范围上限满足 均放行（只做越界拦截）。"""
    multi = validate_attrs(
        {"optionSetKey": "bms.x.y", "defaultValue": ["active"]},
        field_type="option_multi",
        is_option_registered=True,
        option_values=_OPTION_VALUES,
    )
    assert multi.default_value == ["active"]
    long_enough = validate_attrs(
        {"defaultValue": "abcd", "rules": [{"kind": "length", "min": 2}]},
        field_type="text",
        is_option_registered=False,
        option_values=_OPTION_VALUES,
    )
    assert long_enough.default_value == "abcd"
    in_range = validate_attrs(
        {"defaultValue": 5, "rules": [{"kind": "range", "min": 1, "max": 9}]},
        field_type="number",
        is_option_registered=False,
        option_values=_OPTION_VALUES,
    )
    assert in_range.default_value == 5


def test_normalize_attrs_treats_unparsable_rule_bounds_as_none() -> None:
    """规则上下限为不可解析形态（映射 / 列表）时按未配置处理。"""
    raw = cast("dict[str, object]", {"rules": [{"kind": "length", "min": {}, "max": []}]})
    attrs = normalize_attrs(raw)
    assert attrs.rules[0].min is None
    assert attrs.rules[0].max is None
