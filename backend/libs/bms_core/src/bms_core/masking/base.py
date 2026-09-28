"""数据脱敏能力域：字段掩码基座契约（真实规则见 `masking/default.py`）。

- `BaseMasker`：能力域中间层契约（`key = "masking"`）——字段注册（`register`）+ 自定义策略注册
  （`register_strategy`）+ 掩码（`mask`）+ 明文还原（`reveal`）；「持 `data:plain` 权限方可看明文」
  由基座内 `check_plain()` **单点判定**（权限检查器构造注入），调用方不传权限参数。
- `get_masker`：依赖注入提供者——取应用级掩码器并把掩码器写入 `current_masker` 上下文变量
  （请求结束复位），供 `BaseSchema` 序列化期取用；公共依赖经 `app/api/deps.py` 统一导出。
"""

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.context import reset_current_masker, set_current_masker
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.permission.base import BasePermissionChecker

MASK_STRATEGIES: tuple[str, ...] = ("phone", "id_card", "email", "bank_card", "name", "address", "custom")
"""候选掩码策略（内置策略规格见 `masking/default.py` 的 `BUILTIN_MASK_SPECS`；`custom` 恒居末位）。"""

PLAIN_PERMISSION = "data:plain"
"""明文查看权限码（持码方可看明文，见《架构设计 · 性能与安全》「数据安全」节）。"""

STRATEGY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""自定义掩码策略名格式（小写字母开头，仅小写字母 / 数字 / 下划线）。"""

MaskStrategy = Callable[[str, str], str]
"""自定义掩码策略：`(字段值, 掩码字符) -> 掩码串`。"""


@dataclass(frozen=True)
class MaskRule(BaseObject):
    """字段掩码登记项：字段名 + 掩码策略。"""

    field: str
    strategy: str = "custom"


class BaseMasker(BasePluggable, ABC):
    """数据脱敏契约：字段注册 + 掩码 / 明文还原。"""

    key: str = "masking"
    plugin_key: str = "masking"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, checker: BasePermissionChecker) -> None:
        """初始化脱敏基座。

        Args:
            checker: 权限检查器（判定 `data:plain`；随 RBAC 阶段替换实现）。
        """
        super().__init__()
        self._checker = checker
        self._rules: dict[str, MaskRule] = {}
        self._strategies: dict[str, MaskStrategy] = {}

    def register(self, field: str, strategy: str = "custom") -> MaskRule:
        """登记敏感字段（同字段重复注册以最后一次为准）。

        Args:
            field: 字段名。
            strategy: 掩码策略（占位期仅登记，取值不校验）。

        Returns:
            MaskRule: 登记项。
        """
        rule = MaskRule(field=field, strategy=strategy)
        self._rules[field] = rule
        return rule

    @property
    def masked_fields(self) -> frozenset[str]:
        """已登记字段集合（供序列化层与测试核对）。

        Returns:
            frozenset[str]: 字段名集合。
        """
        return frozenset(self._rules)

    def rules(self) -> tuple[MaskRule, ...]:
        """登记项快照（按字段名排序，输出稳定）。

        Returns:
            tuple[MaskRule, ...]: 登记项元组。
        """
        return tuple(self._rules[field] for field in sorted(self._rules))

    def register_strategy(self, name: str, strategy: MaskStrategy) -> None:
        """登记自定义掩码策略（同名自定义策略重复注册以最后一次为准）。

        自定义策略优先级高于同名内置策略（内置策略名不可占用）；未注册策略名 / 未命中自定义
        策略的字段在实现侧按全掩码兜底，**不抛错**（序列化期抛错会中断响应）。

        Args:
            name: 策略名（不得与内置 `MASK_STRATEGIES` 同名，且须符合
                `^[a-z][a-z0-9_]*$`）。
            strategy: 掩码函数（`(字段值, 掩码字符) -> 掩码串`）。

        Raises:
            PluginError: 名称与内置策略同名或格式非法（40002，装配期 fail-fast）。
        """
        if name in MASK_STRATEGIES:
            raise PluginError(f"自定义掩码策略名与内置策略同名：{name}")
        if not STRATEGY_NAME_PATTERN.match(name):
            raise PluginError(f"自定义掩码策略名格式非法（须为小写字母开头的 snake_case）：{name}")
        self._strategies[name] = strategy

    def strategies(self) -> tuple[str, ...]:
        """自定义策略名快照（按名称排序，输出稳定）。

        Returns:
            tuple[str, ...]: 已登记自定义策略名元组。
        """
        return tuple(sorted(self._strategies))

    def check_plain(self) -> bool:
        """当前请求是否持 `data:plain`（明文查看）权限。

        Returns:
            bool: 持有为 True。
        """
        return self._checker.check(PLAIN_PERMISSION)

    @abstractmethod
    def mask(self, field: str, value: object) -> object:
        """掩码字段值。

        Args:
            field: 字段名（未登记字段原样返回）。
            value: 原始值。

        Returns:
            object: 持 `data:plain` 时为明文，否则为掩码值。
        """

    @abstractmethod
    def reveal(self, field: str, value: object) -> object:
        """还原字段明文（加密字段解密）。

        Args:
            field: 字段名（未登记字段原样返回）。
            value: 存储值（密文或掩码值）。

        Returns:
            object: 持 `data:plain` 时为明文，否则为掩码值。
        """


async def get_masker(request: Request) -> AsyncIterator[BaseMasker]:
    """取应用级掩码器并注入请求上下文（依赖注入提供者）。

    请求期把掩码器写入 `current_masker` 上下文变量（`BaseSchema` 序列化期取用），
    请求结束复位；上下文变量请求级隔离，可并发。

    必须为**异步**生成器依赖：同步依赖由 FastAPI 放入线程池执行，`set` 与 `reset`
    不在同一 Context（会抛 `Token was created in a different Context`），上下文变量也传不到接口内。

    Args:
        request: 请求对象。

    Yields:
        BaseMasker: 应用装配的掩码器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    masker = cast(
        "BaseMasker",
        resolve_plugin(
            "masking",
            settings.masking.provider,
            expected_version=BaseMasker.contract_version,
        ),
    )
    token = set_current_masker(masker)
    try:
        yield masker
    finally:
        reset_current_masker(token)
