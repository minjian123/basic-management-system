"""code_validator 能力域缺省实现（Null Object）：恒定通过、诊断为空，不连库、不解析代码。

- `NullCodeValidator`：`validate_sql` 固定返回通过（诊断 / 字段清单 / 预览行为空、耗时 0、未截断）——
  不连从库、不解析 SQL、不校验白名单；`validate_expression` 固定返回通过（诊断为空）——不解析表达式、
  不校验字段与变量。
"""

from app.codecheck.base import (
    BaseCodeValidator,
    ExpressionContext,
    ExpressionValidationResult,
    SqlValidationResult,
)
from app.core.capability import BaseNullObject

__all__ = ["NullCodeValidator"]


class NullCodeValidator(BaseCodeValidator, BaseNullObject):
    """占位代码校验：两方法恒定通过（不连从库、不解析、无副作用）。"""

    async def validate_sql(self, sql: str, *, datasource: str | None = None) -> SqlValidationResult:
        """校验 SQL 并做只读试算（占位恒定通过）。

        Args:
            sql: SQL 文本（占位忽略）。
            datasource: 目标数据源标识（占位忽略）。

        Returns:
            SqlValidationResult: 占位结果（诊断 / 字段清单 / 预览行为空、耗时 0、未截断）。
        """
        return SqlValidationResult()

    async def validate_expression(
        self,
        expr: str,
        *,
        context: ExpressionContext | None = None,
    ) -> ExpressionValidationResult:
        """校验表达式（占位恒定通过）。

        Args:
            expr: 表达式文本（占位忽略）。
            context: 校验上下文（占位忽略）。

        Returns:
            ExpressionValidationResult: 占位结果（诊断为空）。
        """
        return ExpressionValidationResult()
