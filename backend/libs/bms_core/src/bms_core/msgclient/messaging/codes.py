"""消息数据面码表（msg 03-6 详细设计 §7）：码 →（基座类别，本层动作）。

**为什么客户端必须自带码表**：数据面 JSON 错误体只有 `code` / `message` / `data`，`retryable` / `layer`
只存在于帧形态的错误帧头。客户端走 JSON，所以「这条能不能再发」必须自己判。

**与基座 `classify()` 的关系**：`category` 一列照抄 msg 服务端 `api/frame/responses.py::classify()` 的判定
（同一个码在服务端与客户端不能给出不同类别），`action` 一列是本层新增：它回答「这条消息该怎么再发」，
而 `category` 只回答「码本身是什么性质」。两处不同恰好说明为什么需要两维——见 `350022`：
类别是 `transient`（清理后可恢复），动作是 `fatal`（退避解决不了，必须有人去清盘）。
"""

from __future__ import annotations

from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.roots import BaseValueObject
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging.errors import ClientAction

__all__ = ["rule_for_consume", "rule_for_publish"]


@dataclass(frozen=True)
class _CodeRule(BaseValueObject):
    """单个码的处置规则（内部值对象；不对外暴露，避免调用方绕过错误对象自行判码）。

    Attributes:
        category: 基座错误类别。
        action: 本层动作。
        outcome_unknown: 结果是否未知（可能已写入）。
    """

    category: ErrorCategory
    action: ClientAction
    outcome_unknown: bool = False


_FATAL = _CodeRule(ErrorCategory.BUSINESS_REJECT, ClientAction.FATAL)
_PARAM = _CodeRule(ErrorCategory.PARAM_ERROR, ClientAction.FATAL)
_RETRY = _CodeRule(ErrorCategory.TRANSIENT, ClientAction.RETRY)
_REFRESH = _CodeRule(ErrorCategory.TRANSIENT, ClientAction.REFRESH)
_NEEDS_HUMAN = _CodeRule(ErrorCategory.TRANSIENT, ClientAction.FATAL)
_AMBIGUOUS = _CodeRule(ErrorCategory.TRANSIENT, ClientAction.FATAL, outcome_unknown=True)
_UNKNOWN_CODE = _CodeRule(ErrorCategory.SERVER_BUG, ClientAction.FATAL)
"""未登记码的兜底：宁可少重试也不放大故障（与服务端 `classify()` 的兜底同向）。"""

_PUBLISH_RULES = ConcurrentStableFrozenDict(
    {
        350001: _FATAL,  # 主题不存在 / 未启用
        350005: _RETRY,  # 生产限流（Retry-After 优先）
        350006: _PARAM,  # 载荷超 1 MiB（改参：拆分或引用对象存储）
        350010: _FATAL,  # 命名空间非法
        350011: _FATAL,  # 租户停用
        350012: _FATAL,  # 租户不存在
        350015: _RETRY,  # 延迟区已满（容量型，退避有意义）
        350020: _RETRY,  # 连接数超限
        350021: _RETRY,  # 单连接长驻流超限
        350022: _NEEDS_HUMAN,  # 存储水位：类别瞬时，但动作是人工（退避解决不了）
        350027: _FATAL,  # ACL 拒绝
        350028: _FATAL,  # 主题状态不接受该操作
        350032: _AMBIGUOUS,  # ISR 不足 / 提交超时：可能已落盘
        350033: _REFRESH,  # 非 leader / 过期任期 / 切换中 / 租约过期
        10001: _PARAM,  # 参数 / 载荷编码非法
        10006: _RETRY,  # 数据库繁忙
        10007: _RETRY,  # 依赖服务不可用
    }
)
"""生产端码表（详细设计 §7.1）。"""

_CONSUME_RULES = ConcurrentStableFrozenDict(
    {
        350001: _FATAL,
        350002: _FATAL,  # 位点非法（数据面不可回退，需管理员重置）
        350003: _FATAL,  # 消息不存在（位点已被保留期清理）
        350005: _RETRY,
        350007: _FATAL,  # 重投超限已进死信（调用方跳过该条）
        350009: _FATAL,  # 分区号非法
        350010: _FATAL,
        350011: _FATAL,
        350012: _FATAL,
        350013: _FATAL,  # 组不存在（未 join 或被回收）
        350014: _CodeRule(ErrorCategory.BUSINESS_REJECT, ClientAction.REFRESH),  # 成员失效 / 分区易主
        350026: _FATAL,  # 组数配额已满
        10006: _RETRY,
        10007: _RETRY,
    }
)
"""消费 / 成员端码表（详细设计 §7.2）。"""


def rule_for_publish(code: int) -> _CodeRule:
    """按生产端码表取规则（未登记码落兜底）。

    Args:
        code: 产品码 / 平台码。

    Returns:
        _CodeRule: 处置规则。
    """
    return _PUBLISH_RULES.get(code, _UNKNOWN_CODE)


def rule_for_consume(code: int) -> _CodeRule:
    """按消费 / 成员端码表取规则（未登记码落兜底）。

    Args:
        code: 产品码 / 平台码。

    Returns:
        _CodeRule: 处置规则。
    """
    return _CONSUME_RULES.get(code, _UNKNOWN_CODE)
