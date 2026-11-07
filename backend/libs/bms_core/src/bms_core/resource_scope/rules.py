"""作用域校验扩展点（07D `02_01`）：产品第四步规则的可注册端口与有序规则链。

**分工**：前三步（租户可用性 → `module_key` 登记态 → 资源类型注册与归属 → `resource_key` 越界）
由基座在 `SourceScopeResolver` 内固定执行，产品只在第四步追加语义；顺序不可调、不可跳。

口径：

- **只拿只读入参**：规则收到的是**已通过前四步**的 `ResolvedScope`（含 `tenant` / `key` /
  `resource_type` / `extensions`），拿不到租户源、注册表与 DB 会话——无法借此绕过前四步。
- **只执行已声明的规则**：启用清单来自产品 `extension_requirements()` 的 `scope_rule` 声明
  （按 `(order, 声明序)` 排序）；**注册了但未声明的规则不执行**，避免平台内置规则意外生效。
- **fail-closed**：规则抛 `BizError` 原样冒泡；抛其它异常一律包成 `InternalError`（10000）——
  规则自身写崩不得变成「放行」。
- **空链等价现状**：无声明即空链，`verify()` 不改变任何既有产品行为。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn, cast

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import BizError, ConfigError, InternalError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.extension.base import DEFAULT_EXTENSION_ORDER, SCOPE_RULE_KEY, ExtensionRequirement, requirements_by_key

if TYPE_CHECKING:
    from bms_core.resource_scope.resolver import ResolvedScope

__all__ = [
    "EMPTY_SCOPE_RULE_CHAIN",
    "BaseScopeRule",
    "NullScopeRule",
    "ScopeRuleChain",
    "build_scope_rule_chain",
]

_LOGGER = get_logger("bms.scope_rule")


class BaseScopeRule(BasePluggable, ABC):
    """作用域校验第四步规则契约（能力域 `scope_rule`）。

    产品实现本类并在 `configure_plugins()` 内登记，同时在 `extension_requirements()` 声明
    `ExtensionRequirement(SCOPE_RULE_KEY, "<实现名>")`——声明才启用。
    """

    key: str = SCOPE_RULE_KEY
    plugin_key: str = SCOPE_RULE_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION
    order: int = DEFAULT_EXTENSION_ORDER
    """执行序（小者先；同序按声明序）。实现可覆写。"""

    def applies_to(self, scope: ResolvedScope) -> bool:
        """规则是否适用于该作用域（缺省适用）。

        Args:
            scope: 已通过前四步的作用域。

        Returns:
            bool: 适用为 True；为假时该规则本次零调用。
        """
        del scope
        return True

    @abstractmethod
    def verify(self, scope: ResolvedScope) -> None:
        """判定（不通过即抛）。

        Args:
            scope: 已通过前四步的作用域。

        Raises:
            BizError: 产品自定义拒绝（码由产品声明，渲染由统一单点）。
        """
        ...


class NullScopeRule(BaseScopeRule, BaseNullObject):
    """占位规则：不做任何判定（仅开发期显式占位；生产声明它等于「显式不做第四步校验」）。"""

    plugin_name: str = NULL_PLUGIN_NAME

    def verify(self, scope: ResolvedScope) -> None:
        """空判定。

        Args:
            scope: 已通过前四步的作用域（忽略）。
        """
        del scope


@dataclass(frozen=True)
class ScopeRuleChain(BaseValueObject):
    """有序规则链（不可变）：逐条执行，首个不通过即中断。"""

    rules: ConcurrentStableFrozenList[BaseScopeRule]
    """已按 `(order, 声明序)` 排序的规则（空链表示不做第四步校验）。"""

    def verify(self, scope: ResolvedScope) -> None:
        """依次执行适用规则。

        Args:
            scope: 已通过前四步的作用域。

        Raises:
            BizError: 规则拒绝（原样冒泡）。
            InternalError: 规则抛非 `BizError`（fail-closed，内部日志带规则名）。
        """
        for rule in self.rules:
            name = f"{rule.plugin_key}:{rule.plugin_name}"
            try:
                applies = rule.applies_to(scope)
            except BizError:
                raise
            except Exception as exc:  # 规则实现缺陷不得变成放行（fail-closed）
                _raise_rule_failure(name, scope, exc)
            if not applies:
                continue
            try:
                rule.verify(scope)
            except BizError:
                raise
            except Exception as exc:  # 同上
                _raise_rule_failure(name, scope, exc)

    def __bool__(self) -> bool:
        """是否含规则（空链为假）。

        Returns:
            bool: 有规则为 True。
        """
        return bool(self.rules)


def _raise_rule_failure(name: str, scope: ResolvedScope, exc: Exception) -> NoReturn:
    """把规则内非业务异常转成 `InternalError`（并记录定位信息）。

    Args:
        name: 规则标识（`plugin_key:plugin_name`）。
        scope: 当前作用域（取模块键 / 资源键定位）。
        exc: 规则抛出的原始异常。

    Raises:
        InternalError: 恒定（fail-closed）。
    """
    _LOGGER.error(
        "scope_rule_failed",
        rule=name,
        module_key=scope.module_key,
        resource_key=scope.resource_key,
        error=type(exc).__name__,
        detail=repr(exc),
    )
    raise InternalError(f"作用域校验规则执行失败：{name}") from exc


EMPTY_SCOPE_RULE_CHAIN = ScopeRuleChain(rules=ConcurrentStableFrozenList[BaseScopeRule]())
"""空链（未声明任何规则时的缺省值）。"""


def build_scope_rule_chain(requirements: Iterable[ExtensionRequirement]) -> ScopeRuleChain:
    """按声明构造规则链（注册表须已冻结）。

    Args:
        requirements: 生效的扩展点声明（`verify_extension_requirements()` 返回值）。

    Returns:
        ScopeRuleChain: 有序链；无声明即空链。

    Raises:
        ConfigError: 声明了但解析失败（装配期本应已由必需项核对拦住，运行期不静默跳过）。
    """
    ordered = requirements_by_key(requirements, SCOPE_RULE_KEY)
    if not ordered:
        return EMPTY_SCOPE_RULE_CHAIN
    collected: ConcurrentStableList[BaseScopeRule] = ConcurrentStableList()
    for requirement in ordered:
        try:
            rule = cast(
                "BaseScopeRule",
                resolve_plugin(
                    SCOPE_RULE_KEY,
                    requirement.plugin_name,
                    expected_version=BaseScopeRule.contract_version,
                ),
            )
        except Exception as exc:
            raise ConfigError(f"作用域校验规则解析失败：{requirement.label}（{type(exc).__name__}）") from exc
        collected.add(rule)
    return ScopeRuleChain(rules=ConcurrentStableFrozenList[BaseScopeRule](collected))
