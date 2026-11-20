"""表单动态校验占位实现（`Null*` 落点护栏：占位类必须落在专属 `null` / `*_null` 模块）。

**为什么单独成模块**：`tests/crosscut/test_null_migration.py` 要求所有 `Null*` 类都定义在
`null.py`（或 `*_null.py`）里，不混进业务模块——占位实现与真实实现混放会让「null 迁移」护栏失效，
也容易让人误以为 `validator.py` 里的占位就是生产默认行为。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_core.formdesign.validator import EMPTY_KEYS, BaseFormValidator, ValidationResult

__all__ = ["NullFormValidator"]


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
