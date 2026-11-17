"""表单字段属性领域纯函数：属性归一 / 规则编译 / 默认值 / 合法性校验（框架无关、无 IO）。

**为什么字段属性单独一张表一层函数**（任务 10_01 决策 16）：需求 08-2 要求「必填 / 默认值 / 提示 /
校验规则 / 组件类型切换 / 选项集来源 / 只读 / 隐藏」可在线调整，而概要 §4 的表清单只给了布局与自建
字段两张表——平台字段的属性没有落点。单列 `sys_form_field_attr` + 本模块，使「只改属性不动布局」
的语义清晰，且三级属性与三级布局**同层同源**（选了哪层布局就用哪层属性）。

**规则编译与校验分离**：本模块只把声明式属性（`FieldRule`）编译成可执行规则集，实际求值在
`formdesign/validator.py` 的 `LocalFormValidator`；两边共用同一份 `CompiledRule`，保证「前端声明什么、
后端校验什么」不走样。
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import FormAttrInvalidError
from bms_core.core.objects import BaseValueObject
from bms_core.core.serialization import normalize_collections

__all__ = [
    "COMPILED_RULE_KINDS",
    "FIELD_RULE_KINDS",
    "MAX_PATTERN_LENGTH",
    "MAX_PLACEHOLDER_LENGTH",
    "CompiledRule",
    "FieldAttrs",
    "FieldRule",
    "compile_rules",
    "dump_attrs",
    "normalize_attrs",
    "parse_attrs_config",
    "resolve_default",
    "validate_attrs",
]

FIELD_RULE_KINDS: ConcurrentStableList[str] = ConcurrentStableList(
    ("required", "length", "range", "pattern", "options")
)
"""规则种类白名单（与前端 `FieldRule.kind` 同值）。"""

COMPILED_RULE_KINDS: ConcurrentStableList[str] = ConcurrentStableList(FIELD_RULE_KINDS)
"""可编译规则种类（与 `FIELD_RULE_KINDS` 相同；分列常量便于将来编译期收窄）。"""

MAX_PATTERN_LENGTH = 512
"""正则最大长度（超长正则拒收，防编译开销与误配）。"""

MAX_PLACEHOLDER_LENGTH = 255
"""提示文案最大长度。"""

_NESTED_QUANTIFIER_RE = re.compile(r"\([^()]*[+*][^()]*\)[+*{]")
"""嵌套量词探测（`(a+)+` / `(a*)*` 等回溯爆炸写法）。"""


@dataclass(frozen=True)
class FieldRule(BaseValueObject):
    """字段校验规则（声明式；与前端 `FieldRule` 同形）。"""

    kind: str
    """规则种类：`required` / `length` / `range` / `pattern` / `options`。"""
    min: float | None = None
    """长度或数值下限。"""
    max: float | None = None
    """长度或数值上限。"""
    pattern: str | None = None
    """正则（`pattern` 规则）。"""
    message: str | None = None
    """自定义错误文案（缺省按规则种类由前端 i18n 取词）。"""


@dataclass(frozen=True)
class FieldAttrs(BaseValueObject):
    """字段渲染属性（后端可省略；省略项按缺省）。"""

    required: bool = False
    """是否必填（字段权限 `required` 可覆盖为更严）。"""
    placeholder: str = ""
    """占位提示。"""
    default_value: object = None
    """默认值（记录未提供该字段值时使用）。"""
    rules: ConcurrentStableFrozenList[FieldRule] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """校验规则（声明式）。"""
    option_set_key: str | None = None
    """选项集标识（仅 `option` / `option_multi` 消费）。"""
    widget: str | None = None
    """控件形态覆盖（未登记或 `plain` 时回退字段类型默认形态）。"""
    readonly: bool = False
    """只读（编辑态亦只读）。"""
    hidden: bool = False
    """隐藏（布局引用但默认不渲染）。"""


@dataclass(frozen=True)
class CompiledRule(BaseValueObject):
    """编译后的可执行规则（校验器消费）。"""

    kind: str
    """规则种类。"""
    min: float | None = None
    """下限。"""
    max: float | None = None
    """上限。"""
    pattern: str | None = None
    """正则源码。"""
    message: str | None = None
    """自定义文案。"""


def _as_bool(value: object, fallback: bool = False) -> bool:
    """把 JSON 值归一为布尔。

    Args:
        value: 原始值。
        fallback: 不可解析时的回落值。

    Returns:
        bool: 归一后的布尔。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, int | float):
        return bool(value)
    return fallback


