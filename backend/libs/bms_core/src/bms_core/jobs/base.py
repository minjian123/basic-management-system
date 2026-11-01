"""异步作业基类体系：执行上下文 / 执行结果 / 产品扩展基类。

- `BaseJobHandler`：**产品默认扩展基类**（继承 `BasePluggable`，实现 `run(ctx)`）；产品只实现
  本产品的 handler 与负载，抢占 / 租约 / 重试 / 进度 / 取消 / 事件由基座统一提供；
- `JobContext`：执行上下文（作业标识 / 负载 / 尝试次数 / 租户 / 会话开合口 / 进度上报 / 取消检查 /
  行级错误写入）；执行体不自己建连接、不直接写作业表；
- `JobResult`：执行结果（成功 / 失败（可重试标记）/ 取消），由消费者统一落终态。

确有必要时可继承更深的消费者 / worker 基类并覆写少量钩子，但必须保持统一状态机、租约、进度与
事件契约；偏差由该产品自担，不得影响其他产品，不得另起炉灶自研平行队列 / 消费者 / 租约 / 重试 / 监控。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable
from bms_core.core.roots import BaseDataContract, BaseValueObject

__all__ = ["BaseJobHandler", "JobContext", "JobResult"]

ProgressReporter = Callable[[int, "int | None"], Awaitable[None]]
"""进度上报回调：`(done, total)`。"""

CancelChecker = Callable[[], Awaitable[bool]]
"""取消检查回调：返回 True 表示已请求取消。"""

ErrorWriter = Callable[..., Awaitable[None]]
"""行级错误写入回调：`(message, row_no=None, column_key=None, item_ref=None)`。"""


@dataclass
class JobContext(BaseDataContract):
    """作业执行上下文（由消费者构造并注入能力，执行体只读 / 只调用回调）。"""

    job_id: int
    """作业标识（`sys_job.id`；日志与事件串联键）。"""

    job_type: str
    """作业类型（与声明一致）。"""

    service_key: str
    """提供方服务键。"""

    db_key: str
    """作业所在库键（执行体取库会话的依据）。"""

    payload: ConcurrentStableDict[str, object] = field(default_factory=ConcurrentStableDict[str, object])
    """已解析负载（JSON 对象）。"""

    tenant_id: int | None = None
    """租户主键（平台链作业为 None）。"""

    attempt: int = 1
    """本次是第几次执行（自 1 起）。"""

    max_attempts: int = 1
    """最大执行次数。"""

    open_session: Callable[[], AbstractAsyncContextManager[Any]] | None = field(default=None, repr=False)
    """作业所在库的会话开合口（消费者注入）。"""

    progress_reporter: ProgressReporter | None = field(default=None, repr=False)
    """进度上报回调（消费者注入）。"""

    cancel_checker: CancelChecker | None = field(default=None, repr=False)
    """取消检查回调（消费者注入）。"""

    error_writer: ErrorWriter | None = field(default=None, repr=False)
    """行级错误写入回调（消费者注入）。"""

    def session(self) -> AbstractAsyncContextManager[Any]:
        """取作业所在库的会话上下文（`async with ctx.session() as session:`）。

        Returns:
            AbstractAsyncContextManager[Any]: 会话上下文。

        Raises:
            RuntimeError: 消费者未注入会话开合口（装配缺失，属编码错误而非业务错误）。
        """
        if self.open_session is None:
            raise RuntimeError("作业执行上下文未注入会话开合口（open_session）")
        return self.open_session()

    async def report_progress(self, done: int, total: int | None = None) -> None:
        """上报进度（总量未知传 None；消费者负责节流与续租）。

        Args:
            done: 已完成量。
            total: 总量；None 表示不确定进度。

        Raises:
            RuntimeError: 消费者未注入进度上报回调（装配缺失）。
        """
        if self.progress_reporter is None:
            raise RuntimeError("作业执行上下文未注入进度上报回调（progress_reporter）")
        await self.progress_reporter(int(done), None if total is None else int(total))

    async def should_cancel(self) -> bool:
        """检查是否已请求取消（handler 应在批次边界调用并自行收尾）。

        Returns:
            bool: 已请求取消 True；未注入检查器时 False。
        """
        if self.cancel_checker is None:
            return False
        return await self.cancel_checker()

    async def add_error(
        self,
        message: str,
        *,
        row_no: int | None = None,
        column_key: str | None = None,
        item_ref: str | None = None,
    ) -> None:
        """写一条行级错误明细（导入等批量作业用；随作业保留期硬删）。

        Args:
            message: 错误原因。
            row_no: 业务行号（导入 Excel 行，自 2 起）。
            column_key: 出错列 / 字段键。
            item_ref: 业务条目标识（非行号场景）。

        Raises:
            RuntimeError: 消费者未注入错误写入回调（装配缺失）。
        """
        if self.error_writer is None:
            raise RuntimeError("作业执行上下文未注入错误写入回调（error_writer）")
        await self.error_writer(message, row_no=row_no, column_key=column_key, item_ref=item_ref)


@dataclass(frozen=True)
class JobResult(BaseValueObject):
    """作业执行结果（消费者据此落终态；异常由消费者统一转失败）。"""

    status: str
    """结果状态：`succeeded` / `failed` / `canceled`。"""

    message: str = ""
    """给运营看的一句话说明（失败 / 取消必填原因）。"""

    output: ConcurrentStableDict[str, object] | None = None
    """成功输出摘要（落 `sys_job.result`，按 `result_max_chars` 截断）。"""

    retryable: bool = True
    """失败是否可重试（仅 `failed` 有意义；默认异常 / 失败可重试）。"""

    @classmethod
    def success(cls, output: ConcurrentStableDict[str, object] | None = None, message: str = "") -> JobResult:
        """构造成功结果。

        Args:
            output: 输出摘要（JSON 对象）。
            message: 说明。

        Returns:
            JobResult: 成功结果。
        """
        return cls(status="succeeded", message=message, output=output)

    @classmethod
    def failed(
        cls,
        message: str,
        *,
        retryable: bool = True,
        output: ConcurrentStableDict[str, object] | None = None,
    ) -> JobResult:
        """构造失败结果。

        Args:
            message: 失败摘要。
            retryable: 是否可重试（默认 True；业务明确失败传 False）。
            output: 附加输出。

        Returns:
            JobResult: 失败结果。
        """
        return cls(status="failed", message=message, output=output, retryable=retryable)

    @classmethod
    def canceled(cls, message: str = "") -> JobResult:
        """构造取消结果（handler 在批次边界发现取消后返回）。

        Args:
            message: 取消原因。

        Returns:
            JobResult: 取消结果。
        """
        return cls(status="canceled", message=message)


class BaseJobHandler(BasePluggable, ABC):
    """产品默认扩展基类：声明作业类型并实现 `run(ctx)`。

    产品侧最小接入面 = 声明 `[[jobs]]` + 继承本类实现 `run`；公共执行语义由基座提供。
    """

    key: str = "job_handler"
    """插件键（作业处理器能力域）。"""

    plugin_key: str = "job_handler"
    """能力域键。"""

    plugin_name: str = NULL_PLUGIN_NAME
    """插件名（端口缺省 null；具体实现由作业注册表按类型装配）。"""

    contract_version: str = DEFAULT_CONTRACT_VERSION
    """插件契约版本（与基座插件体系一致）。"""

    job_type: str = ""
    """作业类型（子类必须声明；与 `[[jobs]]` 声明一致）。"""

    description: str = ""
    """说明（供目录展示；缺省取声明）。"""

    @abstractmethod
    async def run(self, ctx: JobContext) -> JobResult:
        """执行作业（至少一次语义：必须幂等或以业务唯一约束兜底）。

        Args:
            ctx: 执行上下文。

        Returns:
            JobResult: 执行结果。
        """
