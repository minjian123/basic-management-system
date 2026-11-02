"""导出域接口契约：产物 / 异步受理 / 空结果 / 列表 PDF 结果 / 作业状态。"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from bms_core.schemas.base import BaseSchema, SnowflakeIdStr

__all__ = [
    "ExportArtifact",
    "ExportAsyncAccepted",
    "ExportEmptyResult",
    "ExportJobStatus",
    "ExportListPdfResult",
]


class ExportArtifact(BaseSchema):
    """导出产物（对象 key + 限时取址）。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    object_key: str = Field(description="产物对象 key（路径风格）")
    file_name: str = Field(description="文件名（含扩展名）")
    size: int = Field(ge=0, description="产物字节数")
    content_type: str = Field(description="内容类型")
    url: str | None = Field(default=None, description="限时取址（预签名失败时为空）")
    expires_in: int = Field(default=0, ge=0, description="取址有效期（秒）")


class ExportAsyncAccepted(BaseSchema):
    """异步受理结果（数据量超阈值时返回，不含文件流）。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    async_mode: bool = Field(default=True, alias="async", serialization_alias="async", description="恒为 true")
    job_id: SnowflakeIdStr = Field(description="导出作业主键")
    total: int = Field(ge=0, description="本次导出条数")
    status_url: str = Field(description="状态查询地址（相对路径）")
    message: str = Field(description="提示文案")


class ExportEmptyResult(BaseSchema):
    """空结果（0 行不生成空文件、不建作业）。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    empty: bool = Field(default=True, description="恒为 true")
    message: str = Field(description="提示文案")


class ExportListPdfResult(BaseSchema):
    """列表 PDF 同步结果（产物取址）。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    async_mode: bool = Field(default=False, alias="async", serialization_alias="async", description="恒为 false")
    total: int = Field(ge=0, description="本次导出条数")
    artifact: ExportArtifact | None = Field(default=None, description="产物（同步成功时非空）")


class ExportJobStatus(BaseSchema):
    """异步导出作业状态（终态含产物取址；产物过期时 artifact 为空）。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    job_id: SnowflakeIdStr = Field(description="作业主键")
    status: str = Field(description="作业状态（pending/running/success/failed/cancelled）")
    kind: str = Field(description="导出类型（excel/pdf）")
    biz: str = Field(description="业务标识")
    total: int = Field(default=0, ge=0, description="总条数")
    done: int = Field(default=0, ge=0, description="已完成条数（进度）")
    artifact: ExportArtifact | None = Field(default=None, description="产物（终态成功且未过期时非空）")
    message: str | None = Field(default=None, description="提示 / 失败原因摘要")
