"""值对象体系 · 选项链层：不可变选项契约（配置选项 → 不可变选项对象）。

**公共段**：`from_options(options)` 统一入口 + 取值助手（取键 / 默认 / 类型与范围校验 / 非法拒启
`PluginError`）在本层维护；子类只声明字段与「字段 ← 选项键」映射。

成员：`CaptchaImageOptions` / `CaptchaSliderOptions` / `CaptchaSmsOptions` / `MaskerOptions`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from bms_core.core.objects.roots import BaseValueObject

if TYPE_CHECKING:  # `core.concurrent` 经 `core.holder` 反向依赖本包，运行期导入会成环
    from bms_core.core.concurrent import ConcurrentStableDict

# 说明：`PluginError` 由 `core.exceptions` 定义，而本模块被 `core.exceptions.BizError` 反向依赖
# （`BizError` 挂 `BaseFrameworkObject`，09_05 批次 ②b）——顶层导入会形成 `core.exceptions ↔ core.objects`
# 循环导入，故在**使用处**延迟导入（行为不变，仅导入时机）。
__all__ = ["BaseOptionsContract"]


@dataclass(frozen=True)
class BaseOptionsContract(BaseValueObject, ABC):
    """不可变选项契约（值对象体系 · 选项链层）。

    公共段：`from_options` 为唯一受控构造入口（配置映射 → 不可变选项），取值助手把「取键 /
    缺省 / 类型与范围校验 / 非法拒启」收在本层；**子类不得绕过助手自行解析**（保证错误语义一致）。
    """

    @classmethod
    @abstractmethod
    def from_options(cls, options: ConcurrentStableDict[str, object] | None = None) -> Self:
        """从配置选项映射构造不可变选项对象（缺失取缺省，非法拒启）。

        Args:
            options: 配置选项映射（插入序；可为 None，视同空映射）。

        Returns:
            Self: 解析结果。

        Raises:
            PluginError: 选项类型非法 / 越界 / 形态不符。
        """

    @classmethod
    def _int_option(
        cls, options: ConcurrentStableDict[str, object], key: str, default: int, minimum: int, maximum: int
    ) -> int:
        """取整型选项并做范围校验（缺失取缺省，非法拒启）。

        Args:
            options: 选项映射。
            key: 选项键。
            default: 缺省值。
            minimum: 允许下限（含）。
            maximum: 允许上限（含）。

        Returns:
            int: 校验通过的整数选项。

        Raises:
            PluginError: 布尔 / 非数值 / 不可转换（`{类名} 选项非法`）或超出范围（`{类名} 选项越界`）。
        """
        from bms_core.core.exceptions import PluginError

        raw = options.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise PluginError(f"{cls.__name__} 选项非法：{key}={raw!r}（应为整数）")
        try:
            value = int(raw)
        except ValueError as exc:
            raise PluginError(f"{cls.__name__} 选项非法：{key}={raw!r}（应为整数）") from exc
        if not minimum <= value <= maximum:
            raise PluginError(f"{cls.__name__} 选项越界：{key}={value}（允许 {minimum} ~ {maximum}）")
        return value

    @classmethod
    def _str_option(cls, options: ConcurrentStableDict[str, object], key: str, default: str) -> str:
        """取非空字符串选项（缺失取缺省，非法拒启）。

        Args:
            options: 选项映射。
            key: 选项键。
            default: 缺省值。

        Returns:
            str: 非空字符串选项。

        Raises:
            PluginError: 非字符串或空字符串。
        """
        from bms_core.core.exceptions import PluginError

        raw = options.get(key, default)
        if not isinstance(raw, str) or not raw:
            raise PluginError(f"{cls.__name__} 选项非法：{key}={raw!r}（应为非空字符串）")
        return raw

    @classmethod
    def _single_char_option(cls, options: ConcurrentStableDict[str, object], key: str, default: str) -> str:
        """取单字符选项（缺失 / 空值取缺省，非法拒启）。

        Args:
            options: 选项映射。
            key: 选项键。
            default: 缺省值。

        Returns:
            str: 单字符选项。

        Raises:
            PluginError: 长度不为 1。
        """
        from bms_core.core.exceptions import PluginError

        raw = options.get(key) or default
        if not isinstance(raw, str) or len(raw) != 1:
            raise PluginError(f"{cls.__name__} 选项非法：{key}（须为单字符）")
        return raw

    @classmethod
    def _mapping_option(cls, options: ConcurrentStableDict[str, object], key: str) -> ConcurrentStableDict[str, str]:
        """取「非空字符串 → 非空字符串」映射选项（缺失取空映射，非法拒启）。

        Args:
            options: 选项映射（插入序）。
            key: 选项键。

        Returns:
            ConcurrentStableDict[str, str]: 校验通过的映射（键值均为非空字符串；插入序）。

        Raises:
            PluginError: 非映射，或键 / 值为非非空字符串。
        """
        from bms_core.core.concurrent import ConcurrentStableDict
        from bms_core.core.exceptions import PluginError

        raw: object = options.get(key)
        if raw is None:
            return ConcurrentStableDict()
        if not isinstance(raw, Mapping):
            raise PluginError(f"{cls.__name__} 选项非法：{key}（应为「键 → 值」映射）")
        parsed: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for name, value in cast("Mapping[object, object]", raw).items():
            if not isinstance(name, str) or not name:
                raise PluginError(f"{cls.__name__} 选项映射键非法（须为非空字符串）：{key}")
            if not isinstance(value, str) or not value:
                raise PluginError(f"{cls.__name__} 选项映射值非法（须为非空字符串）：{key}.{name}")
            parsed.set(name, value)
        return parsed
