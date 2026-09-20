"""代码校验基座契约测试（Kiwi 927）：契约 / 常量 / 数据契约 / 占位语义 / 依赖解析 / 占位路由 / 限流接入。"""

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.api.codecheck import router as codecheck_router
from app.api.deps import get_code_validator, get_rate_limiter
from app.codecheck.base import (
    DEFAULT_EXPRESSION_SCOPE,
    DEFAULT_SQL_TIMEOUT_MS,
    EXPRESSION_SCOPES,
    SQL_ROW_LIMIT,
    SQL_VALIDATE_RATE_LIMIT,
    VALIDATION_ISSUE_KINDS,
    VALIDATION_LEVELS,
    BaseCodeValidator,
    ExpressionContext,
    ExpressionValidationResult,
    SqlValidationResult,
    ValidationColumn,
    ValidationIssue,
)
from app.codecheck.null import NullCodeValidator
from app.core.capability import BaseCapability, BaseNullObject
from app.core.error_codes import ErrorCode
from app.core.plugin import BasePluggable, resolve_plugin
from app.main import ApplicationFactory, lifespan
from app.ratelimit.base import RateLimitRule

API = "/api/v1/code"


class _RecordingLimiter:
    """限流基座测试替身：记录限流键（不继承能力端口，避免以占位名污染进程级注册表）。"""

    def __init__(self) -> None:
        """初始化空限流键记录。"""
        self.keys: list[str] = []

    async def require(self, key: str, rule: RateLimitRule) -> None:
        """记录限流键并恒定放行。

        Args:
            key: 限流键。
            rule: 限流规则（替身忽略）。
        """
        del rule
        self.keys.append(key)


@pytest.mark.kiwi_id(927)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BaseCodeValidator, BasePluggable)
    assert issubclass(BaseCodeValidator, BaseCapability)
    assert issubclass(NullCodeValidator, BaseCodeValidator)
    assert issubclass(NullCodeValidator, BaseNullObject)
    assert BaseCodeValidator.key == "code_validator"
    assert BaseCodeValidator.plugin_key == "code_validator"

    instance = NullCodeValidator()
    assert instance.placeholder is True
    assert "占位实现" in instance.describe()


@pytest.mark.kiwi_id(927)
def test_constants() -> None:
    """取值集合与口径常量。"""
    assert VALIDATION_LEVELS == ("error", "warning")
    assert VALIDATION_ISSUE_KINDS == ("syntax", "whitelist", "field", "variable", "other")
    assert EXPRESSION_SCOPES == ("data_scope", "workflow_condition", "report", "custom")
    assert DEFAULT_EXPRESSION_SCOPE == "custom"
    assert SQL_ROW_LIMIT == 200
    assert DEFAULT_SQL_TIMEOUT_MS == 5000
    assert SQL_VALIDATE_RATE_LIMIT == 30


@pytest.mark.kiwi_id(927)
def test_data_contract_defaults() -> None:
    """五数据契约字段口径与缺省值。"""
    issue = ValidationIssue(message="缺少 FROM")
    assert issue.level == "error"
    assert issue.kind == "other"
    assert issue.line is None
    assert issue.column is None

    column = ValidationColumn(name="amount")
    assert column.type is None

    result = SqlValidationResult()
    assert result.valid is True
    assert result.issues == []
    assert result.columns == []
    assert result.rows == []
    assert result.cost_ms == 0
    assert result.truncated is False

    context = ExpressionContext()
    assert context.scope == DEFAULT_EXPRESSION_SCOPE
    assert context.fields == []
    assert context.variables == []

    expression = ExpressionValidationResult()
    assert expression.valid is True
    assert expression.issues == []


@pytest.mark.kiwi_id(927)
async def test_null_validate_sql_always_passes() -> None:
    """占位 SQL 校验：恒定通过、零诊断、零副作用。"""
    validator = NullCodeValidator()

    result = await validator.validate_sql("select 1")
    assert result == SqlValidationResult()
    assert await validator.validate_sql("select 1", datasource="rpt") == result


@pytest.mark.kiwi_id(927)
async def test_null_validate_expression_always_passes() -> None:
    """占位表达式校验：恒定通过、零诊断（上下文传入与否一致）。"""
    validator = NullCodeValidator()

    result = await validator.validate_expression("dept_id = @current_dept")
    assert result == ExpressionValidationResult()
    context = ExpressionContext(scope="data_scope", fields=["dept_id"], variables=["@current_dept"])
    assert await validator.validate_expression("dept_id = @current_dept", context=context) == result


@pytest.mark.kiwi_id(927)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位实现与提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        validator = app.state.code_validator
        assert isinstance(validator, NullCodeValidator)
        assert resolve_plugin("code_validator", None) is validator
        assert app.state.plugin_providers["code_validator"] == "null"


