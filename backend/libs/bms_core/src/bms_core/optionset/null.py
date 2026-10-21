"""选项集能力域缺省实现（Null Object）：登记真实、解析空集、校验恒定通过。

- `register` 继承基座：登记与装载期冲突校验照常生效（占位期也能单测冲突规则）。
- `resolve` 恒定返回空选项集（`items` 空 / `name` 空 / `version=0`），不抛未命中错误。
- `validate` 恒定通过（空违规元组），不解析值域。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.optionset.base import (
    OPTION_SET_KEY_SEPARATOR,
    BaseOptionSet,
    BaseOptionSetRegistry,
    OptionItem,
    OptionSetInfo,
)

__all__ = [
    "NullOptionSetRegistry",
]


class NullOptionSetRegistry(BaseOptionSetRegistry, BaseNullObject):
    """占位注册表：登记真实（含冲突校验）、解析恒定空集、值域校验恒定通过。"""

    @classmethod
    def _provider_key(cls, provider: BaseOptionSet) -> str:
        """注册项键：选项集标识 `key`。

        Args:
            provider: 选项集提供者。

        Returns:
            str: 选项集标识。
        """
        return provider.key

    def resolve(self, option_set_key: str) -> OptionSetInfo:
        """恒定返回空选项集（占位不提供真实条目）。

        Args:
            option_set_key: 选项集标识（原样回填，供调用方对齐）。

        Returns:
            OptionSetInfo: 空选项集（`version=0` 表示未装载真实条目）。
        """
        namespace = option_set_key.split(OPTION_SET_KEY_SEPARATOR, 1)[0]
        return OptionSetInfo(
            option_set_key=option_set_key,
            items=ConcurrentStableFrozenList[OptionItem](),
            name="",
            namespace=namespace,
            version=0,
        )

    def validate(self, value: str, *, option_set_key: str) -> ConcurrentStableList[str]:
        """恒定通过（占位不校验值域）。

        Args:
            value: 选项值（占位忽略）。
            option_set_key: 选项集标识（占位忽略）。

        Returns:
            ConcurrentStableList[str]: 空违规元组。
        """
        del value, option_set_key
        return ConcurrentStableList(())
