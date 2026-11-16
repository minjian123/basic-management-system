"""03-6 用例：数据面码表（Kiwi 2510）。

覆盖要点：生产与消费两张码表的「已知 / 未登记」两条路径；两处两维不一致要固定下来——
`350022`（类别瞬时、动作人工）与 `350032`（类别瞬时、标结果未知、动作不重试）。
"""

from __future__ import annotations

import pytest

from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging import ClientAction, rule_for_consume, rule_for_publish

pytestmark = pytest.mark.kiwi_id(2510)


def test_publish_rules_cover_retry_refresh_and_ambiguity() -> None:
    """生产端码表：限流可重试、写错 leader 改投、提交超时结果未知、盘满要人工。"""
    assert rule_for_publish(350005).action is ClientAction.RETRY
    assert rule_for_publish(350033).action is ClientAction.REFRESH
    assert rule_for_publish(350033).category is ErrorCategory.TRANSIENT
    assert rule_for_publish(350032).outcome_unknown is True
    assert rule_for_publish(350032).action is ClientAction.FATAL
    assert rule_for_publish(350022).category is ErrorCategory.TRANSIENT
    assert rule_for_publish(350022).action is ClientAction.FATAL
    assert rule_for_publish(350006).category is ErrorCategory.PARAM_ERROR


def test_publish_rules_fall_back_to_server_bug() -> None:
    """未登记码：兜底为「服务端异常 + 不重试」，宁可少重试也不放大故障。"""
    rule = rule_for_publish(399999)
    assert rule.category is ErrorCategory.SERVER_BUG
    assert rule.action is ClientAction.FATAL


def test_consume_rules_cover_member_and_retry() -> None:
    """消费端码表：成员失效是「重新加入」、限流是重试、位点非法要人工。"""
    assert rule_for_consume(350014).action is ClientAction.REFRESH
    assert rule_for_consume(350005).action is ClientAction.RETRY
    assert rule_for_consume(350002).action is ClientAction.FATAL
    assert rule_for_consume(350007).action is ClientAction.FATAL


def test_consume_rules_fall_back_to_server_bug() -> None:
    """消费端未登记码同样兜底为服务端异常。"""
    assert rule_for_consume(399999).category is ErrorCategory.SERVER_BUG
