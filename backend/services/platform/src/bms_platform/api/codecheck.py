"""代码校验占位路由：`/api/v1/code/validate-sql` 与 `/api/v1/code/validate-expression`。

- 两端点统一经代码校验出口（占位实现恒定通过），**均需登录**（设计期操作），权限码（报表 `rpt:design` /
  数据范围 `role:grant` / 工作流 `wf:define`）由上层声明、基座不内建。
- SQL 校验为**重操作**（真实实现走只读从库试算），先经限流基座（02-25）按 IP 维度判定配额
  （租户位取解析链当前租户、规则取 `SQL_VALIDATE_RATE_LIMIT` + 限流基座缺省窗口）；表达式校验不接限流。
- **校验不通过以结果契约表达（非异常）**：语法 / 白名单 / 字段 / 变量问题随响应返回，供前端内联标注。
- 真实只读从库执行与表达式语义校验随报表 BI / RBAC / 工作流阶段，本路由只做参数校验、限流判定与委托。
"""

from typing import Annotated

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import current_code_of, get_code_validator, get_rate_limiter, get_tenant
from bms_core.codecheck.base import (
    SQL_VALIDATE_RATE_LIMIT,
    BaseCodeValidator,
    ExpressionContext,
    ExpressionValidationResult,
    SqlValidationResult,
    ValidationIssue,
)
from bms_core.db.tenant import TenantContext
from bms_core.ratelimit.base import GLOBAL_RATE_SCOPE, BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_core.schemas.codecheck import (
    ExpressionContextPayload,
    ExpressionValidateRequest,
    ExpressionValidationResponse,
    SqlValidateRequest,
    SqlValidationResponse,
    ValidationColumnResponse,
    ValidationIssueResponse,
)
from bms_core.schemas.common import ApiResponse

router = BaseRouter(
    key="codecheck",
    prefix="/code",
    tags=["codecheck"],
    dependencies=[Depends(require_auth)],
)

ValidatorDep = Annotated[BaseCodeValidator, Depends(get_code_validator)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]


def _issue_response(issue: ValidationIssue) -> ValidationIssueResponse:
    """把能力域诊断明细映射为路由响应契约（字段一一对应）。

    Args:
        issue: 能力域诊断明细。

    Returns:
        ValidationIssueResponse: 路由响应契约。
    """
    return ValidationIssueResponse(
        level=issue.level,
        kind=issue.kind,
        message=issue.message,
        line=issue.line,
        column=issue.column,
    )


def _sql_response(result: SqlValidationResult) -> SqlValidationResponse:
    """把能力域 SQL 校验结果映射为路由响应契约（字段一一对应）。

    Args:
        result: 能力域 SQL 校验结果。

    Returns:
        SqlValidationResponse: 路由响应契约。
    """
    return SqlValidationResponse(
        valid=result.valid,
        issues=[_issue_response(issue) for issue in result.issues],
        columns=[ValidationColumnResponse(name=column.name, type=column.type) for column in result.columns],
        rows=result.rows,
        cost_ms=result.cost_ms,
        truncated=result.truncated,
    )


def _expression_response(result: ExpressionValidationResult) -> ExpressionValidationResponse:
    """把能力域表达式校验结果映射为路由响应契约（字段一一对应）。

    Args:
        result: 能力域表达式校验结果。

    Returns:
        ExpressionValidationResponse: 路由响应契约。
    """
    return ExpressionValidationResponse(
        valid=result.valid,
        issues=[_issue_response(issue) for issue in result.issues],
    )


def _to_context(payload: ExpressionContextPayload | None) -> ExpressionContext | None:
    """把路由上下文映射为能力域上下文（缺省保留 None，由实现侧取场景缺省）。

    Args:
        payload: 路由上下文（可为 None）。

    Returns:
        ExpressionContext | None: 能力域上下文；未提供为 None。
    """
    if payload is None:
        return None
    return ExpressionContext(scope=payload.scope, fields=payload.fields, variables=payload.variables)


async def _require_sql_quota(
    request: Request,
    limiter: BaseRateLimiter,
    tenant: TenantContext | None,
) -> None:
    """按 IP 维度校验 SQL 试算配额（超出抛限流错误 10005 / 429）。

    Args:
        request: 请求对象（取客户端地址作为限流目标）。
        limiter: 限流基座。
        tenant: 解析链租户上下文（限流键租户位）。
    """
    client = request.client
    target = client.host if client is not None else GLOBAL_RATE_SCOPE
    key = build_rate_limit_key(dimension="ip", target=target, tenant=current_code_of(tenant))
    await limiter.require(key, RateLimitRule(limit=SQL_VALIDATE_RATE_LIMIT))


@router.post("/validate-sql")
async def validate_sql(
    request: Request,
    validator: ValidatorDep,
    limiter: LimiterDep,
    tenant: TenantDep,
    req: SqlValidateRequest,
) -> ApiResponse:
    """校验 SQL 并做只读试算（先经限流基座判定配额）。

    Args:
        request: 请求对象（限流目标取客户端地址）。
        validator: 代码校验基座。
        limiter: 限流基座。
        tenant: 解析链租户上下文（限流键租户位）。
        req: SQL 校验请求（SQL 文本 / 目标数据源）。

    Returns:
        ApiResponse: 统一响应，data 为校验结果（`SqlValidationResponse`）。
    """
    await _require_sql_quota(request, limiter, tenant)
    result = await validator.validate_sql(req.sql, datasource=req.datasource)
    return ApiResponse.ok(_sql_response(result))


@router.post("/validate-expression")
async def validate_expression(
    validator: ValidatorDep,
    req: ExpressionValidateRequest,
) -> ApiResponse:
    """校验表达式（语法 / 字段 / 变量诊断，含位置）。

    Args:
        validator: 代码校验基座。
        req: 表达式校验请求（表达式文本 / 上下文）。

    Returns:
        ApiResponse: 统一响应，data 为校验结果（`ExpressionValidationResponse`）。
    """
    result = await validator.validate_expression(req.expr, context=_to_context(req.context))
    return ApiResponse.ok(_expression_response(result))
