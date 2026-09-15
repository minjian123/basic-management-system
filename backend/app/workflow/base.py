"""工作流能力域：统一引擎适配契约（真实 SpiffWorkflow + BPMN 解析随工作流阶段回补）。

- `WORKFLOW_STATUS` / `NULL_INSTANCE_ID` / `NULL_TASK_ID`：实例状态清单与占位 id。
- `WorkflowAction`：审批动作枚举（`approve` 同意 / `reject` 驳回 / `withdraw` 撤回）。
- `ProcessDefinition` / `ProcessInstance` / `WorkflowTask`：定义 / 实例 / 任务数据契约（frozen dataclass）。
- `BaseWorkflowEngine`：能力域中间层契约（`key = "workflow_engine"`）——异步 `deploy` / `start` / `complete_task`。
- `get_workflow_engine`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：真实实现用 SpiffWorkflow（同步引擎在异步栈中以线程池运行）；引擎本身不持久化，流程 / 实例 / 任务 /
审批记录由 BMS 自建表（`wf_process` / `wf_instance` / `wf_task` / `wf_record`）维护，归实现与上层；
待办站内信 / 邮件取 02-4-4 `BaseNotifier`、待办实时提醒 `approval.todo` 取 02-4-5 `BaseRealtimePublisher`。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "NULL_INSTANCE_ID",
    "NULL_TASK_ID",
    "WORKFLOW_STATUS",
    "BaseWorkflowEngine",
    "ProcessDefinition",
    "ProcessInstance",
    "WorkflowAction",
    "WorkflowTask",
    "get_workflow_engine",
]

WORKFLOW_STATUS: tuple[str, ...] = ("running", "completed", "rejected")
"""实例状态清单；占位期仅登记不校验。"""

NULL_INSTANCE_ID = "null-instance-id"
"""占位实例 id（NullWorkflowEngine 固定返回）。"""

NULL_TASK_ID = "null-task-id"
"""占位任务 id。"""


class WorkflowAction(StrEnum):
    """审批动作。"""

    APPROVE = "approve"
    """同意。"""

    REJECT = "reject"
    """驳回。"""

    WITHDRAW = "withdraw"
    """撤回。"""


@dataclass(frozen=True)
class ProcessDefinition(BaseObject):
    """流程定义（BPMN 2.0）。"""

    definition_key: str
    """流程标识（同一流程多版本共享；`definition_key` + `version` 唯一）。"""

    bpmn_xml: str
    """BPMN XML 定义内容。"""

    version: int = 1
    """版本号。"""


@dataclass(frozen=True)
class ProcessInstance(BaseObject):
    """流程实例。"""

    process_id: str
    """实例 id。"""

    definition_key: str = ""
    """流程标识。"""

    business_type: str = ""
    """业务类型（如 `pur_purchase_apply`）。"""

    business_id: str = ""
    """业务单据 id。"""

    current_node: str = ""
    """当前节点。"""

    status: str = "running"
    """实例状态（取值见 `WORKFLOW_STATUS`）。"""


@dataclass(frozen=True)
class WorkflowTask(BaseObject):
    """流程任务（待办）。"""

    task_id: str
    """任务 id。"""

    instance_id: str
    """所属实例 id。"""

    node_id: str
    """节点 id。"""

    assignee: str
    """处理人（用户 id）。"""

    status: str = "pending"
    """任务状态。"""


class BaseWorkflowEngine(BasePluggable, ABC):
    """工作流引擎适配契约：部署定义 / 启动实例 / 完成任务。"""

    key: str = "workflow_engine"
    plugin_key: str = "workflow_engine"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def deploy(self, definition: ProcessDefinition) -> None:
        """部署流程定义（真实实现落 `wf_process` 并发布 `wf.process.deployed`）。

        Args:
            definition: 流程定义。
        """

    @abstractmethod
    async def start(self, definition_key: str, *, business_type: str, business_id: str) -> ProcessInstance:
        """启动流程实例（按最新版本）。

        Args:
            definition_key: 流程标识。
            business_type: 业务类型。
            business_id: 业务单据 id。

        Returns:
            ProcessInstance: 新实例。
        """

    @abstractmethod
    async def complete_task(
        self,
        task_id: str,
        *,
        action: WorkflowAction,
        variables: Mapping[str, object] | None = None,
    ) -> ProcessInstance:
        """完成待办任务并推进流程。

        Args:
            task_id: 任务 id。
            action: 审批动作（同意 / 驳回 / 撤回）。
            variables: 推进变量（可选）。

        Returns:
            ProcessInstance: 推进后的实例。
        """


def get_workflow_engine(request: Request) -> BaseWorkflowEngine:
    """取应用级工作流引擎（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseWorkflowEngine: 应用装配的引擎实例。
    """
    return cast("BaseWorkflowEngine", request.app.state.workflow_engine)
