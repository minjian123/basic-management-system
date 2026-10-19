"""测试公共基座：模板方法钩子与方法别名（Kiwi 2317）。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import BaseTestCase


class _Recorder(BaseTestCase):
    """记录钩子调用顺序的基类替身。"""

    def __init__(self) -> None:
        """初始化调用记录。"""
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    def prepare(self) -> None:
        """记录前置。"""
        self.calls.add("prepare")

    def assert_invariants(self) -> None:
        """记录不变量断言。"""
        self.calls.add("assert_invariants")

    def cleanup(self) -> None:
        """记录清理。"""
        self.calls.add("cleanup")


class _ProjectBase(_Recorder):
    """模拟「某测试类扩展了新方法」。"""

    def seed(self) -> None:
        """扩展方法（应可被同类测试继承）。"""
        self.calls.add("seed")


class _Concrete(_ProjectBase):
    """模拟继承扩展基类的具体测试类。"""


@pytest.mark.kiwi_id(2317)
def test_hooks_run_in_order() -> None:
    """钩子顺序：prepare → （用例体）→ assert_invariants → cleanup。"""
    case = _Recorder()

    case.setup_method()
    case.teardown_method()

    assert list(case.calls) == ["prepare", "assert_invariants", "cleanup"]


@pytest.mark.kiwi_id(2317)
def test_teardown_still_cleans_when_invariant_fails() -> None:
    """不变量失败：cleanup 仍执行（`finally` 语义）。"""

    class _Broken(_Recorder):
        def assert_invariants(self) -> None:
            self.calls.add("assert_invariants")
            raise AssertionError("不变量失败")

    case = _Broken()
    case.setup_method()
    with pytest.raises(AssertionError):
        case.teardown_method()
    assert list(case.calls) == ["prepare", "assert_invariants", "cleanup"]


@pytest.mark.kiwi_id(2317)
def test_derived_base_is_inheritable() -> None:
    """继承扩展：具体测试类可使用上层扩展的方法（无限层派生）。"""
    case = _Concrete()

    case.seed()

    assert list(case.calls) == ["seed"]


@pytest.mark.kiwi_id(2317)
def test_method_aliases_delegate_to_helpers() -> None:
    """方法别名：断言 / 输出别名与 helper 同源（失败信息一致）。"""
    case = _Recorder()

    case.assert_error({"code": 30010, "status": 403}, code=30010, status=403)
    with pytest.raises(AssertionError):
        case.assert_error({"code": 1}, code=2)


@pytest.mark.kiwi_id(2317)
def test_all_aliases_delegate(capsys: pytest.CaptureFixture[str]) -> None:
    """方法别名全覆盖：日志 / 输出 / CLI 均委托 helper。"""
    case = _Recorder()

    print('{"event": "alias.event", "level": "info"}')
    assert case.log_events(capsys)

    print('{"event": "alias.event", "level": "info"}')
    case.assert_logged(capsys, event="alias.event")

    print("alias-out")
    assert "alias-out" in case.stdout_text(capsys)

    print("alias-out-2")
    case.assert_output(capsys, contains="alias-out-2")

    result = case.run_cli("-c", "print(1)")
    assert result.exit_code == 0
