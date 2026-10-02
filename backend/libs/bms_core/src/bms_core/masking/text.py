"""数据脱敏能力域：内置策略规格、掩码纯函数与文本掩码辅助。

- `MaskSpec` / `BUILTIN_MASK_SPECS`：内置策略规格（保留前段位数 / 保留后段位数 / 固定掩码字符数）；
- `mask_edges` / `mask_email`：边缘掩码与邮箱掩码纯函数（无 IO、无正则扫描，可并发调用）；
- `apply_builtin_strategy`：按内置策略名分派（`email` 特例 → 规格表 → 未命中兜底 `custom` 全掩码）；
- `mask_text`：单段文本掩码入口——供日志 / 审计 / `ai_chat_log` 等消费方在落库落文件前**显式给出策略**
  掩码（不做值探测，与 04_01「显式注册驱动」口径一致）。

规则口径、示例与退化表见《后端基类清单》「数据脱敏」条目；`masking/default.py` 再导出本模块规格与纯函数，
既有导入路径（`bms_core.masking.default`）保持不变。
"""

from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseValueObject

__all__ = [
    "BUILTIN_MASK_SPECS",
    "DEFAULT_MASK_CHAR",
    "EMAIL_MASK_STARS",
    "EMAIL_STRATEGY",
    "MaskSpec",
    "apply_builtin_strategy",
    "mask_edges",
    "mask_email",
    "mask_text",
]

DEFAULT_MASK_CHAR = "*"
"""缺省掩码字符。"""

EMAIL_STRATEGY = "email"
"""邮箱策略名（掩码规则为特殊分支，见 `mask_email`）。"""

EMAIL_MASK_STARS = 3
"""邮箱掩码固定字符数。"""


@dataclass(frozen=True)
class MaskSpec(BaseValueObject):
    """内置策略规格：保留前段位数 / 保留后段位数 / 固定掩码字符数。"""

    head: int
    """保留前段字符数。"""

    tail: int
    """保留后段字符数。"""

    stars: int
    """固定掩码字符数（不随被掩码字符数变化）。"""


BUILTIN_MASK_SPECS: ConcurrentStableDict[str, MaskSpec] = ConcurrentStableDict(
    {
        "phone": MaskSpec(head=3, tail=4, stars=4),
        "id_card": MaskSpec(head=6, tail=4, stars=8),
        "bank_card": MaskSpec(head=4, tail=4, stars=8),
        "name": MaskSpec(head=1, tail=0, stars=1),
        "address": MaskSpec(head=6, tail=0, stars=3),
        "custom": MaskSpec(head=0, tail=0, stars=3),
    }
)
"""内置策略规格（`email` 为特殊分支，见 `mask_email`）。"""


def mask_edges(text: str, spec: MaskSpec, mask_char: str = DEFAULT_MASK_CHAR) -> str:
    """保留首尾的通用掩码（长度不足退化为保留可用前段，不原样回显、不抛错）。

    Args:
        text: 待掩码文本。
        spec: 策略规格（保留前段 / 后段位数与固定掩码字符数）。
        mask_char: 掩码字符。

    Returns:
        str: 掩码结果；长度不足 `head + tail + 1` 时保留 `min(head, len - 1)` 个前段字符
        （空串与单字符退化为纯掩码串，绝不通原值）。
    """
    mask = mask_char * spec.stars
    if len(text) >= spec.head + spec.tail + 1:
        kept_tail = text[-spec.tail :] if spec.tail else ""
        return f"{text[: spec.head]}{mask}{kept_tail}"
    keep = min(spec.head, max(len(text) - 1, 0))
    return f"{text[:keep]}{mask}"


def mask_email(text: str, mask_char: str = DEFAULT_MASK_CHAR) -> str:
    """邮箱掩码：保留首字符与域名（`zhangsan@example.com` → `z***@example.com`）。

    本地部分为空（`@domain`）→ 仅保留域名；**无 `@`** 时退化为「首字符 + 掩码」
    （长度不足 2 退化为纯掩码串）。

    Args:
        text: 待掩码邮箱。
        mask_char: 掩码字符。

    Returns:
        str: 掩码结果。
    """
    mask = mask_char * EMAIL_MASK_STARS
    local, sep, domain = text.partition("@")
    if not sep:
        keep = min(1, max(len(text) - 1, 0))
        return f"{text[:keep]}{mask}"
    return f"{local[:1]}{mask}@{domain}"


def apply_builtin_strategy(strategy: str, text: str, mask_char: str = DEFAULT_MASK_CHAR) -> str:
    """按内置策略名分派掩码（未知策略名兜底 `custom` 全掩码，不抛错）。

    Args:
        strategy: 策略名（内置策略名见《后端基类清单》「数据脱敏」条目规则清单）。
        text: 待掩码文本（已 `str()`）。
        mask_char: 掩码字符。

    Returns:
        str: 掩码串。
    """
    if strategy == EMAIL_STRATEGY:
        return mask_email(text, mask_char)
    spec = BUILTIN_MASK_SPECS.get(strategy) or BUILTIN_MASK_SPECS["custom"]
    return mask_edges(text, spec, mask_char)


def mask_text(text: str, strategy: str = "custom", *, mask_char: str = DEFAULT_MASK_CHAR) -> str:
    """单段文本掩码（消费方显式给出策略；不做值探测 / 正则识别）。

    Args:
        text: 待掩码文本。
        strategy: 内置策略名（缺省 `custom` 全掩码）；自定义策略请走 `BaseMasker.mask`。
        mask_char: 掩码字符。

    Returns:
        str: 掩码串（未知策略名兜底 `custom`）。
    """
    return apply_builtin_strategy(strategy, text, mask_char)
