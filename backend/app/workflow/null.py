"""workflow 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.workflow.base.py 迁入）。"""

from collections.abc import Mapping

from app.core.capability import BaseNullObject
from app.workflow.base import NULL_INSTANCE_ID, BaseWorkflowEngine, ProcessDefinition, ProcessInstance, WorkflowAction

__all__ = [
    "NullWorkflowEngine",
]


class NullWorkflowEngine(BaseWorkflowEngine, BaseNullObject):
    """占位工作流引擎：部署空操作、启动 / 完成任务固定返回占位实例（不连引擎）。"""

    async def deploy(self, definition: ProcessDefinition) -> None:
        """空操作（占位不部署）。

        Args:
            definition: 流程定义（占位忽略）。
        """

    async def start(self, definition_key: str, *, business_type: str, business_id: str) -> ProcessInstance:
        """固定返回占位实例（不连引擎）。

        Args:
            definition_key: 流程标识（占位回显）。
            business_type: 业务类型（占位回显）。
            business_id: 业务单据 id（占位回显）。

        Returns:
            ProcessInstance: 占位实例（`process_id` 为 `NULL_INSTANCE_ID`、`status="running"`）。
        """
        return ProcessInstance(
            process_id=NULL_INSTANCE_ID,
            definition_key=definition_key,
            business_type=business_type,
            business_id=business_id,
            current_node="start",
            status="running",
        )

    async def complete_task(
        self,
        task_id: str,
        *,
        action: WorkflowAction,
        variables: Mapping[str, object] | None = None,
    ) -> ProcessInstance:
        """固定返回占位实例（不连引擎）。

        Args:
            task_id: 任务 id（占位忽略）。
            action: 审批动作（占位忽略）。
            variables: 推进变量（占位忽略）。

        Returns:
            ProcessInstance: 占位实例（`process_id` 为 `NULL_INSTANCE_ID`、`status="completed"`）。
        """
        return ProcessInstance(process_id=NULL_INSTANCE_ID, status="completed")