@pytest.mark.kiwi_id(927)
def test_route_auth_scope() -> None:
    """登录口径：两端点均挂登录依赖（路由级统一）。"""
    routes = [route for route in codecheck_router.routes if isinstance(route, APIRoute)]
    assert codecheck_router.key == "codecheck"
    assert {route.path for route in routes} == {"/code/validate-sql", "/code/validate-expression"}
    assert {route.path: len(route.dependencies) for route in routes} == {
        "/code/validate-sql": 1,
        "/code/validate-expression": 1,
    }


@pytest.mark.kiwi_id(927)
async def test_placeholder_route_validate_sql(client: AsyncClient) -> None:
    """占位路由：SQL 校验结果回显；空 SQL → 10001。"""
    resp = await client.post(f"{API}/validate-sql", json={"sql": "select 1", "datasource": "rpt"})
    assert resp.status_code == 200
    assert resp.json()["data"] == {
        "valid": True,
        "issues": [],
        "columns": [],
        "rows": [],
        "cost_ms": 0,
        "truncated": False,
    }

    invalid = await client.post(f"{API}/validate-sql", json={"sql": "   "})
    assert invalid.json()["code"] == ErrorCode.PARAM


@pytest.mark.kiwi_id(927)
async def test_placeholder_route_validate_expression(client: AsyncClient) -> None:
    """占位路由：表达式校验结果回显（带上下文一致）；空表达式 → 10001。"""
    resp = await client.post(f"{API}/validate-expression", json={"expr": "dept_id = 1"})
    assert resp.status_code == 200
    assert resp.json()["data"] == {"valid": True, "issues": []}

    with_context = await client.post(
        f"{API}/validate-expression",
        json={
            "expr": "dept_id = @current_dept",
            "context": {"scope": "data_scope", "fields": ["dept_id"], "variables": ["@current_dept"]},
        },
    )
    assert with_context.json()["data"] == {"valid": True, "issues": []}

    invalid = await client.post(f"{API}/validate-expression", json={"expr": "   "})
    assert invalid.json()["code"] == ErrorCode.PARAM


class _StubValidator:
    """代码校验测试替身：返回非空诊断与试算结果（覆盖映射分支；不继承能力端口，不参与注册表）。"""

    async def validate_sql(self, sql: str, *, datasource: str | None = None) -> SqlValidationResult:
        """校验 SQL（替身固定返回非空诊断与试算结果）。

        Args:
            sql: SQL 文本（替身忽略）。
            datasource: 数据源标识（替身忽略）。

        Returns:
            SqlValidationResult: 含诊断 / 字段 / 预览行 / 耗时 / 截断标记的结果。
        """
        del sql, datasource
        return SqlValidationResult(
            valid=False,
            issues=[ValidationIssue(level="warning", kind="whitelist", message="仅支持 SELECT", line=2, column=3)],
            columns=[ValidationColumn(name="amount", type="decimal")],
            rows=[{"amount": "1.00"}],
            cost_ms=12,
            truncated=True,
        )

    async def validate_expression(
        self,
        expr: str,
        *,
        context: ExpressionContext | None = None,
    ) -> ExpressionValidationResult:
        """校验表达式（替身固定返回非空诊断）。

        Args:
            expr: 表达式文本（替身忽略）。
            context: 校验上下文（替身忽略）。

        Returns:
            ExpressionValidationResult: 含单条字段类诊断的结果。
        """
        del expr, context
        return ExpressionValidationResult(valid=False, issues=[ValidationIssue(kind="field", message="字段不存在：x")])


@pytest.mark.kiwi_id(927)
async def test_route_mapping_with_stub_validator() -> None:
    """映射分支：替身校验器返回非空诊断与试算结果时路由字段一一对应。"""
    app = ApplicationFactory().create(None)
    app.dependency_overrides[get_code_validator] = _StubValidator
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sql = await client.post(f"{API}/validate-sql", json={"sql": "select 1"})
        expr = await client.post(f"{API}/validate-expression", json={"expr": "x = 1"})

    assert sql.json()["data"] == {
        "valid": False,
        "issues": [{"level": "warning", "kind": "whitelist", "message": "仅支持 SELECT", "line": 2, "column": 3}],
        "columns": [{"name": "amount", "type": "decimal"}],
        "rows": [{"amount": "1.00"}],
        "cost_ms": 12,
        "truncated": True,
    }
    assert expr.json()["data"] == {
        "valid": False,
        "issues": [{"level": "error", "kind": "field", "message": "字段不存在：x", "line": None, "column": None}],
    }


@pytest.mark.kiwi_id(927)
async def test_validate_sql_rate_limit_key() -> None:
    """限流接入：SQL 校验先经限流基座（IP 维度 + 解析链租户位）。"""
    app = ApplicationFactory().create(None)
    limiter = _RecordingLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"{API}/validate-sql", json={"sql": "select 1"})

    assert resp.json()["data"]["valid"] is True
    assert len(limiter.keys) == 1
    assert limiter.keys[0].startswith("bms:")
    assert ":rate:ip:" in limiter.keys[0]
