"""代码校验能力域：SQL 只读试算与表达式校验契约、诊断数据契约与依赖注入提供者。

- 取值集合：诊断级别 `VALIDATION_LEVELS`（错误 / 警告）、诊断类别 `VALIDATION_ISSUE_KINDS`
  （语法 / 白名单 / 字段 / 变量 / 其他）、表达式场景 `EXPRESSION_SCOPES`（数据范围 / 工作流条件 /
  报表数据集 / 自定义）。
- 口径常量：只读试算结果行上限 `SQL_ROW_LIMIT`、试算超时 `DEFAULT_SQL_TIMEOUT_MS`、
  校验限流配额 `SQL_VALIDATE_RATE_LIMIT`（窗口复用限流基座缺省值，不新建平行常量）。
- 数据契约：`ValidationIssue`（诊断明细：级别 / 类别 / 提示 / 行 / 列）/ `ValidationColumn`
  （试算字段）/ `SqlValidationResult`（结论 / 诊断 / 字段清单 / 预览行 / 耗时 / 截断标记）/
  `ExpressionContext`（场景 / 可用字段 / 预置变量）/ `ExpressionValidationResult`（结论 / 诊断）。
- `BaseCodeValidator`（`key = plugin_key = "code_validator"`）：异步 `validate_sql`（只读试算，超时与
  限流归实现与路由侧）/ `validate_expression`（语法 / 字段 / 变量诊断，含位置）。
- 提供者 `get_code_validator`（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：**校验不通过不是异常**——语法 / 白名单 / 字段 / 变量问题一律以结果契约（`valid=False` + 诊断明细）
返回，供前端内联标注；只有执行侧故障（服务不可用 / 超时）才由实现侧抛错。只读试算只允许只读语句、
走只读从库（归报表 BI 阶段），字段清单与预览行随校验一次返回、行数受 `SQL_ROW_LIMIT` 截断。cron 合法性
校验**不属本域**（归任务调度阶段）。真实执行与语义校验随报表 BI / RBAC / 工作流阶段回补。
"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request
from pydantic import Field

from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_EXPRESSION_SCOPE",
    "DEFAULT_SQL_TIMEOUT_MS",
    "EXPRESSION_SCOPES",
    "SQL_ROW_LIMIT",
    "SQL_VALIDATE_RATE_LIMIT",
    "VALIDATION_ISSUE_KINDS",
    "VALIDATION_LEVELS",
    "BaseCodeValidator",
    "ExpressionContext",
    "ExpressionValidationResult",
    "SqlValidationResult",
    "ValidationColumn",
    "ValidationIssue",
    "get_code_validator",
]

VALIDATION_LEVELS: tuple[str, ...] = ("error", "warning")
"""诊断级别取值集合（错误 / 警告）。"""

VALIDATION_ISSUE_KINDS: tuple[str, ...] = ("syntax", "whitelist", "field", "variable", "other")
"""诊断类别取值集合（语法 / 白名单 / 字段 / 变量 / 其他）。"""

EXPRESSION_SCOPES: tuple[str, ...] = ("data_scope", "workflow_condition", "report", "custom")
"""表达式场景取值集合（数据范围 / 工作流条件 / 报表数据集 / 自定义）。"""

DEFAULT_EXPRESSION_SCOPE = "custom"
"""缺省表达式场景（未声明时按自定义，不臆断业务场景）。"""

SQL_ROW_LIMIT = 200
"""只读试算结果行上限（超限截断并置截断标记）。"""

DEFAULT_SQL_TIMEOUT_MS = 5000
"""只读试算超时（毫秒；真实执行侧生效）。"""

SQL_VALIDATE_RATE_LIMIT = 30
"""SQL 校验限流配额（每窗口次数；窗口复用限流基座缺省窗口，不新建平行常量）。"""


class ValidationIssue(BaseSchema):
    """诊断明细（级别 / 类别 / 提示 / 位置）。"""

    level: str = Field(default="error", description="诊断级别（error 错误 / warning 警告）")
    kind: str = Field(default="other", description="诊断类别（syntax / whitelist / field / variable / other）")
    message: str = Field(description="提示文案（实现侧给出，前端直接展示）")
    line: int | None = Field(default=None, description="行号（从 1 起；无位置信息为空）")
    column: int | None = Field(default=None, description="列号（从 1 起；无位置信息为空）")


class ValidationColumn(BaseSchema):
    """只读试算返回字段（字段名 / 类型）。"""

    name: str = Field(description="字段名（供列名复制与字段声明比对）")
    type: str | None = Field(default=None, description="字段类型（缺省未知）")


class SqlValidationResult(BaseSchema):
    """SQL 校验与只读试算结果（结论 / 诊断 / 字段清单 / 预览行 / 耗时 / 截断标记）。"""

    valid: bool = Field(default=True, description="校验结论（无 error 级诊断即通过）")
    issues: list[ValidationIssue] = Field(default_factory=list[ValidationIssue], description="诊断明细")
    columns: list[ValidationColumn] = Field(default_factory=list[ValidationColumn], description="试算返回字段清单")
    rows: list[dict[str, object]] = Field(
        default_factory=list[dict[str, object]], description="结果预览行（上限 SQL_ROW_LIMIT）"
    )
    cost_ms: int = Field(default=0, ge=0, description="试算耗时（毫秒）")
    truncated: bool = Field(default=False, description="结果是否被行上限截断")


class ExpressionContext(BaseSchema):
    """表达式校验上下文（场景 / 可用字段 / 预置变量）。"""

    scope: str = Field(default=DEFAULT_EXPRESSION_SCOPE, description="表达式场景（data_scope / workflow_condition）")
    fields: list[str] = Field(default_factory=list[str], description="可用字段（场景侧下发）")
    variables: list[str] = Field(default_factory=list[str], description="预置变量（场景侧下发，如 @current_dept）")


class ExpressionValidationResult(BaseSchema):
    """表达式校验结果（结论 / 诊断）。"""

    valid: bool = Field(default=True, description="校验结论（无 error 级诊断即通过）")
    issues: list[ValidationIssue] = Field(default_factory=list[ValidationIssue], description="诊断明细")


class BaseCodeValidator(BasePluggable, ABC):
    """代码校验契约：SQL 只读试算与表达式校验（真实执行随报表 BI / RBAC / 工作流阶段）。"""

    key: str = "code_validator"
    plugin_key: str = "code_validator"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def validate_sql(self, sql: str, *, datasource: str | None = None) -> SqlValidationResult:
        """校验 SQL 并做只读试算（仅只读语句、走只读从库、超时与限流）。

        Args:
            sql: SQL 文本（仅只读语句；参数化防注入由实现侧承载）。
            datasource: 目标数据源标识（None 表示按场景缺省）。

        Returns:
            SqlValidationResult: 校验与试算结果（诊断 / 字段清单 / 预览行 / 耗时 / 截断标记）。
        """

    @abstractmethod
    async def validate_expression(
        self,
        expr: str,
        *,
        context: ExpressionContext | None = None,
    ) -> ExpressionValidationResult:
        """校验表达式（语法 / 字段 / 变量诊断，含位置）。

        Args:
            expr: 表达式文本（字段 + 运算符 + 预置变量）。
            context: 校验上下文（场景 / 可用字段 / 预置变量；None 表示按自定义场景）。

        Returns:
            ExpressionValidationResult: 校验结果（诊断明细）。
        """


def get_code_validator(request: Request) -> BaseCodeValidator:
    """取应用级代码校验器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseCodeValidator: 应用装配的代码校验器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseCodeValidator",
        resolve_plugin(
            "code_validator",
            settings.code_validator.provider,
            expected_version=BaseCodeValidator.contract_version,
        ),
    )
