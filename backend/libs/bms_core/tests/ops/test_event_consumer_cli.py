"""事件消费 CLI 用例：组清单诊断 / 未知服务退码 / 无声明时的安全返回。

不起 broker、不消费——只验「声明装载 + 校验 + 输出」这条链路，broker 交互由
`test_rocketmq_consumer` 的替身用例覆盖。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from ops.event_consumer import main

pytestmark = pytest.mark.kiwi_id(2370)


def test_groups_lists_declarations(capsys: pytest.CaptureFixture[str]) -> None:
    """`--groups` 打印服务声明与开关；平台服务当前未声明消费组（0 条）。"""
    code = main(ConcurrentStableList(["--service", "platform", "--groups"]))
    assert code == 0
    out = capsys.readouterr().out
    assert "服务 platform" in out
    assert "消费开关" in out


def test_unknown_service_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """未知服务包 → 退出码 2（不静默当作 0 条声明）。"""
    with pytest.raises(SystemExit) as excinfo:
        main(ConcurrentStableList(["--service", "no_such_service", "--groups"]))
    assert excinfo.value.code == 2
    assert "服务包不存在" in capsys.readouterr().err


def test_mode_is_mutually_exclusive() -> None:
    """必须且只能选一个动作（防误跑）。"""
    with pytest.raises(SystemExit):
        main(ConcurrentStableList(["--service", "platform"]))
