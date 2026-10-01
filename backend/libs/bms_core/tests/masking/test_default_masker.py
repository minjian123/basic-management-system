"""脱敏基座真实实现用例（Kiwi 2212）：内置规则分派 / 自定义策略 / 明文揭示 fail-closed / 配置化 / 装配。"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

from bms_core.core import plugin as plugin_module
from bms_core.core.assembly import DefaultMaskerFactory, PlaceholderMaskerFactory
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BasePlaceholder
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import PluginRegistry
from bms_core.masking.base import MASK_STRATEGIES, BaseMasker, get_masker
from bms_core.masking.default import (
    BUILTIN_MASK_SPECS,
    DefaultMasker,
    MaskerOptions,
    mask_edges,
    mask_email,
)
from bms_core.masking.null import NullMasker
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.null import NullPermissionChecker


class _AllowChecker(BasePermissionChecker):
    """测试用允许实现：恒定持有权限码（**非**占位实现，模拟 RBAC 就绪后持 `data:plain`）。"""

    def check(self, code: str) -> bool:
        """恒定允许。

        Args:
            code: 权限码（本实现不校验）。

        Returns:
            bool: True。
        """
        return True


class _DenyChecker(BasePermissionChecker):
    """测试用拒绝实现：不持任何权限码（非占位实现）。"""

    def check(self, code: str) -> bool:
        """恒定拒绝。

        Args:
            code: 权限码（本实现不校验）。

        Returns:
            bool: False。
        """
        return False


def _emp_mask(value: str, mask_char: str) -> str:
    """测试用自定义策略：固定前缀 + 掩码。

    Args:
        value: 字段值（本策略不使用）。
        mask_char: 掩码字符。

    Returns:
        str: 自定义掩码串。
    """
    del value
    return f"EMP-{mask_char * 3}"


def _show_value(value: str, mask_char: str) -> str:
    """测试用自定义策略：原样返回（用于验证登记入口本身）。

    Args:
        value: 字段值。
        mask_char: 掩码字符（本策略不使用）。

    Returns:
        str: 原值。
    """
    del mask_char
    return value


def _masker(
    checker: BasePermissionChecker | None = None,
    mask_char: str = "*",
    rules: ConcurrentStableDict[str, str] | None = None,
) -> DefaultMasker:
    """构造真实掩码器（缺省注入占位权限检查器）。

    Args:
        checker: 权限检查器（缺省 `NullPermissionChecker`）。
        mask_char: 掩码字符。
        rules: 字段 → 策略映射。

    Returns:
        DefaultMasker: 掩码器实例。
    """
    return DefaultMasker(checker=checker or NullPermissionChecker(), mask_char=mask_char, rules=rules)


def _request(settings: Settings) -> Request:
    """构造最小请求替身（提供者只读 `app.state.settings`）。

    Args:
        settings: 应用配置。

    Returns:
        Request: 请求替身。
    """
    return cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))


@pytest.mark.kiwi_id(2212)
def test_inheritance_and_strategies() -> None:
    """继承链、插件实现名与策略常量（含扩展的 address）。"""
    assert issubclass(DefaultMasker, BaseMasker)
    assert issubclass(BaseMasker, BaseCapability)
    assert issubclass(BaseCapability, BaseObject)
    assert not issubclass(DefaultMasker, BasePlaceholder)
    assert BaseMasker.key == "masking"
    assert DefaultMasker.plugin_name == "default"
    assert MASK_STRATEGIES == ("phone", "id_card", "email", "bank_card", "name", "address", "custom")
    assert set(BUILTIN_MASK_SPECS) | {"email"} == set(MASK_STRATEGIES)


@pytest.mark.kiwi_id(2212)
@pytest.mark.parametrize(
    ("strategy", "raw", "expected"),
    [
        ("phone", "13812345678", "138****5678"),
        ("id_card", "110101199001011234", "110101********1234"),
        ("bank_card", "6222021234567890", "6222********7890"),
        ("name", "张三", "张*"),
        ("address", "北京市朝阳区某某路1号", "北京市朝阳区***"),
        ("email", "zhangsan@example.com", "z***@example.com"),
        ("custom", "EMP-0001", "***"),
    ],
)
def test_builtin_masks(strategy: str, raw: str, expected: str) -> None:
    """内置策略掩码结果符合规则清单示例。"""
    masker = _masker()
    masker.register("target", strategy)
    assert masker.mask("target", raw) == expected


@pytest.mark.kiwi_id(2212)
def test_length_fallback_and_boundaries() -> None:
    """长度不足退化、空串、None、非字符串与未注册字段的边界行为。"""
    masker = _masker()
    masker.register("phone", "phone")
    assert masker.mask("phone", "1234567") == "123****"
    assert masker.mask("phone", "1") == "****"
    assert masker.mask("phone", "") == "****"
    assert masker.mask("phone", None) is None
    assert masker.mask("phone", 13800001111) == "138****1111"
    assert masker.mask("unregistered", "13800001111") == "13800001111"

    # 星数固定：不随被掩码字符数变化（身份证 18 位仍是 8 星）
    masker.register("id_card", "id_card")
    assert masker.mask("id_card", "110101199001011234") == "110101********1234"


@pytest.mark.kiwi_id(2212)
def test_mask_pure_functions() -> None:
    """掩码纯函数（`mask_edges` / `mask_email`）的示例与退化。"""
    assert mask_edges("1234567", BUILTIN_MASK_SPECS["phone"]) == "123****"
    assert mask_edges("", BUILTIN_MASK_SPECS["phone"]) == "****"
    assert mask_edges("张三", BUILTIN_MASK_SPECS["name"], "#") == "张#"
    assert mask_email("@example.com") == "***@example.com"
    assert mask_email("abc") == "a***"
    assert mask_email("") == "***"


@pytest.mark.kiwi_id(2212)
def test_register_strategy_and_priority() -> None:
    """自定义策略注册生效；字段级注册 > 内置策略 > 未知策略兜底全掩码。"""
    masker = _masker()
    masker.register_strategy("emp", _emp_mask)
    assert masker.strategies() == ("emp",)
    masker.register("emp_no", "emp")
    assert masker.mask("emp_no", "12345") == "EMP-***"

    masker.register("phone", "phone")
    assert masker.mask("phone", "13812345678") == "138****5678"

    masker.register("mystery", "unknown_strategy")
    assert masker.mask("mystery", "value") == "***"


@pytest.mark.kiwi_id(2212)
def test_register_strategy_rejects_builtin_and_invalid() -> None:
    """自定义策略名与内置同名 / 格式非法一律拒（40002）。"""
    masker = _masker()
    with pytest.raises(PluginError):
        masker.register_strategy("phone", _show_value)
    with pytest.raises(PluginError):
        masker.register_strategy("Bad-Name", _show_value)
    with pytest.raises(PluginError):
        masker.register_strategy("Phone", _show_value)

    masker.register_strategy("emp", _show_value)
    assert masker.strategies() == ("emp",)


@pytest.mark.kiwi_id(2212)
def test_field_reregistration_last_wins() -> None:
    """同字段重复注册以最后一次为准（沿用既有 `register` 语义）。"""
    masker = _masker()
    masker.register("phone", "custom")
    masker.register("phone", "phone")
    assert [rule.strategy for rule in masker.rules()] == ["phone"]
    assert masker.mask("phone", "13812345678") == "138****5678"


@pytest.mark.kiwi_id(2212)
def test_check_plain_fail_closed_with_placeholder() -> None:
    """占位权限检查器一律按「无权限码」处理：`check_plain` 为 False 且输出掩码值。"""
    masker = _masker()
    masker.register("phone", "phone")
    assert masker.check_plain() is False
    assert masker.mask("phone", "13812345678") == "138****5678"


@pytest.mark.kiwi_id(2212)
def test_plain_allowed_and_denied_with_real_checker() -> None:
    """非占位检查器：持码放行明文、不持码输出掩码值。"""
    allowed = _masker(_AllowChecker())
    allowed.register("phone", "phone")
    assert allowed.check_plain() is True
    assert allowed.mask("phone", "13812345678") == "13812345678"

    denied = _masker(_DenyChecker())
    denied.register("phone", "phone")
    assert denied.check_plain() is False
    assert denied.mask("phone", "13812345678") == "138****5678"


@pytest.mark.kiwi_id(2212)
def test_reveal_mirrors_mask() -> None:
    """`reveal` 与 `mask` 对称：有权限原值、无权限掩码值（本期不做解密）。"""
    plain = _masker(_AllowChecker())
    hidden = _masker(_DenyChecker())
    for masker in (plain, hidden):
        masker.register("phone", "phone")
    assert plain.reveal("phone", "13812345678") == "13812345678"
    assert hidden.reveal("phone", "13812345678") == "138****5678"
    assert hidden.reveal("phone", "13812345678") == hidden.mask("phone", "13812345678")
    assert hidden.reveal("unregistered", "x") == "x"
    assert hidden.reveal("phone", None) is None


@pytest.mark.kiwi_id(2212)
def test_mask_char_and_rules_from_config() -> None:
    """掩码字符与规则表可配置（构造期注册）；掩码字符非单字符拒启。"""
    masker = _masker(mask_char="#", rules=ConcurrentStableDict({"phone": "phone"}))
    assert masker.masked_fields == frozenset({"phone"})
    assert masker.mask("phone", "13812345678") == "138####5678"

    with pytest.raises(PluginError):
        DefaultMasker(checker=NullPermissionChecker(), mask_char="**")


@pytest.mark.kiwi_id(2212)
def test_options_defaults_and_override() -> None:
    """选项解析：缺省回落与显式覆盖（空串视为未设置）。"""
    default = MaskerOptions.from_options(None)
    assert default.mask_char == "*"
    assert default.rules == {}

    assert MaskerOptions.from_options({"mask_char": ""}).mask_char == "*"

    parsed = MaskerOptions.from_options({"mask_char": "#", "rules": {"phone": "phone"}})
    assert parsed.mask_char == "#"
    assert parsed.rules == {"phone": "phone"}


@pytest.mark.kiwi_id(2212)
@pytest.mark.parametrize(
    "options",
    [
        ConcurrentStableDict({"mask_char": "**"}),
        ConcurrentStableDict({"mask_char": 1}),
        ConcurrentStableDict({"rules": ["phone"]}),
        ConcurrentStableDict({"rules": {"": "phone"}}),
        ConcurrentStableDict({"rules": {"phone": ""}}),
        ConcurrentStableDict({"rules": {"phone": 1}}),
    ],
)
def test_options_invalid(options: ConcurrentStableDict[str, object]) -> None:
    """选项非法一律拒启（40002，不静默降级）。"""
    with pytest.raises(PluginError):
        MaskerOptions.from_options(options)


@pytest.mark.kiwi_id(2212)
def test_factory_creates_implementations(monkeypatch: pytest.MonkeyPatch) -> None:
    """装配工厂：默认配置构造 `DefaultMasker`、provider 空构造 `NullMasker`。"""
    registry = PluginRegistry()
    registry.register("permission", "null", lambda: NullPermissionChecker())
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)

    masker = DefaultMaskerFactory(Settings(masking=PluginSelection(provider="default"))).create()
    assert isinstance(masker, DefaultMasker)
    assert not isinstance(masker, BasePlaceholder)

    fallback = PlaceholderMaskerFactory(Settings(masking=PluginSelection(provider=""))).create()
    assert isinstance(fallback, NullMasker)
    assert fallback.placeholder is True


@pytest.mark.kiwi_id(2212)
async def test_get_masker_resolves_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖提供者：默认配置解析 `DefaultMasker`、provider 空回落 `NullMasker`（依赖注入可解析）。"""
    registry = PluginRegistry()
    registry.register("masking", "default", lambda: _masker())
    registry.register("masking", "null", lambda: NullMasker(checker=NullPermissionChecker()))
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)

    real_settings = Settings(masking=PluginSelection(provider="default"))
    stream = cast("AsyncGenerator[BaseMasker]", get_masker(_request(real_settings)))
    assert isinstance(await anext(stream), DefaultMasker)
    await stream.aclose()

    fallback_settings = Settings(masking=PluginSelection(provider=""))
    stream = cast("AsyncGenerator[BaseMasker]", get_masker(_request(fallback_settings)))
    assert isinstance(await anext(stream), NullMasker)
    await stream.aclose()
