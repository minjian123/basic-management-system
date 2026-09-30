"""数据脱敏能力域：真实实现（内置规则分派 + 自定义策略 + 受权限约束的明文揭示）。

- `MaskSpec` / `BUILTIN_MASK_SPECS`：内置策略规格（保留前段位数 / 保留后段位数 / 固定掩码字符数）。
- `mask_edges` / `mask_email`：掩码纯函数（无 IO、无正则扫描，可并发调用）。
- `MaskerOptions`：`[masking].options` 解析与校验载体（`mask_char` + `rules`）。
- `DefaultMasker`（`plugin_name = "default"`）：字段 → 策略分派、明文判定 **fail-closed**
  （注入占位权限检查器时一律按「无权限码」处理；RBAC 就绪注入真实检查器后自动按 `data:plain` 放行，
  脱敏侧零改动）。

规则口径：保留首尾类策略使用**固定掩码字符数**（不随被掩码字符数变化，不泄露真实长度）；长度不足时
退化为「保留可用前段 + 掩码」（不原样回显、不抛错）；未注册字段与 `None` 原样返回；未知策略名兜底
全掩码。示例与退化表见《后端基类清单》「数据脱敏」条目规则清单与任务详细设计。
"""

from dataclasses import dataclass, field
from typing import Self

from bms_core.core.capability import BasePlaceholder
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import PluginError
from bms_core.core.objects import BaseOptionsContract, BaseValueObject
from bms_core.masking.base import BaseMasker
from bms_core.permission.base import BasePermissionChecker

__all__ = [
    "BUILTIN_MASK_SPECS",
    "DEFAULT_MASK_CHAR",
    "EMAIL_MASK_STARS",
    "DefaultMasker",
    "MaskSpec",
    "MaskerOptions",
    "mask_edges",
    "mask_email",
]

DEFAULT_MASK_CHAR = "*"
"""缺省掩码字符。"""

OPTION_MASK_CHAR = "mask_char"
"""配置选项键：掩码字符。"""

OPTION_RULES = "rules"
"""配置选项键：字段名 → 策略名映射。"""

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


@dataclass(frozen=True)
class MaskerOptions(BaseOptionsContract):
    """`[masking].options` 解析结果：掩码字符 + 启动期字段 → 策略映射。"""

    mask_char: str = DEFAULT_MASK_CHAR
    """掩码字符（单字符）。"""

    rules: ConcurrentStableDict[str, str] = field(default_factory=ConcurrentStableDict[str, str])
    """字段名 → 策略名映射（缺省空）。"""

    @classmethod
    def from_options(cls, options: ConcurrentStableDict[str, object] | None = None) -> Self:
        """解析并校验配置选项（缺省回落）；非法取值**不静默**。

        Args:
            options: `[masking].options`（插入序；可为 None）。

        Returns:
            MaskerOptions: 解析结果。

        Raises:
            PluginError: 掩码字符非单字符 / 规则表非映射 / 字段名或策略名非非空字符串（40002）。
        """
        values: ConcurrentStableDict[str, object] = options or ConcurrentStableDict()
        return cls(
            mask_char=cls._single_char_option(values, OPTION_MASK_CHAR, DEFAULT_MASK_CHAR),
            rules=cls._mapping_option(values, OPTION_RULES),
        )


class DefaultMasker(BaseMasker):
    """真实脱敏实现：内置规则分派 + 自定义策略 + 受权限约束的明文揭示。"""

    plugin_name: str = "default"

    def __init__(
        self,
        *,
        checker: BasePermissionChecker,
        mask_char: str = DEFAULT_MASK_CHAR,
        rules: ConcurrentStableDict[str, str] | None = None,
    ) -> None:
        """初始化真实脱敏实现。

        Args:
            checker: 权限检查器（**占位实现一律按「无权限码」处理**，见 `check_plain`）。
            mask_char: 掩码字符（单字符）。
            rules: 启动期字段 → 策略映射（经 `[masking].options.rules` 注入）。

        Raises:
            PluginError: 掩码字符非法（须为单字符，40002）。
        """
        super().__init__(checker=checker)
        if len(mask_char) != 1:
            raise PluginError("脱敏掩码字符非法（须为单字符）")
        self._mask_char = mask_char
        for field_name, strategy in (rules or ConcurrentStableDict[str, str]()).items():
            self.register(field_name, strategy)

    def check_plain(self) -> bool:
        """当前请求是否持 `data:plain`（明文查看）权限。

        本期口径「无权限码一律不解掩码」：注入的权限检查器为**占位实现**（`BasePlaceholder`，
        如 `NullPermissionChecker` 恒定允许）时一律视为不持权限码 → `False`（**fail-closed**）。

        Returns:
            bool: 持明文查看权限为 True。
        """
        if isinstance(self._checker, BasePlaceholder):
            return False
        return super().check_plain()

    def mask(self, field: str, value: object) -> object:
        """按字段策略掩码。

        未注册字段（未注册即非敏感）与 `None` **原样返回**；持 `data:plain` 时返回原值；
        否则按策略返回掩码字符串（非字符串值先 `str()`，出参恒为 `str`）。

        Args:
            field: 字段名。
            value: 原始值。

        Returns:
            object: 明文（有权限 / 未注册 / `None`）或掩码字符串。
        """
        if field not in self._rules or value is None:
            return value
        if self.check_plain():
            return value
        return self._apply(self._rules[field].strategy, str(value))

    def reveal(self, field: str, value: object) -> object:
        """明文揭示（受权限约束的明文读取路径）。

        本期无加密存储字段，故与 `mask` **语义对称**：持 `data:plain` 返回原值，否则返回掩码值
        （不引入解密 / 密钥，加解密随 04-3 扩展）。

        Args:
            field: 字段名。
            value: 存储值。

        Returns:
            object: 明文（有权限 / 未注册 / `None`）或掩码字符串。
        """
        return self.mask(field, value)

    def _apply(self, strategy: str, text: str) -> str:
        """按策略名解析掩码串（自定义策略 → 内置策略 → 兜底全掩码）。

        Args:
            strategy: 策略名（字段注册时登记；未知策略名兜底 `custom` 全掩码）。
            text: 待掩码文本（已 `str()`）。

        Returns:
            str: 掩码串。
        """
        custom = self._strategies.get(strategy)
        if custom is not None:
            return custom(text, self._mask_char)
        if strategy == "email":
            return mask_email(text, self._mask_char)
        spec = BUILTIN_MASK_SPECS.get(strategy) or BUILTIN_MASK_SPECS["custom"]
        return mask_edges(text, spec, self._mask_char)
