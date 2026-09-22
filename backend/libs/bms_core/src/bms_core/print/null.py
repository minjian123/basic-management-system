"""print_template / print_exporter 能力域缺省实现（Null Object）：固定返回，不触对象存储、不写库、不渲染。

- `NullPrintTemplateProvider`：模板清单固定为空（不臆造模板定义）；取模板恒定未命中（`50201` / 404）。
- `NullPrintExporter`：单条导出与批量打印固定返回占位产物（对象 key 经统一助手派生、占位取址与占位文案）；
  产物有效期复用对象存储缺省预签名有效期，不新建平行常量。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import PrintTemplateNotFoundError
from bms_core.print.base import (
    NULL_PRINT_BIZ_KEY,
    NULL_PRINT_URL,
    PRINT_BATCH_MODES,
    PRINT_CONTENT_TYPE,
    PRINT_PLACEHOLDER_MESSAGE,
    BasePrintExporter,
    BasePrintTemplateProvider,
    PrintBatchResult,
    PrintDocument,
    PrintExportResult,
    PrintOptions,
    PrintTemplateInfo,
    build_print_object_key,
)
from bms_core.storage.base import DEFAULT_PRESIGN_TTL

__all__ = ["NullPrintExporter", "NullPrintTemplateProvider"]


class NullPrintTemplateProvider(BasePrintTemplateProvider, BaseNullObject):
    """占位打印模板来源：清单固定为空、取模板恒定未命中（不臆造模板定义）。"""

    async def list(self, *, biz_type: str | None = None) -> list[PrintTemplateInfo]:
        """取打印模板清单（占位固定空清单，不区分单据类型）。

        Args:
            biz_type: 单据类型（占位忽略）。

        Returns:
            list[PrintTemplateInfo]: 空清单。
        """
        return []

    async def get(self, template_key: str) -> PrintTemplateInfo:
        """取单模板定义（占位恒定未命中）。

        Args:
            template_key: 打印模板键。

        Raises:
            PrintTemplateNotFoundError: 模板键未命中（50201 / 404）。
        """
        raise PrintTemplateNotFoundError(f"打印模板不存在：{template_key}")


class NullPrintExporter(BasePrintExporter, BaseNullObject):
    """占位打印导出：固定返回占位产物（不触对象存储、不写库、不渲染）。"""

    async def export_pdf(
        self,
        template_key: str,
        document: PrintDocument,
        *,
        options: PrintOptions | None = None,
    ) -> PrintExportResult:
        """导出单条单据 PDF 产物（占位固定返回占位产物）。

        Args:
            template_key: 打印模板键。
            document: 单据数据（单据键缺省时回落 `NULL_PRINT_BIZ_KEY`）。
            options: 渲染选项（占位不消费）。

        Returns:
            PrintExportResult: 占位产物。
        """
        biz_key = document.biz_key or NULL_PRINT_BIZ_KEY
        return self._artifact(template_key, biz_key, f"{template_key}.pdf")

    async def batch_print(
        self,
        keys: list[str],
        *,
        template_key: str,
        mode: str = "separate",
        options: PrintOptions | None = None,
    ) -> PrintBatchResult:
        """批量打印多单据（占位固定返回占位产物汇总）。

        Args:
            keys: 单据键集合（空集合返回空汇总，零副作用）。
            template_key: 打印模板键。
            mode: 批量模式（separate 逐份出多份产物 / merged 合并出单份产物）。
            options: 渲染选项（占位不消费）。

        Returns:
            PrintBatchResult: 占位批量结果（汇总计数为单据数、任务标识为空）。
        """
        if not keys:
            return PrintBatchResult(message=PRINT_PLACEHOLDER_MESSAGE)
        if mode == PRINT_BATCH_MODES[1]:  # merged：合并单份产物，以批内首个单据键为标识
            items = [self._artifact(template_key, keys[0], f"{template_key}.pdf")]
        else:  # separate：逐份产物，逐键命名
            items = [self._artifact(template_key, key, f"{template_key}-{key}.pdf") for key in keys]
        return PrintBatchResult(
            total=len(keys),
            succeeded=len(keys),
            failed=0,
            items=items,
            message=PRINT_PLACEHOLDER_MESSAGE,
        )

    @staticmethod
    def _artifact(template_key: str, biz_key: str, file_name: str) -> PrintExportResult:
        """构造占位产物（单条导出与批量打印共用）。

        Args:
            template_key: 打印模板键。
            biz_key: 单据键（产物对象 key 末段）。
            file_name: 产物文件名。

        Returns:
            PrintExportResult: 占位产物（占位取址与占位文案）。
        """
        return PrintExportResult(
            object_key=build_print_object_key(template_key=template_key, biz_key=biz_key),
            file_name=file_name,
            content_type=PRINT_CONTENT_TYPE,
            url=NULL_PRINT_URL,
            expires_in=DEFAULT_PRESIGN_TTL,
            message=PRINT_PLACEHOLDER_MESSAGE,
        )