def _as_optional_str(value: object) -> str | None:
    """把 JSON 值归一为非空字符串或 None。

    Args:
        value: 原始值。

    Returns:
        str | None: 去空白后的字符串；空 / 非字符串返回 None。
    """
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _as_optional_number(value: object) -> float | None:
    """把 JSON 值归一为数值或 None。

    Args:
        value: 原始值。

    Returns:
        float | None: 数值；布尔 / 不可解析返回 None。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _normalize_rules(raw: object) -> ConcurrentStableFrozenList[FieldRule]:
    """归一规则列表（按 `kind` 白名单过滤，未知键丢弃）。

    Args:
        raw: 原始规则列表。

    Returns:
        ConcurrentStableFrozenList[FieldRule]: 归一后的规则（插入序）。
    """
    rules: ConcurrentStableList[FieldRule] = ConcurrentStableList()
    if not isinstance(raw, list):
        return ConcurrentStableFrozenList(())
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        record = ConcurrentStableDict(cast("Mapping[str, object]", item))
        kind = _as_optional_str(record.get("kind"))
        if kind is None or kind not in FIELD_RULE_KINDS:
            continue
        rules.add(
            FieldRule(
                kind=kind,
                min=_as_optional_number(record.get("min")),
                max=_as_optional_number(record.get("max")),
                pattern=_as_optional_str(record.get("pattern")),
                message=_as_optional_str(record.get("message")),
            )
        )
    return ConcurrentStableFrozenList(rules)


def normalize_attrs(raw: object) -> FieldAttrs:
    """归一字段属性（缺省项补空、未知键丢弃、规则按白名单过滤）。

    Args:
        raw: 原始属性（字典或 `FieldAttrs`）。

    Returns:
        FieldAttrs: 归一后的属性。
    """
    if isinstance(raw, FieldAttrs):
        return raw
    if not isinstance(raw, Mapping):
        return FieldAttrs()
    record = ConcurrentStableDict(raw)
    rules = _normalize_rules(record.get("rules"))
    required = _as_bool(record.get("required"))
    if not required:
        # `required` 也可能只以规则形式出现：两条路径都认，合并成一个布尔
        required = any(rule.kind == "required" for rule in rules)
    return FieldAttrs(
        required=required,
        placeholder=_as_optional_str(record.get("placeholder")) or "",
        default_value=record.get("defaultValue") if "defaultValue" in record else record.get("default_value"),
        rules=rules,
        option_set_key=_as_optional_str(record.get("optionSetKey")) or _as_optional_str(record.get("option_set_key")),
        widget=_as_optional_str(record.get("widget")),
        readonly=_as_bool(record.get("readonly")),
        hidden=_as_bool(record.get("hidden")),
    )


def dump_attrs(attrs: FieldAttrs) -> ConcurrentStableDict[str, object]:
    """属性 → `attrs` 配置字典（写库与契约下发同形；键用前端既有 camelCase）。

    Args:
        attrs: 字段属性。

    Returns:
        ConcurrentStableDict[str, object]: 可 JSON 序列化的属性字典（值全为内置容器）。
    """
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if attrs.required:
        result.set("required", True)
    if attrs.placeholder != "":
        result.set("placeholder", attrs.placeholder)
    if attrs.default_value is not None:
        result.set("defaultValue", attrs.default_value)
    if len(attrs.rules) > 0:
        rule_list: ConcurrentStableList[object] = ConcurrentStableList()
        for rule in attrs.rules:
            item: ConcurrentStableDict[str, object] = ConcurrentStableDict({"kind": rule.kind})
            if rule.min is not None:
                item.set("min", rule.min)
            if rule.max is not None:
                item.set("max", rule.max)
            if rule.pattern is not None:
                item.set("pattern", rule.pattern)
            if rule.message is not None:
                item.set("message", rule.message)
            rule_list.add(item)
        result.set("rules", rule_list)
    if attrs.option_set_key is not None:
        result.set("optionSetKey", attrs.option_set_key)
    if attrs.widget is not None:
        result.set("widget", attrs.widget)
    if attrs.readonly:
        result.set("readonly", True)
    if attrs.hidden:
        result.set("hidden", True)
    return ConcurrentStableDict(cast("dict[str, object]", normalize_collections(result)))


def parse_attrs_config(raw: str) -> FieldAttrs:
    """解析库里存的 `attrs` JSON 文本并归一。

    Args:
        raw: JSON 文本。

    Returns:
        FieldAttrs: 归一后的属性（JSON 非法时回落空属性：库内损坏不阻断渲染）。

    Raises:
        FormAttrInvalidError: 不抛——本函数对损坏数据容错（渲染路径不因一条坏属性白屏），
            写路径的非法输入由 `validate_attrs` 在保存期拦截。
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return FieldAttrs()
    return normalize_attrs(parsed)


