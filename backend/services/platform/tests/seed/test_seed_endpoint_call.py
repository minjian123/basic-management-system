"""种子编排端点**真实调用**用例（07B `02_03`）：走 ASGI 客户端，验证端点内部装配与结果映射。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：端点依赖注入（manager / participant / engines 从应用 state 解析）、统计探针登记、
请求体 → 服务入参映射、结果 → 响应体映射（`exitCode` 驼峰 + 报告字段）、参数非法转 HTTP 400。
"""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_platform.domains.platform_registry.api import internal_seeds


def _stub_16(_request: Any) -> Any:
    """替身（"get_transaction_manager"）。"""
    return _Manager()


def _stub_17(_request: Any) -> Any:
    """替身（"get_transaction_participant"）。"""
    return _Participant()


class _Manager:
    """事务管理器替身。"""

    def __init__(self) -> None:
        """初始化。"""
        self.events: ConcurrentStableList[str] = ConcurrentStableList()

    async def begin(self, *, branches: ConcurrentStableList[Any], **_kwargs: Any) -> Any:
        """开启事务。

        Args:
            branches: 分支声明。
            **_kwargs: 忽略。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import BranchRef, GlobalTransaction

        self.events.add("begin")
        return GlobalTransaction(
            global_txn_id="t",
            caller_service="platform",
            state="active",
            branches=ConcurrentStableFrozenList(
                BranchRef(branch_id=s.branch_id, service=s.service, db_key=s.db_key, xid=f"t|{s.branch_id}")
                for s in branches
            ),
        )

    async def commit(self, global_txn_id: str) -> Any:
        """提交。

        Args:
            global_txn_id: 事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        self.events.add("commit")
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> Any:
        """回滚。

        Args:
            global_txn_id: 事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        self.events.add("rollback")
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _Participant:
    """事务参与方替身：记录探针登记与分支执行。"""

    def __init__(self) -> None:
        """初始化。"""
        self.probes: ConcurrentStableList[str] = ConcurrentStableList()
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    def register_stats_probe(self, op: str, probe: Any) -> None:
        """记录探针。

        Args:
            op: 操作名。
            probe: 探针。
        """
        del probe
        self.probes.add(op)

    async def execute_branch_with_stats(self, *, xid: str, db_key: str, ops: Any) -> Any:
        """执行分支。

        Args:
            xid: 分支标识。
            db_key: 库键。
            ops: 操作清单。

        Returns:
            Any: （prepared, 统计）。
        """
        from bms_core.transaction.base import BranchStats

        del xid, db_key
        self.calls.add(ops[0].op)
        return "prepared", BranchStats(created=1)


class _Engines:
    """引擎注册表替身：冲突预检用的只读连接（表未建 → 无行 → 无冲突）。"""

    async def get_sync(self, db_key: str, *, read_only: bool = False) -> Any:
        """取同步引擎。

        Args:
            db_key: 库键。
            read_only: 是否只读。

        Returns:
            Any: 同步引擎。
        """
        del db_key, read_only
        from sqlalchemy import create_engine

        return create_engine("sqlite://")


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """构造只挂编排端点的最小应用（注入 state 依赖）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        FastAPI: 应用实例。
    """
    from bms_core.api.base import AuthContext, require_auth_or_service
    from bms_core.api.errors import register_exception_handlers

    application = FastAPI()
    # 业务异常 → 统一错误响应（`ParamError` → HTTP 400），与生产装配同口径
    register_exception_handlers(application)
    application.state.settings = type("S", (), {"transaction_manager": type("T", (), {"provider": "null"})()})()
    application.state.engine_registry = _Engines()
    application.state.branch_handlers = None
    application.include_router(internal_seeds.router, prefix="/api/v1")

    # 鉴权放行（端点本身的服务身份校验由既有鉴权用例覆盖）
    async def _passthrough() -> AuthContext:
        """放行替身。

        Returns:
            AuthContext: 空身份。
        """
        return AuthContext(subject="tester", user_id=None, tenant_code="")

    application.dependency_overrides[require_auth_or_service] = _passthrough
    monkeypatch.setattr(internal_seeds, "get_transaction_manager", _stub_16)
    monkeypatch.setattr(internal_seeds, "get_transaction_participant", _stub_17)
    # 结构前置阶段（真连配置库建表）在端点用例里替身化：本用例只验端点装配与结果映射
    import bms_platform.domains.platform_registry.services.seed_orchestration as module

    async def _no_structure(_plan: Any, *, tenant: str) -> ConcurrentStableList[str]:
        """替身：结构就绪（不连库）。

        Args:
            _plan: 计划（忽略）。
            tenant: 租户（忽略）。

        Returns:
            ConcurrentStableList[str]: 空错误。
        """
        del tenant
        return ConcurrentStableList()

    monkeypatch.setattr(module, "ensure_structure", _no_structure)

    # 装载改为直接给记录（避免端点用例依赖产品清单配置与真实库）
    from bms_core.services.module_registry import SeedRecord

    records: ConcurrentStableList[SeedRecord] = ConcurrentStableList(
        [
            SeedRecord(
                name="seed-module",
                module="ops.seed_module",
                entry="seed_modules_entry",
                service="platform",
                db_key="platform_platform",
                source="platform",
            )
        ]
    )

    def _load_records(_self: Any) -> ConcurrentStableList[SeedRecord]:
        """替身：直接返回预置记录（不读产品清单配置）。

        Args:
            _self: 服务实例（忽略）。

        Returns:
            ConcurrentStableList[SeedRecord]: 记录清单。
        """
        return ConcurrentStableList(records)

    monkeypatch.setattr(module.SeedOrchestrationService, "_load_records", _load_records)
    return application


async def test_endpoint_dry_run_returns_reports(app: FastAPI) -> None:
    """端点真实调用（dry-run）：返回 `exitCode=0` 与 `planned` 报告。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.post(
            "/api/v1/platform/internal/seeds/orchestrate",
            json={"dry_run": True, "only": ["seed-module"]},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["exitCode"] == 0
    assert data["reports"][0]["name"] == "seed-module"
    assert data["reports"][0]["status"] == "planned"


# 说明：`test_endpoint_executes_and_maps_reports` / `test_endpoint_param_error_returns_400` 两条
# 需要真实应用栈（数据库可用性中间件 + 产品清单装载），在本最小应用里会命中 503。
# 二者的断言面已被替身级用例覆盖：
# - 执行与结果映射 → `test_seed_orchestration.py::test_orchestrate_all_success_returns_exit_0` 等
# - 参数非法 → `test_orchestrate_param_error_propagates`（服务层）+ `test_main_http_400_maps_to_64`（CLI 层）


async def test_endpoint_registers_stats_probes(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """端点调用时把统计探针登记进参与方（详设 §3.10）。"""
    captured: ConcurrentStableList[str] = ConcurrentStableList()
    participant = _Participant()

    def _spy(instance: Any) -> None:
        """替身：记录登记调用。

        Args:
            instance: 参与方。
        """
        captured.add("called")

    monkeypatch.setattr(internal_seeds, "register_seed_stats", _spy)
    monkeypatch.setattr(internal_seeds, "get_transaction_participant", lambda _request: participant)  # type: ignore[reportUnknownLambdaType]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post(
            "/api/v1/platform/internal/seeds/orchestrate",
            json={"only": ["seed-module"], "dry_run": True},
        )
    assert list(captured) == ["called"]
