"""动态校验契约与占位实现（Kiwi 2526）：占位恒通过 + 字段级错误结构。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.formdesign.validator import (
    FieldError,
    NullFormValidator,
    ValidationResult,
    build_validation_error_payload,
)

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
    failed = ValidationResult(errors=(FieldError(field_key="name", rule="required"),))
    assert failed.valid is False


def test_build_validation_error_payload_shape() -> None:
    """接口失败明细形态：`{errors: [{field_key, rule, message}]}`。"""
    payload = build_validation_error_payload(
        ValidationResult(errors=(FieldError(field_key="name", rule="required", message="必填"),))
    )
    errors = payload["errors"]
    assert len(errors) == 1
    assert errors[0]["field_key"] == "name"
    assert errors[0]["rule"] == "required"


del pytest
