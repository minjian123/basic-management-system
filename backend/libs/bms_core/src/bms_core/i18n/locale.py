"""国际化语言元数据：清单条目值对象与 `Accept-Language` 解析纯函数。

- `LocaleInfo`：语言清单条目（`code` / `name` / `rtl` / `is_default` / `status` / `sort`），只读值对象。
- `match_locale`：按 `Accept-Language` 顺序匹配支持清单（精确命中优先、再按主语言前缀），
  无命中回退默认语言；纯函数、无 IO，供同步解析路径复用。
- locale 一律 IETF 标准形态（`zh-CN` / `en-US` / `ar-SA`），**比较大小写不敏感**；
  返回值取清单里的原始形态（不自行改写大小写）。
"""

from collections.abc import Iterable
from dataclasses import dataclass

from bms_core.core.objects import BaseValueObject

__all__ = ["LocaleInfo", "match_locale"]

LOCALE_ENABLED = "enabled"
"""语言状态：启用。"""

LOCALE_DISABLED = "disabled"
"""语言状态：停用。"""


@dataclass(frozen=True)
class LocaleInfo(BaseValueObject):
    """语言清单条目（只读）。"""

    code: str
    """语言标识（IETF 标准形态，如 `zh-CN`）。"""

    name: str = ""
    """语言名称（本地名，如 `简体中文`）。"""

    rtl: bool = False
    """是否从右到左（驱动前端布局方向）。"""

    is_default: bool = False
    """是否系统默认语言（全清单恰一条）。"""

    status: str = LOCALE_ENABLED
    """状态（`enabled` / `disabled`）。"""

    sort: int = 0
    """排序（升序）。"""

    @property
    def enabled(self) -> bool:
        """是否启用。

        Returns:
            bool: 启用为 True。
        """
        return self.status == LOCALE_ENABLED


def match_locale(accept_language: str | None, supported: Iterable[str], default: str) -> str:
    """按 `Accept-Language` 匹配支持清单。

    匹配顺序：逐个语言标签（按客户端优先级）→ 精确命中（大小写不敏感）→ 主语言前缀命中 → 默认语言。

    Args:
        accept_language: 请求头原值（可空）。
        supported: 支持的语言清单（插入序）。
        default: 默认语言（无命中时返回）。

    Returns:
        str: 命中语言（清单原始形态）或默认语言。
    """
    for part in (accept_language or "").split(","):
        tag = part.split(";")[0].strip()
        if not tag:
            continue
        lowered = tag.lower()
        for code in supported:
            if code.lower() == lowered:
                return code
        prefix = lowered.split("-")[0]
        for code in supported:
            if code.split("-")[0].lower() == prefix:
                return code
    return default