def dump_attrs_config(attrs: FieldAttrs) -> str:
    """序列化属性为 `attrs` JSON 文本（写库用）。

    Args:
        attrs: 字段属性。

    Returns:
        str: JSON 文本（`ensure_ascii=False`，紧凑分隔）。
    """
    return json.dumps(normalize_collections(dump_attrs(attrs)), ensure_ascii=False, separators=(",", ":"))


def compile_rules(attrs: FieldAttrs, field_type: str) -> ConcurrentStableFrozenList[CompiledRule]:
    """属性 → 可执行规则集（`required` 合并显式规则；枚举类型必有 `options` 规则）。

    Args:
        attrs: 字段属性。
        field_type: 字段类型（用于判断是否枚举类型）。

    Returns:
        ConcurrentStableFrozenList[CompiledRule]: 规则集（`required` 恒在首位）。
    """
    compiled: ConcurrentStableList[CompiledRule] = ConcurrentStableList()
    if attrs.required:
        compiled.add(CompiledRule(kind="required"))
    for rule in attrs.rules:
        if rule.kind == "required":
            # 已在首部按布尔合并，避免规则列表里再塞一条必填
            continue
        compiled.add(
            CompiledRule(
                kind=rule.kind,
                min=rule.min,
                max=rule.max,
                pattern=rule.pattern,
                message=rule.message,
            )
        )
    has_options_rule = any(item.kind == "options" for item in compiled)
    if field_type in ("option", "option_multi") and not has_options_rule:
        compiled.add(CompiledRule(kind="options"))
    return ConcurrentStableFrozenList(compiled)


def resolve_default(attrs: FieldAttrs) -> object:
    """取默认值（记录未提供该字段值时使用）。

    Args:
        attrs: 字段属性。

    Returns:
        object: 默认值（未配置返回 None）。
    """
    return attrs.default_value


