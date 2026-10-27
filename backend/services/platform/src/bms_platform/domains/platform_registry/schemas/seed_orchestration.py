"""种子编排端点契约（07B `02_03`）。

**集合声明口径**：一律用插入序集合类（`ConcurrentStableList`）+ `CONTRACT_COLLECTION` 注解，
不用裸 `list` / `dict`（《后端开发规范》与裸集合护栏）。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema

__all__ = ["SeedOrchestrationRequestSchema", "SeedOrchestrationResultSchema"]

NameList = Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION]
"""种子名清单（插入序；端点契约集合）。"""

ReportList = Annotated[ConcurrentStableList[ConcurrentStableDict[str, object]], CONTRACT_COLLECTION]
"""逐项报告清单（插入序；每项为报告字段映射）。"""


class SeedOrchestrationRequestSchema(BaseSchema):
    """编排请求（内部端点入参）。"""

    tenant: str = Field(default="", description="目标租户；空串取 [platform_tenant].code")
    only: NameList = Field(default_factory=ConcurrentStableList, description="只执行这些种子（空表示不限制）")
    skip: NameList = Field(default_factory=ConcurrentStableList, description="跳过这些种子")
    require: NameList = Field(default_factory=ConcurrentStableList, description="人工强制前置（必须在本批之前完成）")
    dry_run: bool = Field(default=False, description="只做装载 + 排序 + 冲突预检，不开事务不执行")
    timeout_seconds: float = Field(default=300.0, description="全局事务超时（秒）")


class SeedOrchestrationResultSchema(BaseSchema):
    """编排结果（内部端点出参）。"""

    exitCode: int = Field(default=0, description="退出码（0/1/2/3/64）")
    reports: ReportList = Field(
        default_factory=lambda: ConcurrentStableList[ConcurrentStableDict[str, object]](),
        description="逐项报告",
    )
    errors: NameList = Field(default_factory=lambda: ConcurrentStableList[str](), description="前置错误（退出码 3 时）")
    conflicts: NameList = Field(
        default_factory=lambda: ConcurrentStableList[str](), description="数据冲突明细（退出码 1 时）"
    )
    warnings: NameList = Field(default_factory=lambda: ConcurrentStableList[str](), description="警示")
