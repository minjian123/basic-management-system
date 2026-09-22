"""工作流引擎适配基座契约测试（Kiwi 53）：契约 / 标识 / 枚举 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from support_app import ApplicationFactory, lifespan

from bms_core.api.deps import get_workflow_engine
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.workflow.base import (
    NULL_INSTANCE_ID,
    NULL_TASK_ID,
    WORKFLOW_STATUS,
    BaseWorkflowEngine,
    ProcessDefinition,
    ProcessInstance,
    WorkflowAction,
    WorkflowTask,
)
from bms_core.workflow.null import NullWorkflowEngine


@pytest.mark.kiwi_id(53)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseWorkflowEngine, BaseCapability)
    assert issubclass(NullWorkflowEngine, BaseWorkflowEngine)
    assert issubclass(NullWorkflowEngine, BaseNullObject)
    assert BaseWorkflowEngine.key == "workflow_engine"

    engine = NullWorkflowEngine()
    assert engine.placeholder is True
    assert "占位实现" in engine.describe()


@pytest.mark.kiwi_id(53)
def test_action_enum() -> None:
    """审批动作枚举三值（StrEnum 字符串比较）。"""
    assert [action.value for action in WorkflowAction] == ["approve", "reject", "withdraw"]
    assert WorkflowAction.APPROVE == "approve"
    assert WorkflowAction.REJECT == "reject"
    assert WorkflowAction.WITHDRAW == "withdraw"


@pytest.mark.kiwi_id(53)
def test_constants() -> None:
    """状态清单与占位 id 常量。"""
    assert WORKFLOW_STATUS == ("running", "completed", "rejected")
    assert len(set(WORKFLOW_STATUS)) == len(WORKFLOW_STATUS)
    assert NULL_INSTANCE_ID == "null-instance-id"
    assert NULL_TASK_ID == "null-task-id"


@pytest.mark.kiwi_id(53)
def test_data_contracts_defaults_and_frozen() -> None:
    """三数据契约默认值正确且不可变。"""
    assert ProcessDefinition(definition_key="k", bpmn_xml="<xml/>").version == 1
    instance = ProcessInstance(process_id="p1")
    assert instance.status == "running"
    assert instance.definition_key == ""
    assert WorkflowTask(task_id="t1", instance_id="p1", node_id="n1", assignee="u1").status == "pending"

    field = "status"
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field, "completed")


@pytest.mark.kiwi_id(53)
async def test_null_deploy_noop() -> None:
    """占位 deploy 为空操作。"""
    engine = NullWorkflowEngine()
    assert await engine.deploy(ProcessDefinition(definition_key="k", bpmn_xml="<xml/>")) is None


@pytest.mark.kiwi_id(53)
async def test_null_start_and_complete_task() -> None:
    """占位 start / complete_task 固定返回占位实例（不连引擎）。"""
    engine = NullWorkflowEngine()
    started = await engine.start("leave", business_type="pur_apply", business_id="B1")
    assert started == ProcessInstance(
        process_id=NULL_INSTANCE_ID,
        definition_key="leave",
        business_type="pur_apply",
        business_id="B1",
        current_node="start",
        status="running",
    )

    completed = await engine.complete_task(NULL_TASK_ID, action=WorkflowAction.APPROVE)
    assert completed.process_id == NULL_INSTANCE_ID
    assert completed.status == "completed"


@pytest.mark.kiwi_id(53)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位引擎；路由经 get_workflow_engine 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.workflow_engine, NullWorkflowEngine)

        @app.get("/workflow-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            engine: Annotated[BaseWorkflowEngine, Depends(get_workflow_engine)],
        ) -> dict[str, object]:
            instance = await engine.start("k", business_type="b", business_id="1")
            return {"key": engine.key, "type": type(engine).__name__, "status": instance.status}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/workflow-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "workflow_engine", "type": "NullWorkflowEngine", "status": "running"}
