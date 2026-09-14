"""导入导出能力域 · 共享数据契约：列定义（导入解析与导出列定义共用）。"""

from dataclasses import dataclass

__all__ = ["ColumnSpec"]


@dataclass(frozen=True)
class ColumnSpec:
    """列定义（导入期望列 / 导出输出列共用）。"""

    key: str
    """字段键（与数据行字段名对应）。"""

    title: str
    """表头标题（文件首行展示）。"""

    required: bool = False
    """是否必填（导入按此校验必填缺失）。"""
