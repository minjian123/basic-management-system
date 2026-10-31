"""异步作业基座（横跨所有产品的横切能力；01_03）。

公共语义只在共享基座维护，平台内建与产品扩展沿同一继承链派生：

- `BaseJobHandler`：产品默认扩展基类（实现 `run(ctx)` 即可）；
- `JobContext` / `JobResult`：执行上下文与结果契约；
- `JobSubmission` / `JobSnapshot`：提交规格与只读快照；
- `JobLimits`：`[jobs]` 生效参数与容错回落；
- `JobHandlerRegistry`：本服务 handler 注册与声明对账；
- `JobStore`（`store` 模块函数）：作业表唯一写入口（提交 / 抢占 / 续租 / 终态 / 回收 / 清理）。

消费者（`JobWorker`）与同步执行入口（`JobRunner`）在后续模块提供。
"""

from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry, resolve_handler_path
from bms_core.jobs.spec import JobSnapshot, JobSubmission, parse_job_payload

__all__ = [
    "BaseJobHandler",
    "JobContext",
    "JobHandlerRegistry",
    "JobLimits",
    "JobResult",
    "JobSnapshot",
    "JobSubmission",
    "parse_job_payload",
    "resolve_handler_path",
]
