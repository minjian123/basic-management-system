"""数据脱敏能力域：真实实现（内置规则分派 + 自定义策略 + 受权限约束的明文揭示）。

- `MaskSpec` / `BUILTIN_MASK_SPECS` / `mask_edges` / `mask_email`：内置策略规格与掩码纯函数，定义在
  `masking/text.py`（**本模块再导出**，既有导入路径 `bms_core.masking.default` 不变）。
- `MaskerOptions`：`[masking].options` 解析与校验载体（`mask_char` + `rules`）。
- `DefaultMasker`（`plugin_name = "default"`）：字段 → 策略分派、明文判定 **fail-closed**
  （注入占位权限检查器时一律按「无权限码」处理；RBAC 就绪注入真实检查器后自动按 `data:plain` 放行，
  脱敏侧零改动）。

策略解析顺序：`[masking].options.rules` / 显式注册 > Schema 声明（`mask` 的 `strategy` 入参）>
字段名同名内置策略 > 未命中原样返回（未声明即非敏感）；未知策略名兜底 `custom` 全掩码（不抛错，
序列化期抛错会中断响应）。规则口径与退化表见《后端基类清单》「数据脱敏」条目与任务详细设计。
"""

from dataclasses import dataclass, field
from typing import Self

from bms_core.core.capability import BasePlaceholder
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import PluginError
from bms_core.core.objects import BaseOptionsContract
from bms_core.masking.base import MASK_STRATEGIES, BaseMasker
from bms_core.masking.text import (
    BUILTIN_MASK_SPECS,
    DEFAULT_MASK_CHAR,
    EMAIL_MASK_STARS,
    MaskSpec,
    apply_builtin_strategy,
    mask_edges,
    mask_email,
)
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

OPTION_MASK_CHAR = "mask_char"
"""配置选项键：掩码字符。"""

OPTION_RULES = "rules"
"""配置选项键：字段名 → 策略名映射。"""


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

    def mask(self, field: str, value: object, strategy: str | None = None) -> object:
        """按字段策略掩码。

        未声明且未注册字段（未声明即非敏感）与 `None` **原样返回**；持 `data:plain` 时返回原值；
        否则按解析出的策略返回掩码字符串（非字符串值先 `str()`，出参恒为 `str`）。

        策略解析顺序：`[masking].options.rules` / 显式注册 > `strategy` 入参（Schema 声明）>
        字段名同名内置策略 > 未命中原样返回。

        Args:
            field: 字段名。
            value: 原始值。
            strategy: 字段策略（序列化层按 `BaseSchema.masked_fields` 声明传入；缺省 None）。

        Returns:
            object: 明文（有权限 / 未声明 / `None`）或掩码字符串。
        """
        if value is None:
            return value
        resolved = self._resolve_strategy(field, strategy)
        if resolved is None:
            return value
        if self.check_plain():
            return value
        return self._apply(resolved, str(value))

    def reveal(self, field: str, value: object, strategy: str | None = None) -> object:
        """明文揭示（受权限约束的明文读取路径）。

        本期无加密存储字段，故与 `mask` **语义对称**：持 `data:plain` 返回原值，否则返回掩码值
        （不引入解密 / 密钥，加解密随 04-3 扩展）。

        Args:
            field: 字段名。
            value: 存储值。
            strategy: 字段策略（同 `mask`）。

        Returns:
            object: 明文（有权限 / 未声明 / `None`）或掩码字符串。
        """
        return self.mask(field, value, strategy)

    def _resolve_strategy(self, field: str, declared: str | None) -> str | None:
        """解析字段生效策略（未命中返回 None＝未声明即非敏感，原样返回）。

        Args:
            field: 字段名。
            declared: Schema 声明的策略名（`mask` 的 `strategy` 入参；可为 None）。

        Returns:
            str | None: 生效策略名；未命中为 None。
        """
        rule = self._rules.get(field)
        if rule is not None:
            return rule.strategy
        if declared is not None:
            return declared
        if field in MASK_STRATEGIES:
            return field
        return None

    def _apply(self, strategy: str, text: str) -> str:
        """按策略名解析掩码串（自定义策略 → 内置策略 → 兜底全掩码）。

        Args:
            strategy: 策略名（字段注册 / Schema 声明；未知策略名兜底 `custom` 全掩码）。
            text: 待掩码文本（已 `str()`）。

        Returns:
            str: 掩码串。
        """
        custom = self._strategies.get(strategy)
        if custom is not None:
            return custom(text, self._mask_char)
        return apply_builtin_strategy(strategy, text, self._mask_char)
