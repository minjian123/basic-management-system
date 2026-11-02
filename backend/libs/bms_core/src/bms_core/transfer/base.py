"""导入导出能力域 · 共享数据契约：列定义（导入解析与导出列定义共用）。"""

from dataclasses import dataclass, field

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.objects import BaseFieldSpecContract

__all__ = ["COLUMN_VALUE_TYPES", "ColumnSpec"]

COLUMN_VALUE_TYPES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    ("text", "int", "number", "bool", "date", "datetime")
)
"""通用列值类型（导入预检使用；枚举 label 反查归业务定义）。"""


@dataclass(frozen=True)
class ColumnSpec(BaseFieldSpecContract):
    """列定义（导入期望列 / 导出输出列共用）。

    前三个字段是历史口径；其余字段为 04_01 新增的可选校验 / 模板说明字段，全部有默认值，
    导出侧零影响。
    """

    key: str
    """字段键（与数据行字段名对应）。"""

    title: str
    """表头标题（文件首行展示）。"""

    required: bool = False
    """是否必填（导入按此校验必填缺失）。"""

    max_length: int | None = None
    """文本最大长度；None 不限制。"""

    value_type: str = "text"
    """通用读值类型，取值见 `COLUMN_VALUE_TYPES`。"""

    pattern: str | None = None
    """可选正则（如账号 / 邮箱 / 手机号）；None 不校验。"""

    choices: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList[str]())
    """可选值（模板下拉 + 通用预检）；空表示不限制。"""

    note: str = ""
    """填写说明（模板「填写说明」sheet）。"""

    example: str = ""
    """示例（只进说明 sheet，不进数据 sheet）。"""
