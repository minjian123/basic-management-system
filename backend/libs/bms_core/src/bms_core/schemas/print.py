"""打印与导出 PDF 占位路由的请求 / 响应契约（与 `app/print/` 能力域契约字段一一对应）。

- `PrintDocumentPayload` / `PrintOptionsPayload`：单据数据与渲染选项（对应能力域 `PrintDocument` / `PrintOptions`）。
- `PrintExportRequest` / `PrintBatchRequest`：单条导出与批量打印请求。
- `PrintExportResponse` / `PrintBatchResponse`：导出产物与批量结果响应。
- `PrintVariableResponse` / `PrintTemplateInfoResponse` / `PrintTemplateListResponse`：模板变量、模板定义与清单响应。

口径：路由契约与能力域契约**字段名一致**，由路由层显式映射（不隐式透传字典），保证 OpenAPI 契约稳定；
字段一律 snake_case（前端 camelCase 契约由宿主数据通路注入层映射）。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema

__all__ = [
    "PrintBatchRequest",
    "PrintBatchResponse",
    "PrintDocumentPayload",
    "PrintExportRequest",
    "PrintExportResponse",
    "PrintOptionsPayload",
    "PrintTemplateInfoResponse",
    "PrintTemplateListResponse",
    "PrintVariableResponse",
]


class PrintDocumentPayload(BaseSchema):
    """单据数据（单据键 + 主表字段 + 明细行）。"""

    biz_key: str | None = Field(default=None, description="单据键（产物 key / 文件名派生用）")
    fields: dict[str, object] = Field(default_factory=dict[str, object], description="主表字段")
    rows: list[dict[str, object]] = Field(default_factory=list[dict[str, object]], description="明细行")


class PrintOptionsPayload(BaseSchema):
    """渲染选项（纸张 / 方向 / 色调 / 水印 / 打印人）。"""

    paper: str = Field(default="A4", description="纸张（A4 / A5 / custom）")
    orientation: str = Field(default="portrait", description="纸张方向（portrait 纵向 / landscape 横向）")
    tone: str = Field(default="color", description="打印色调（color 彩色 / mono 黑白）")
    watermark: str = Field(default="", description="水印文案")
    printed_by: str | None = Field(default=None, description="打印人")


class PrintExportRequest(BaseSchema):
    """单条导出 PDF 请求：`{template_key, document, options?}`。"""

    template_key: str = Field(min_length=1, description="打印模板键")
    document: PrintDocumentPayload = Field(description="单据数据")
    options: PrintOptionsPayload | None = Field(default=None, description="渲染选项（缺省取平台缺省）")


class PrintBatchRequest(BaseSchema):
    """批量打印请求：`{template_key, keys, mode?, options?}`。"""

    template_key: str = Field(min_length=1, description="打印模板键")
    keys: list[str] = Field(min_length=1, description="单据键集合（至少一条）")
    mode: str = Field(default="separate", description="批量模式（separate 逐份 / merged 合并）")
    options: PrintOptionsPayload | None = Field(default=None, description="渲染选项（缺省取平台缺省）")


class PrintExportResponse(BaseSchema):
    """导出产物响应。"""

    object_key: str = Field(description="产物对象 key")
    file_id: str | None = Field(default=None, description="文件标识（真实实现回填）")
    file_name: str = Field(description="文件名（含 .pdf）")
    size: int = Field(ge=0, description="产物字节数")
    content_type: str = Field(description="内容类型")
    url: str | None = Field(default=None, description="限时取址")
    expires_in: int = Field(ge=0, description="地址有效期（秒）")
    message: str | None = Field(default=None, description="结果提示文案")


class PrintBatchResponse(BaseSchema):
    """批量打印结果响应。"""

    task_id: str | None = Field(default=None, description="后台任务标识（超阈值转后台时非空）")
    total: int = Field(ge=0, description="单据总数")
    succeeded: int = Field(ge=0, description="成功单据数")
    failed: int = Field(ge=0, description="失败单据数")
    items: list[PrintExportResponse] = Field(description="产物明细（逐份多份 / 合并单份）")
    message: str | None = Field(default=None, description="结果提示文案")


class PrintVariableResponse(BaseSchema):
    """模板变量响应。"""

    key: str = Field(description="变量键")
    label: str = Field(description="变量标签")


class PrintTemplateInfoResponse(BaseSchema):
    """打印模板定义响应。"""

    key: str = Field(description="模板键")
    name: str = Field(description="模板名称")
    biz_type: str | None = Field(default=None, description="单据类型（缺省不限）")
    variables: list[PrintVariableResponse] = Field(description="变量清单")
    status: str = Field(description="模板状态（active 启用 / disabled 停用）")


class PrintTemplateListResponse(BaseSchema):
    """打印模板清单响应。"""

    templates: list[PrintTemplateInfoResponse] = Field(description="模板清单")
