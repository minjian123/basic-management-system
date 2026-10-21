"""选项集注册表真实实现（插件名 `local`）：内建平台选项集 + 各产品装载注入。

- `PLATFORM_OPTION_SETS`：内建平台选项集清单（**本期为空**；真实平台状态类选项集随表单定制阶段按
  平台字段回补，避免在占位期臆造 value / label）。
- `LocalOptionSetRegistry`：先以 `origin=platform` 登记内建清单，再以 `origin=product` 登记注入项；
  登记即校验（同 value 合并 / 同值异义 / 同 label 异值 / 同标识异义 / 产品覆盖基座一律 40002）。
- 解析与校验继承基座：`resolve` 未命中抛 `NotFoundError`（10002）；`validate` 委托提供者 `validate_value`。
"""

from collections.abc import Iterable

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.optionset.base import (
    OPTION_SET_ORIGIN_PLATFORM,
    OPTION_SET_ORIGIN_PRODUCT,
    BaseOptionSet,
    BaseOptionSetRegistry,
)

__all__ = [
    "PLATFORM_OPTION_SETS",
    "LocalOptionSetRegistry",
]

PLATFORM_OPTION_SETS: ConcurrentStableList[BaseOptionSet] = ConcurrentStableList(())
"""内建平台选项集清单（本期为空；随表单定制阶段按平台字段回补）。"""


class LocalOptionSetRegistry(BaseOptionSetRegistry):
    """真实注册表：装载期登记内建平台选项集与各产品注入项，运行期只读。"""

    @classmethod
    def _provider_key(cls, provider: BaseOptionSet) -> str:
        """注册项键：选项集标识 `key`。

        Args:
            provider: 选项集提供者。

        Returns:
            str: 选项集标识。
        """
        return provider.key

    def __init__(
        self,
        *,
        builtin: Iterable[BaseOptionSet] | None = None,
        injected: Iterable[BaseOptionSet] = (),
    ) -> None:
        """初始化并登记内建清单与注入项。

        Args:
            builtin: 基座内建清单（缺省 `PLATFORM_OPTION_SETS`；以 `origin=platform` 登记）。
            injected: 各产品装载注入项（以 `origin=product` 登记）。

        Raises:
            PluginError: 标识非法、条目冲突、产品占用基座命名空间或改写基座项（40002）。
        """
        super().__init__()
        for provider in PLATFORM_OPTION_SETS if builtin is None else builtin:
            self.register(provider, origin=OPTION_SET_ORIGIN_PLATFORM)
        for provider in injected:
            self.register(provider, origin=OPTION_SET_ORIGIN_PRODUCT)
