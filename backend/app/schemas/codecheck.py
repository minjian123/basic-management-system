"""代码校验占位路由的请求 / 响应契约（与 `app/codecheck/` 能力域契约字段一一对应）。

- `SqlValidateRequest` / `ExpressionValidateRequest`：SQL 校验与表达式校验请求。
- `SqlValidationResponse` / `ExpressionValidationResponse`：校验结果响应（诊断 / 字段清单 / 预览行 / 耗时 / 截断）。
- `ValidationIssueResponse` / `ValidationColumnResponse` / `ExpressionContextPayload`：诊断明细、试算字段与上下文。

口径：路由契约与能力域契约**字段名一致**，由路由层显式映射（不隐式透传字典），保证 OpenAPI 契约稳定；
字段一律 snake_case（前端 camelCase 契约由宿主数据通路注入层映射）；校验不通过以结果契约表达，
**不抛业务异常**（只有执行侧故障由实现侧抛错，随对应阶段登记）。
"""

from pydantic import Field

from app.schemas.base import BaseSchema

__all__ = [
    "ExpressionContextPayload",
    "ExpressionValidateRequest",
    "ExpressionValidationResponse",
    "SqlValidateRequest",
    "SqlValidationResponse",
    "ValidationColumnResponse",
    "ValidationIssueResponse",
]


class SqlValidateRequest(BaseSchema):
    """SQL 校验请求：`{sql, datasource?}`。"""

    sql: str = Field(min_length=1, description="SQL 文本（仅只读语句）")
    datasource: str | None = Field(default=None, description="目标数据源标识（缺省按场景缺省）")


class ExpressionContextPayload(BaseSchema):
    """表达式校验上下文：`{scope?, fields?, variables?}`。"""

    scope: str = Field(default="custom", description="表达式场景（data_scope / workflow_condition / report / custom）")
    fields: list[str] = Field(default_factory=list[str], description="可用字段（场景侧下发）")
    variables: list[str] = Field(default_factory=list[str], description="预置变量（场景侧下发）")


class ExpressionValidateRequest(BaseSchema):
    """表达式校验请求：`{expr, context?}`。"""

    expr: str = Field(min_length=1, description="表达式文本（字段 + 运算符 + 预置变量）")
    context: ExpressionContextPayload | None = Field(default=None, description="校验上下文（缺省按自定义场景）")


class ValidationIssueResponse(BaseSchema):
    """诊断明细响应。"""

    level: str = Field(description="诊断级别（error / warning）")
    kind: str = Field(description="诊断类别（syntax / whitelist / field / variable / other）")
    message: str = Field(description="提示文案")
    line: int | None = Field(default=None, description="行号（从 1 起；无位置信息为空）")
    column: int | None = Field(default=None, description="列号（从 1 起；无位置信息为空）")


class ValidationColumnResponse(BaseSchema):
    """只读试算返回字段响应。"""

    name: str = Field(description="字段名")
    type: str | None = Field(default=None, description="字段类型（缺省未知）")


class SqlValidationResponse(BaseSchema):
    """SQL 校验与只读试算结果响应。"""

    valid: bool = Field(description="校验结论（无 error 级诊断即通过）")
    issues: list[ValidationIssueResponse] = Field(description="诊断明细")
    columns: list[ValidationColumnResponse] = Field(description="试算返回字段清单")
    rows: list[dict[str, object]] = Field(description="结果预览行（上限 200）")
    cost_ms: int = Field(ge=0, description="试算耗时（毫秒）")
    truncated: bool = Field(description="结果是否被行上限截断")


class ExpressionValidationResponse(BaseSchema):
    """表达式校验结果响应。"""

    valid: bool = Field(description="校验结论（无 error 级诊断即通过）")
    issues: list[ValidationIssueResponse] = Field(description="诊断明细")
