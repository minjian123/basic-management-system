"""种子编排端点契约（07B `02_03`）。"""

from pydantic import BaseModel, Field

__all__ = ["SeedOrchestrationRequestSchema", "SeedOrchestrationResultSchema"]


class SeedOrchestrationRequestSchema(BaseModel):
    """编排请求（内部端点入参）。"""

    tenant: str = Field(default="", description="目标租户；空串取 [platform_tenant].code")
    only: list[str] = Field(default_factory=list, description="只执行这些种子（空表示不限制）")
    skip: list[str] = Field(default_factory=list, description="跳过这些种子")
    require: list[str] = Field(default_factory=list, description="人工强制前置（必须在本批之前完成）")
    dry_run: bool = Field(default=False, description="只做装载 + 排序 + 冲突预检，不开事务不执行")
    timeout_seconds: float = Field(default=300.0, description="全局事务超时（秒）")


class SeedOrchestrationResultSchema(BaseModel):
    """编排结果（内部端点出参）。"""

    exitCode: int = Field(default=0, description="退出码（0/1/2/3/64）")
    reports: list[dict] = Field(default_factory=list, description="逐项报告")
    errors: list[str] = Field(default_factory=list, description="前置错误（退出码 3 时）")
    conflicts: list[str] = Field(default_factory=list, description="数据冲突明细（退出码 1 时）")
    warnings: list[str] = Field(default_factory=list, description="警示")
