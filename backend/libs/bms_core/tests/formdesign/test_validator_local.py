"""动态校验契约与占位实现（Kiwi 2526）：占位恒通过 + 字段级错误结构。"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import pytest
from starlette.requests import Request

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
)
from bms_core.formdesign import validator as validator_module
from bms_core.formdesign.validator import (
    FieldError,
    ValidationResult,
    build_validation_error_payload,
)
from bms_core.formdesign.validator_null import NullFormValidator

pytestmark = pytest.mark.kiwi_id(2526)


async def test_null_validator_always_passes() -> None:
    """占位实现恒定通过（无配置时既有接口行为不变）。"""
    validator = NullFormValidator()
    result = await validator.validate("user", ConcurrentStableDict({"any": 1}))
    assert result.valid is True
    assert len(result.errors) == 0


def test_validation_result_validity_follows_errors() -> None:
    """`valid` 与 `errors` 恒一致。"""
    assert ValidationResult().valid is True
    failed = ValidationResult(errors=ConcurrentStableFrozenList((FieldError(field_key="name", rule="required"),)))
    assert failed.valid is False


def test_build_validation_error_payload_shape() -> None:
    """接口失败明细形态：`{errors: [{field_key, rule, message}]}`。"""
    errors_in = ConcurrentStableFrozenList((FieldError(field_key="name", rule="required", message="必填"),))
    payload = build_validation_error_payload(ValidationResult(errors=errors_in))
    errors = cast("ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]", payload["errors"])
    assert len(errors) == 1
    assert errors[0]["field_key"] == "name"
    assert errors[0]["rule"] == "required"


def test_validator_capability_key_and_placeholder_describe() -> None:
    """能力键由只读属性给出（与 `plugin_key` 同值）；占位实现的描述可读。"""
    validator = NullFormValidator()
    assert validator.key == "form_validator"
    assert validator.plugin_key == "form_validator"
    assert "恒定通过" in validator.describe()


def _resolve_to(validator: NullFormValidator) -> Callable[..., NullFormValidator]:
    """构造 `resolve_plugin` 替身（恒定返回给定实现）。

    Args:
        validator: 目标实现。

    Returns:
        Callable[..., NullFormValidator]: 替身函数。
    """

    def _resolve(*_args: object, **_kwargs: object) -> NullFormValidator:
        return validator

    return _resolve


def test_get_form_validator_resolves_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """按配置分区解析实现（`resolve_plugin` 结果原样返回）。"""
    validator = NullFormValidator()
    monkeypatch.setattr(validator_module, "resolve_plugin", _resolve_to(validator))
    settings = SimpleNamespace(form_validator=SimpleNamespace(provider="null"))
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    request = Request({"type": "http", "headers": [], "app": app})
    assert validator_module.get_form_validator(request) is validator
