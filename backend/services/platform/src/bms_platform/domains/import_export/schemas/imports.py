"""导入域接口契约：执行结果 / 状态 / 错误项。"""

from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema, SnowflakeIdStr

__all__ = ["ImportErrorItem", "ImportExecuteResult", "ImportJobStatus"]


class ImportErrorItem(BaseSchema):
    """行错误项（`row` 为 Excel 行号；`column` 为字段键）。"""

    row: int = Field(description="Excel 行号（数据行，从 2 起）")
    column: str | None = Field(default=None, description="出错字段键（可空）")
    message: str = Field(description="错误原因")


class ImportExecuteResult(BaseSchema):
    """执行导入结果（同步 / 异步 / 幂等命中共用）。"""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        extra="forbid",
        populate_by_name=True,
    )

    total: int = Field(default=0, ge=0, description="数据行数")
    success_count: int = Field(default=0, ge=0, description="实际落库行数")
    fail_count: int = Field(default=0, ge=0, description="有错误的行数（按行去重）")
    blocked_count: int = Field(default=0, ge=0, description="合法但因整批拒绝未落库的行数")
    committed: bool = Field(default=False, description="是否已落库")
    errors: Annotated[ConcurrentStableList[ImportErrorItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="错误项（同步响应最多前 200 条）"
    )
    async_mode: bool = Field(
        default=False,
        alias="async",
        serialization_alias="async",
        description="是否已转异步作业",
    )
    job_id: SnowflakeIdStr | None = Field(default=None, description="作业主键（异步 / 幂等命中）")
    report_token: str | None = Field(default=None, description="错误明细 token（有错误时返回）")
    duplicate: bool = Field(default=False, description="是否命中幂等键、返回首次结果")


class ImportJobStatus(BaseSchema):
    """异步导入状态。"""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        extra="forbid",
        populate_by_name=True,
    )

    job_id: SnowflakeIdStr = Field(description="作业主键")
    status: str = Field(description="作业状态（queued/running/succeeded/failed/canceled/dead）")
    progress_done: int = Field(default=0, ge=0, description="已完成量")
    progress_total: int | None = Field(default=None, ge=0, description="总量（未知为 null）")
    total: int | None = Field(default=None, ge=0, description="数据行数（未终态为 null）")
    success_count: int | None = Field(default=None, ge=0, description="实际落库行数")
    fail_count: int | None = Field(default=None, ge=0, description="有错误的行数")
    blocked_count: int | None = Field(default=None, ge=0, description="合法但未落库的行数")
    committed: bool = Field(default=False, description="是否已落库")
    errors: Annotated[ConcurrentStableList[ImportErrorItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="前 N 条错误（默认 20，上限 200）"
    )
    report_token: str | None = Field(default=None, description="错误明细 token（有错误时返回）")
    message: str | None = Field(default=None, description="失败 / 取消原因或结果说明")
