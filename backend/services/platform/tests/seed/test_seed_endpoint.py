"""种子编排内部端点用例（07B `02_03`；详设 §3.7 / §3.11 的端点侧）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：端点路由形状（路径 / 方法 / 鉴权）、请求体契约、结果映射（`exitCode` 驼峰）、
服务端异常路径（前置错误 / 结构失败 / 执行失败）。
"""

from typing import Any

import pytest
from fastapi.routing import APIRoute

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_platform.domains.platform_registry.api.internal_seeds import router
from bms_platform.domains.platform_registry.schemas.seed_orchestration import (
    SeedOrchestrationRequestSchema,
    SeedOrchestrationResultSchema,
)
from bms_platform.domains.platform_registry.services.seed_orchestration import (
    SeedOrchestrationResult,
    SeedOrchestrationService,
)


def _routes() -> ConcurrentStableList[APIRoute]:
    """取路由器上的 `APIRoute`（过滤非路由项）。

    Returns:
        ConcurrentStableList[APIRoute]: 路由清单。
    """
    return ConcurrentStableList(item for item in router.routes if isinstance(item, APIRoute))


def test_router_prefix_and_key() -> None:
    """路由键与前缀（服务间调用，不经网关）。"""
    assert router.prefix == "/platform/internal/seeds"
    assert router.key == "platform_internal_seeds"


def test_orchestrate_route_shape() -> None:
    """端点路径 / 方法：`POST /orchestrate`。"""
    paths = {(item.path, tuple(sorted(item.methods or ()))) for item in _routes()}
    assert ("/platform/internal/seeds/orchestrate", ("POST",)) in paths


def test_route_requires_auth_or_service() -> None:
    """鉴权：双模 `require_auth_or_service`（服务身份或登录态）挂在路由依赖上。"""
    route = next(item for item in _routes() if item.path.endswith("/orchestrate"))
    names = [getattr(dep.call, "__name__", "") for dep in route.dependant.dependencies]
    assert any("require_auth_or_service" in name for name in names)


# ---- 结果映射 ----


def test_result_schema_maps_snake_to_camel() -> None:
    """结果映射：服务出参 `exit_code` → 端点 `exitCode`（CLI 按驼峰读取）。"""
    result = SeedOrchestrationResult(exit_code=1, conflicts=ConcurrentStableFrozenList(["c"]))
    schema = SeedOrchestrationResultSchema(
        exitCode=result.exit_code,
        reports=ConcurrentStableList(),
        errors=ConcurrentStableList(result.errors),
        conflicts=ConcurrentStableList(result.conflicts),
        warnings=ConcurrentStableList(result.warnings),
    )
    assert schema.model_dump()["exitCode"] == 1
    assert schema.model_dump()["conflicts"] == ["c"]


def test_request_schema_accepts_stable_lists() -> None:
    """请求体：`only` / `skip` / `require` 用插入序集合（裸 list 亦可赋值）。"""
    schema = SeedOrchestrationRequestSchema(
        tenant="demo",
        only=ConcurrentStableList(["a"]),
        skip=ConcurrentStableList(["b"]),
        require=ConcurrentStableList(["c"]),
    )
    assert list(schema.only) == ["a"]
    assert list(schema.skip) == ["b"]
    assert list(schema.require) == ["c"]


# ---- 服务异常路径 ----


class _FailingManager:
    """事务管理器替身：`begin` 抛异常。"""

    async def begin(self, **_kwargs: Any) -> Any:
        """恒定抛异常。

        Args:
            **_kwargs: 忽略。

        Raises:
            RuntimeError: 恒定抛出。
        """
        raise RuntimeError("TM 不可达")


class _StubRunner:
    """分支执行器替身：全部 prepared。"""

    async def execute_branch_with_stats(self, **_kwargs: Any) -> Any:
        """执行分支。

        Args:
            **_kwargs: 忽略。

        Returns:
            Any: （prepared, 空统计）。
        """
        from bms_core.transaction.base import BranchStats

        return "prepared", BranchStats()


async def test_orchestrate_structure_failure_returns_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """结构前置失败 → 退出码 3（不进事务）。"""
    import bms_platform.domains.platform_registry.services.seed_orchestration as module

    async def _fail(_plan: Any, *, tenant: str) -> ConcurrentStableList[str]:
        """替身：结构失败。

        Args:
            _plan: 计划（忽略）。
            tenant: 租户（忽略）。

        Returns:
            ConcurrentStableList[str]: 错误明细。
        """
        del tenant
        return ConcurrentStableList(["结构就绪失败：OperationalError"])

    original = module.ensure_structure
    module.ensure_structure = _fail  # type: ignore[attr-defined]
    try:
        service = SeedOrchestrationService(
            caller_service="platform", manager=_FailingManager(), participant=_StubRunner(), engines=None
        )
        result = await service.orchestrate(
            __import__(
                "bms_platform.domains.platform_registry.services.seed_orchestration",
                fromlist=["SeedOrchestrationRequest"],
            ).SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"]))
        )
    finally:
        module.ensure_structure = original  # type: ignore[attr-defined]
    assert result.exit_code == 3
    assert "结构就绪失败" in result.errors[0]


async def test_orchestrate_manager_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """TM 不可达（`begin` 抛异常）→ 异常向上抛（由端点转 5xx / CLI 转 2）。"""
    import bms_platform.domains.platform_registry.services.seed_orchestration as module
    from bms_platform.domains.platform_registry.services.seed_orchestration import SeedOrchestrationRequest

    async def _ok(_plan: Any, *, tenant: str) -> ConcurrentStableList[str]:
        """替身：结构就绪。

        Args:
            _plan: 计划（忽略）。
            tenant: 租户（忽略）。

        Returns:
            ConcurrentStableList[str]: 空错误。
        """
        del tenant
        return ConcurrentStableList()

    original = module.ensure_structure
    module.ensure_structure = _ok  # type: ignore[attr-defined]
    try:
        service = SeedOrchestrationService(
            caller_service="platform", manager=_FailingManager(), participant=_StubRunner(), engines=None
        )
        with pytest.raises(RuntimeError, match="TM 不可达"):
            await service.orchestrate(SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"])))
    finally:
        module.ensure_structure = original  # type: ignore[attr-defined]


async def test_orchestrate_param_error_propagates() -> None:
    """参数非法（`--only` 引用不存在的种子）→ `ParamError`（端点转 HTTP 400）。"""
    from bms_platform.domains.platform_registry.services.seed_orchestration import SeedOrchestrationRequest

    service = SeedOrchestrationService(
        caller_service="platform", manager=_FailingManager(), participant=_StubRunner(), engines=None
    )
    with pytest.raises(ParamError):
        await service.orchestrate(SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["ghost"])))
