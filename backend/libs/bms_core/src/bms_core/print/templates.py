"""打印导出能力域 · 内置模板来源（04_02）。

- `BuiltinPrintTemplateProvider`（插件名 `builtin`，由 `core/assembly.py` 的显式工厂登记）：模板清单与
  单模板定义来自**进程内注册表**，不读库、不渲染；表单定制（10_01）落地后换 provider 即可。
- `BuiltinTemplateRegistry`：进程内模板注册表（可独立实例化，便于测试与产品扩展）。
- `register_builtin_template`：扩展入口（产品仓 / 后续阶段追加模板；重名即拒）。

口径：内置模板只声明模板键 / 名称 / 单据类型；**变量清单为空**——单据字段由调用方随
`PrintDocument.fields` 传入，渲染器按实际键值渲染，不臆造字段。页眉 / 字段 / 明细列 / 签章的渲染定义
归表单定制（10_01），本模块不承载。
"""

from __future__ import annotations

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import PrintTemplateNotFoundError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.print.base import BasePrintTemplateProvider, PrintTemplateInfo

__all__ = [
    "BUILTIN_PRINT_TEMPLATES",
    "DEFAULT_DOCUMENT_TEMPLATE_KEY",
    "DEFAULT_LIST_TEMPLATE_KEY",
    "BuiltinPrintTemplateProvider",
    "BuiltinTemplateRegistry",
    "register_builtin_template",
]

DEFAULT_DOCUMENT_TEMPLATE_KEY = "generic_document"
"""通用单据模板键（单据打印缺省）。"""

DEFAULT_LIST_TEMPLATE_KEY = "generic_list"
"""通用列表模板键（列表 PDF 缺省）。"""


class BuiltinTemplateRegistry(BaseFrameworkObject):
    """内置模板注册表（进程内、导入期登记、运行期只读）。"""

    def __init__(self) -> None:
        """初始化并装入两条内置模板。"""
        self._templates: ConcurrentStableDict[str, PrintTemplateInfo] = ConcurrentStableDict()
        self._register(PrintTemplateInfo(key=DEFAULT_DOCUMENT_TEMPLATE_KEY, name="通用单据"))
        self._register(PrintTemplateInfo(key=DEFAULT_LIST_TEMPLATE_KEY, name="通用列表"))

    def _register(self, info: PrintTemplateInfo) -> PrintTemplateInfo:
        """登记模板（重名即拒）。

        Args:
            info: 模板定义。

        Returns:
            PrintTemplateInfo: 登记项。

        Raises:
            ValueError: 模板键为空或重复（构建期 fail-fast）。
        """
        key = info.key.strip()
        if not key:
            raise ValueError("内置打印模板键为空")
        if key in self._templates:
            raise ValueError(f"内置打印模板键重复：{key}")
        self._templates.set(key, info)
        return info

    def add(self, info: PrintTemplateInfo) -> PrintTemplateInfo:
        """追加模板（扩展入口）。

        Args:
            info: 模板定义。

        Returns:
            PrintTemplateInfo: 登记项。
        """
        return self._register(info)

    def all(self) -> ConcurrentStableFrozenList[PrintTemplateInfo]:
        """全部模板（按模板键排序，输出稳定）。

        Returns:
            ConcurrentStableFrozenList[PrintTemplateInfo]: 模板清单。
        """
        return ConcurrentStableFrozenList(self._templates[key] for key in sorted(self._templates))

    def get(self, template_key: str) -> PrintTemplateInfo:
        """按模板键取定义。

        Args:
            template_key: 模板键。

        Returns:
            PrintTemplateInfo: 模板定义。

        Raises:
            PrintTemplateNotFoundError: 未命中（50201 / 404）。
        """
        info = self._templates.get(template_key)
        if info is None:
            raise PrintTemplateNotFoundError(f"打印模板不存在：{template_key}")
        return info


_REGISTRY = BuiltinTemplateRegistry()

BUILTIN_PRINT_TEMPLATES: ConcurrentStableFrozenList[PrintTemplateInfo] = _REGISTRY.all()
"""内置模板清单（两条：通用单据 / 通用列表）。"""


def register_builtin_template(info: PrintTemplateInfo) -> PrintTemplateInfo:
    """追加内置模板（产品仓 / 后续阶段扩展入口；重名即拒）。

    Args:
        info: 模板定义。

    Returns:
        PrintTemplateInfo: 登记项。

    Raises:
        ValueError: 模板键为空或重复。
    """
    return _REGISTRY.add(info)


class BuiltinPrintTemplateProvider(BasePrintTemplateProvider):
    """内置模板来源：清单与单模板定义取自进程内注册表。"""

    # 由 `core/assembly.py` 的显式工厂登记为 `print_template:builtin`；置空避免自动登记重名。
    plugin_name = ""

    async def list(self, *, biz_type: str | None = None) -> ConcurrentStableList[PrintTemplateInfo]:
        """取打印模板清单（可按单据类型过滤）。

        Args:
            biz_type: 单据类型（None 表示全部）。

        Returns:
            ConcurrentStableList[PrintTemplateInfo]: 模板清单。
        """
        templates = _REGISTRY.all()
        if biz_type is None:
            return ConcurrentStableList(templates)
        return ConcurrentStableList(item for item in templates if item.biz_type in (None, biz_type))

    async def get(self, template_key: str) -> PrintTemplateInfo:
        """取单模板定义。

        Args:
            template_key: 模板键。

        Returns:
            PrintTemplateInfo: 模板定义。

        Raises:
            PrintTemplateNotFoundError: 未命中（50201 / 404）。
        """
        return _REGISTRY.get(template_key)