def validate_attrs(
    raw: object,
    *,
    field_type: str,
    is_option_registered: bool,
    option_values: ConcurrentStableFrozenList[str],
) -> FieldAttrs:
    """校验并归一属性（保存期；非法即抛 `40408`）。

    Args:
        raw: 原始属性。
        field_type: 字段类型（枚举类型必配选项集）。
        is_option_registered: 选项集标识是否已在注册表登记。
        option_values: 选项集取值（默认值越域判定用；空表示不判定）。

    Returns:
        FieldAttrs: 归一后的属性。

    Raises:
        FormAttrInvalidError: 提示过长 / 长度或范围参数非法 / 正则非法或过长 / 正则回溯风险 /
            选项集标识缺失或未注册 / 非枚举类型带选项集 / 默认值不在值域内（40408）。
    """
    attrs = normalize_attrs(raw)
    if len(attrs.placeholder) > MAX_PLACEHOLDER_LENGTH:
        raise FormAttrInvalidError(f"提示文案超长（≤ {MAX_PLACEHOLDER_LENGTH}）：{len(attrs.placeholder)}")
    for rule in attrs.rules:
        if rule.kind in ("length", "range"):
            if rule.min is None and rule.max is None:
                raise FormAttrInvalidError(f"规则缺少上下限：{rule.kind}")
            if rule.min is not None and rule.min < 0:
                raise FormAttrInvalidError(f"规则下限不得为负：{rule.kind}")
            if rule.min is not None and rule.max is not None and rule.min > rule.max:
                raise FormAttrInvalidError(f"规则下限大于上限：{rule.kind}")
        if rule.kind == "pattern":
            pattern = rule.pattern
            if pattern is None or pattern == "":
                raise FormAttrInvalidError("正则规则缺少 pattern")
            if len(pattern) > MAX_PATTERN_LENGTH:
                raise FormAttrInvalidError(f"正则超长（≤ {MAX_PATTERN_LENGTH}）：{len(pattern)}")
            if _NESTED_QUANTIFIER_RE.search(pattern) is not None:
                raise FormAttrInvalidError(f"正则存在嵌套量词回溯风险：{pattern}")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise FormAttrInvalidError(f"正则非法：{exc}") from exc
    is_option_type = field_type in ("option", "option_multi")
    if is_option_type:
        if attrs.option_set_key is None:
            raise FormAttrInvalidError(f"枚举字段必须配置选项集来源：{field_type}")
        if not is_option_registered:
            raise FormAttrInvalidError(f"选项集标识未注册：{attrs.option_set_key}")
    elif attrs.option_set_key is not None:
        raise FormAttrInvalidError(f"非枚举字段不得配置选项集来源：{field_type}")
    default_value = attrs.default_value
    if default_value is not None:
        if is_option_type and len(option_values) > 0:
            if field_type == "option":
                if not isinstance(default_value, str) or default_value not in option_values:
                    raise FormAttrInvalidError(f"默认值不在选项集值域内：{default_value!r}")
            else:
                if not isinstance(default_value, list):
                    raise FormAttrInvalidError("多选默认值须为数组")
                members = ConcurrentStableList(str(item) for item in default_value)
                for item in members:
                    if item not in option_values:
                        raise FormAttrInvalidError(f"默认值不在选项集值域内：{item!r}")
        length_rule = next((rule for rule in attrs.rules if rule.kind == "length"), None)
        if length_rule is not None and isinstance(default_value, str):
            size = len(default_value)
            if length_rule.min is not None and size < length_rule.min:
                raise FormAttrInvalidError(f"默认值长度不足：{size} < {length_rule.min}")
            if length_rule.max is not None and size > length_rule.max:
                raise FormAttrInvalidError(f"默认值长度越界：{size} > {length_rule.max}")
        range_rule = next((rule for rule in attrs.rules if rule.kind == "range"), None)
        if range_rule is not None and isinstance(default_value, int | float) and not isinstance(default_value, bool):
            number = float(default_value)
            if range_rule.min is not None and number < range_rule.min:
                raise FormAttrInvalidError(f"默认值低于下限：{number} < {range_rule.min}")
            if range_rule.max is not None and number > range_rule.max:
                raise FormAttrInvalidError(f"默认值高于上限：{number} > {range_rule.max}")
    return attrs
