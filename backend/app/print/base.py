"""打印模板与导出 PDF 能力域：模板来源与导出两契约（真实渲染 / 模板来源 / 产物落存储随对应阶段回补）。

- 取值集合：纸张 `PRINT_PAPERS`（A4 / A5 / 自定义）、方向 `PRINT_ORIENTATIONS`（纵向 / 横向）、
  色调 `PRINT_TONES`（彩色 / 黑白）、批量模式 `PRINT_BATCH_MODES`（逐份 / 合并）、
  模板状态 `PRINT_TEMPLATE_STATUSES`（启用 / 停用）。
- 产物口径：内容类型 `PRINT_CONTENT_TYPE`（高保真 PDF）、缺省纸张 `DEFAULT_PAPER`、对象 key 域段
  `PRINT_OBJECT_DOMAIN`；对象 key 一律由 `build_print_object_key` 派生（租户缺省位复用全局租户位常量）。
- 占位常量：`PRINT_PLACEHOLDER_MESSAGE`（占位提示文案）、`NULL_PRINT_URL`（占位取址）、
  `NULL_PRINT_BIZ_KEY`（单据键缺省位）。
- 数据契约：`PrintVariable`（模板变量）/ `PrintTemplateInfo`（模板定义）/ `PrintDocument`（单据数据）/
  `PrintOptions`（渲染选项）/ `PrintExportResult`（导出产物）/ `PrintBatchResult`（批量结果）。
- `BasePrintTemplateProvider`（`key = "print_template"`）：异步 `list` / `get`——模板定义来源
  （模板键 / 变量清单），只输出模板元数据、不含渲染结构。
- `BasePrintExporter`（`key = "print_exporter"`）：异步 `export_pdf` / `batch_print`——按模板键与单据数据
  产出产物；产物经对象存储出口落库并以限时取址下发，后端不代理文件流。
- 提供者 `get_print_template_provider` / `get_print_exporter`（应用级单例；公共依赖经
  `app/api/deps.py` 统一导出）。

口径：打印与导出**只经本能力域出口**——业务与前端不得自接 PDF 引擎、自建模板来源或自拼产物 key；
模板来源与渲染分层（来源只出模板元数据，导出只按模板键 + 单据数据产出，不反向读取渲染定义）；
批量超阈值转后台任务（任务标识 + 完成后限时下载）归后续阶段。错误码落文件段（`5xxxx`）打印子段
（`502xx`，见 `app/core/error_codes.py`）。真实渲染引擎 / 模板落库来源 / 产物落存储与取址随通用能力、
表单定制与文件管理阶段回补。
"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request
from pydantic import Field

from app.cache.base import GLOBAL_TENANT
from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_PAPER",
    "NULL_PRINT_BIZ_KEY",
    "NULL_PRINT_URL",
    "PRINT_BATCH_MODES",
    "PRINT_CONTENT_TYPE",
    "PRINT_OBJECT_DOMAIN",
    "PRINT_ORIENTATIONS",
    "PRINT_PAPERS",
    "PRINT_PLACEHOLDER_MESSAGE",
    "PRINT_TEMPLATE_STATUSES",
    "PRINT_TONES",
    "BasePrintExporter",
    "BasePrintTemplateProvider",
    "PrintBatchResult",
    "PrintDocument",
    "PrintExportResult",
    "PrintOptions",
    "PrintTemplateInfo",
    "PrintVariable",
    "build_print_object_key",
    "get_print_exporter",
    "get_print_template_provider",
]

PRINT_PAPERS: tuple[str, ...] = ("A4", "A5", "custom")
"""纸张取值集合（A4 / A5 / 自定义，对齐前端纸张名三取值）。"""

PRINT_ORIENTATIONS: tuple[str, ...] = ("portrait", "landscape")
"""纸张方向取值集合（纵向 / 横向）。"""

PRINT_TONES: tuple[str, ...] = ("color", "mono")
"""打印色调取值集合（彩色 / 黑白）。"""

PRINT_BATCH_MODES: tuple[str, ...] = ("separate", "merged")
"""批量模式取值集合（逐份 / 合并）。"""

PRINT_TEMPLATE_STATUSES: tuple[str, ...] = ("active", "disabled")
"""打印模板状态取值集合（启用 / 停用）。"""

PRINT_CONTENT_TYPE = "application/pdf"
"""产物内容类型（高保真 PDF）。"""

DEFAULT_PAPER = "A4"
"""缺省纸张（未声明时按 A4 纵向）。"""

PRINT_PLACEHOLDER_MESSAGE = "导出未就绪（占位）"
"""占位产物提示文案（与前端占位文案同口径）。"""

NULL_PRINT_URL = "null-print-url"
"""占位产物取址（占位实现不触对象存储，固定返回；便于断言）。"""

NULL_PRINT_BIZ_KEY = "null"
"""单据键缺省位（单据数据未带单据键时，产物对象 key 的末段）。"""

PRINT_OBJECT_DOMAIN = "prints"
"""产物对象 key 的域段。"""


def build_print_object_key(*, template_key: str, biz_key: str, tenant: str | None = None) -> str:
    """构建产物对象 key（格式 `bms:{租户|global}:prints:{模板键}:{单据键}`）。

    Args:
        template_key: 打印模板键。
        biz_key: 单据键（单条导出 / 批量打印的产物标识）。
        tenant: 租户标识；None 表示全局租户位（真实实现按解析链租户传入）。

    Returns:
        str: 产物对象 key（业务与前端不得自拼）。
    """
    return f"bms:{tenant or GLOBAL_TENANT}:{PRINT_OBJECT_DOMAIN}:{template_key}:{biz_key}"


class PrintVariable(BaseSchema):
    """模板变量（变量键与前端展示标签）。"""

    key: str = Field(description="变量键（与单据数据字段键对应）")
    label: str = Field(description="变量标签（前端展示名）")


class PrintTemplateInfo(BaseSchema):
    """打印模板定义（模板键 / 名称 / 单据类型 / 变量清单 / 状态）。"""

    key: str = Field(description="模板键（业务与模板来源的唯一对接标识）")
    name: str = Field(description="模板名称")
    biz_type: str | None = Field(default=None, description="单据类型（缺省不限）")
    variables: list[PrintVariable] = Field(default_factory=list[PrintVariable], description="变量清单")
    status: str = Field(default="active", description="模板状态（active 启用 / disabled 停用）")


class PrintDocument(BaseSchema):
    """单据数据（单据键 + 主表字段 + 明细行）。"""

    biz_key: str | None = Field(default=None, description="单据键（产物 key / 文件名派生与归档审计关联用）")
    fields: dict[str, object] = Field(default_factory=dict[str, object], description="主表字段（键与模板变量键对应）")
    rows: list[dict[str, object]] = Field(default_factory=list[dict[str, object]], description="明细行")


class PrintOptions(BaseSchema):
    """渲染选项（纸张 / 方向 / 色调 / 水印 / 打印人）。"""

    paper: str = Field(default=DEFAULT_PAPER, description="纸张（A4 / A5 / custom）")
    orientation: str = Field(default="portrait", description="纸张方向（portrait 纵向 / landscape 横向）")
    tone: str = Field(default="color", description="打印色调（color 彩色 / mono 黑白）")
    watermark: str = Field(default="", description="水印文案（单据级标签与用户 / 租户信息拼接后下发）")
    printed_by: str | None = Field(default=None, description="打印人（页脚留痕；打印时间由服务端生成）")


class PrintExportResult(BaseSchema):
    """导出产物（对象存储 + 限时取址；字段对齐前端冻结结果）。"""

    object_key: str = Field(description="产物对象 key（经 build_print_object_key 派生）")
    file_id: str | None = Field(default=None, description="文件标识（真实实现回填文件主键字符串）")
    file_name: str = Field(description="文件名（含 .pdf）")
    size: int = Field(default=0, ge=0, description="产物字节数")
    content_type: str = Field(default=PRINT_CONTENT_TYPE, description="内容类型")
    url: str | None = Field(default=None, description="限时取址（真实实现为限时预签名地址）")
    expires_in: int = Field(default=0, ge=0, description="地址有效期（秒）")
    message: str | None = Field(default=None, description="结果提示文案")


class PrintBatchResult(BaseSchema):
    """批量打印结果（任务标识 + 汇总计数 + 产物明细）。"""

    task_id: str | None = Field(default=None, description="后台任务标识（超阈值转后台时非空）")
    total: int = Field(default=0, ge=0, description="单据总数")
    succeeded: int = Field(default=0, ge=0, description="成功单据数")
    failed: int = Field(default=0, ge=0, description="失败单据数")
    items: list[PrintExportResult] = Field(
        default_factory=list[PrintExportResult], description="产物明细（逐份多份 / 合并单份）"
    )
    message: str | None = Field(default=None, description="结果提示文案")


class BasePrintTemplateProvider(BasePluggable, ABC):
    """打印模板来源契约：模板清单与单模板定义（模板键 / 变量清单）。"""

    key: str = "print_template"
    plugin_key: str = "print_template"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def list(self, *, biz_type: str | None = None) -> list[PrintTemplateInfo]:
        """取打印模板清单（可按单据类型过滤）。

        Args:
            biz_type: 单据类型（None 表示全部）。

        Returns:
            list[PrintTemplateInfo]: 模板清单（占位为空清单，消费方以空态回退）。
        """

    @abstractmethod
    async def get(self, template_key: str) -> PrintTemplateInfo:
        """取单模板定义（含变量清单）。

        Args:
            template_key: 打印模板键。

        Returns:
            PrintTemplateInfo: 模板定义。

        Raises:
            PrintTemplateNotFoundError: 模板键未命中（50201 / 404）。
        """


class BasePrintExporter(BasePluggable, ABC):
    """打印导出契约：单条导出 PDF 与批量打印（产物经对象存储、限时取址）。"""

    key: str = "print_exporter"
    plugin_key: str = "print_exporter"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def export_pdf(
        self,
        template_key: str,
        document: PrintDocument,
        *,
        options: PrintOptions | None = None,
    ) -> PrintExportResult:
        """导出单条单据 PDF 产物。

        Args:
            template_key: 打印模板键。
            document: 单据数据（单据键 / 主表字段 / 明细行）。
            options: 渲染选项（None 表示按平台缺省）。

        Returns:
            PrintExportResult: 导出产物（对象 key / 限时取址 / 提示）。
        """

    @abstractmethod
    async def batch_print(
        self,
        keys: list[str],
        *,
        template_key: str,
        mode: str = "separate",
        options: PrintOptions | None = None,
    ) -> PrintBatchResult:
        """批量打印多单据（逐份 / 合并）。

        Args:
            keys: 单据键集合。
            template_key: 打印模板键。
            mode: 批量模式（separate 逐份 / merged 合并；取值 ∈ `PRINT_BATCH_MODES`）。
            options: 渲染选项（None 表示按平台缺省）。

        Returns:
            PrintBatchResult: 批量结果（任务标识 / 汇总计数 / 产物明细）。
        """


def get_print_template_provider(request: Request) -> BasePrintTemplateProvider:
    """取应用级打印模板来源（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BasePrintTemplateProvider: 应用装配的模板来源实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BasePrintTemplateProvider",
        resolve_plugin(
            "print_template",
            settings.print_template.provider,
            expected_version=BasePrintTemplateProvider.contract_version,
        ),
    )


def get_print_exporter(request: Request) -> BasePrintExporter:
    """取应用级打印导出（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BasePrintExporter: 应用装配的打印导出实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BasePrintExporter",
        resolve_plugin(
            "print_exporter",
            settings.print_exporter.provider,
            expected_version=BasePrintExporter.contract_version,
        ),
    )
