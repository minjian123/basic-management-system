"""选项集清单记录与运行时适配：TOML 声明（装载注册）→ `BaseOptionSet` 提供者。

口径（需求 09-4 / 任务 09-03-1）：
- 静态值域由 `deploy/registry/<仓>.toml` 的 `[[option_sets]]` 声明，装载时注册；
- 运行期只读、不落库；加值只改配置；
- `contract_name` / `extensible` 供契约导出派生 `x-extensible-enum`。
"""

from dataclasses import dataclass, field

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.optionset.base import BaseOptionSet, OptionItem

__all__ = [
    "ManifestOptionSet",
    "OptionSetRecord",
]


@dataclass(frozen=True)
class OptionSetRecord(BaseValueObject):
    """清单中的一条选项集声明。

    Attributes:
        option_set_key: 选项集标识（点分小写，如 `bms.tenant.status`）。
        name: 名称。
        contract_name: 对应公开契约组件名（可空）。
        extensible: 是否允许跨版本增加条目（契约输出 `x-extensible-enum`）。
        items: 条目清单（声明顺序）。
    """

    option_set_key: str
    name: str
    contract_name: str | None = None
    extensible: bool = False
    items: ConcurrentStableFrozenList[OptionItem] = field(
        default_factory=lambda: ConcurrentStableFrozenList[OptionItem]()
    )


class ManifestOptionSet(BaseOptionSet):
    """由清单声明构造的选项集提供者（运行期只读）。"""

    def __init__(self, record: OptionSetRecord) -> None:
        """初始化。

        Args:
            record: 清单声明。
        """
        self._record = record
        self.contract_name = record.contract_name
        self.extensible = record.extensible

    @property
    def key(self) -> str:
        """选项集标识。

        Returns:
            str: 标识。
        """
        return self._record.option_set_key

    @property
    def name(self) -> str:
        """名称。

        Returns:
            str: 名称。
        """
        return self._record.name

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 描述。
        """
        return f"选项集 {self._record.option_set_key}（清单声明）"

    def items(self) -> ConcurrentStableList[OptionItem]:
        """条目清单（声明顺序）。

        Returns:
            ConcurrentStableList[OptionItem]: 条目。
        """
        return ConcurrentStableList(self._record.items)

    def get(self, value: str) -> OptionItem | None:
        """按值取条目。

        Args:
            value: 选项值。

        Returns:
            OptionItem | None: 命中项；未命中为 None。
        """
        for item in self._record.items:
            if item.value == value:
                return item
        return None

    def validate_value(self, value: str) -> ConcurrentStableList[str]:
        """判定值是否在值域内。

        Args:
            value: 选项值。

        Returns:
            ConcurrentStableList[str]: 违规原因；空表示通过。
        """
        if self.get(value) is None:
            return ConcurrentStableList([f"取值不在选项集 {self.key} 内：{value!r}"])
        return ConcurrentStableList()
