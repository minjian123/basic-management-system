"""表单动态校验能力域契约：端口 + 注册表 + 提供者（对齐《后端开发规范》§3.1「能力实现必须走基座」）。

- `FieldError`：字段级校验失败项（`field_key` + `rule` + `message`），接口层转 `data.errors[]`。
- `ValidationResult`：校验结果（`valid` + `errors`），只读值对象。
- `BaseFormValidator`：能力基类（`key = plugin_key = "form_validator"`），抽象
  `validate(form_code, values, *, locale)`。
- `get_form_validator`：依赖注入提供者（按 `[form_validator].provider` 解析）。

**为什么做成能力域而不直接写函数**：动态校验会被**各业务模块**的新增 / 编辑接口复用（本任务先接
`users`），后续可能按租户替换实现（条件化 / 按值域扩展）；走能力域可换实现只改配置、不改调用面，
且与《后端开发规范》「禁止各模块自研平行实现」一致。

**校验在 service 层强制执行**（不依赖前端）：业务模块在写库前调用，失败抛 `ParamError`（`10001`）
并带字段级明细。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
)
from bms_core.core.config import Settings
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, resolve_plugin
from bms_core.core.provider import BaseProvider

__all__ = [
    "FORM_VALIDATOR_PLUGIN_KEY",
    "BaseFormValidator",
    "FieldError",
    "NullFormValidator",
    "ValidationResult",
    "build_validation_error_payload",
    "get_form_validator",
]

FORM_VALIDATOR_PLUGIN_KEY = "form_validator"
"""能力键 / 插件键（插件名 `local` / `null`）。"""

EMPTY_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(())
"""空字段键清单（函数默认参数用模块级单例，避免默认值里构造）。"""


@dataclass(frozen=True)
class FieldError(BaseValueObject):
    """字段级校验失败项（文案由前端按 `rule` 做 i18n，后端不拼中文）。"""

    field_key: str
    """字段键。"""
    rule: str
    """规则种类（`required` / `length` / `range` / `pattern` / `options` / `type`）。"""
    message: str | None = None
    """后端补充说明（可选；通常为空，由前端取词）。"""


@dataclass(frozen=True)
class ValidationResult(BaseValueObject):
    """校验结果（`valid` 与 `errors` 恒一致：有错误即不通过）。"""

    errors: ConcurrentStableFrozenList[FieldError] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """字段级错误（空表示通过）。"""

    @property
    def valid(self) -> bool:
        """是否通过。

        Returns:
            bool: 无错误为 True。
        """
        return len(self.errors) == 0


class BaseFormValidator(BaseProvider, ABC):
    """表单动态校验契约：按表单码读取生效布局 / 属性并校验字段值。"""

    key: str = FORM_VALIDATOR_PLUGIN_KEY
    """能力键。"""
    plugin_key: str = FORM_VALIDATOR_PLUGIN_KEY
    """插件键（注册表查表用）。"""
    plugin_name: str = NULL_PLUGIN_NAME
    """实现名（`local` / `null`）。"""
    contract_version: str = DEFAULT_CONTRACT_VERSION
    """契约版本。"""

    @abstractmethod
    async def validate(
        self,
        form_code: str,
        values: ConcurrentStableDict[str, object],
        *,
        locale: str | None = None,
        skip_required_keys: ConcurrentStableFrozenList[str] = EMPTY_KEYS,
    ) -> ValidationResult:
        """校验一组字段值。

        Args:
            form_code: 表单标识（业务码）。
            values: 待校验值（字段键 → 值；缺键按「未提供」处理）。
            locale: 当前语言（属性提示文案与选项集标签回退用；None 表示不取）。
            skip_required_keys: 跳过必填校验的字段键（`editable=false` 的字段由权限侧拒绝写入）。

        Returns:
            ValidationResult: 校验结果。
        """


class NullFormValidator(BaseFormValidator):
    """占位实现（插件名 `null`）：恒定通过——无配置时保持既有接口行为不变。"""

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 说明文本。
        """
        return "表单动态校验占位实现（恒定通过）"

    async def validate(
        self,
        form_code: str,
        values: ConcurrentStableDict[str, object],
        *,
        locale: str | None = None,
        skip_required_keys: ConcurrentStableFrozenList[str] = EMPTY_KEYS,
    ) -> ValidationResult:
        """恒定通过（占位不校验）。

        Args:
            form_code: 表单标识（占位忽略）。
            values: 待校验值（占位忽略）。
            locale: 当前语言（占位忽略）。
            skip_required_keys: 跳过必填的字段键（占位忽略）。

        Returns:
            ValidationResult: 空错误结果。
        """
        del form_code, values, locale, skip_required_keys
        return ValidationResult()


def get_form_validator(request: Request) -> BaseFormValidator:
    """取应用级表单动态校验器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseFormValidator: 应用装配的校验器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseFormValidator",
        resolve_plugin(
            FORM_VALIDATOR_PLUGIN_KEY,
            settings.form_validator.provider,
            expected_version=BaseFormValidator.contract_version,
        ),
    )


def build_validation_error_payload(result: ValidationResult) -> ConcurrentStableDict[str, object]:
    """把校验结果转接口失败明细（`data.errors[]`）。

    Args:
        result: 校验结果。

    Returns:
        ConcurrentStableDict[str, object]: `{"errors": [{"field_key", "rule", "message"}]}`。
    """
    items: ConcurrentStableFrozenList[object] = ConcurrentStableFrozenList(
        tuple(
            ConcurrentStableDict({"field_key": error.field_key, "rule": error.rule, "message": error.message})
            for error in result.errors
        )
    )
    return ConcurrentStableDict({"errors": items})
