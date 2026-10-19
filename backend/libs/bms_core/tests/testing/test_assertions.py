"""测试公共基座：错误断言三形态（Kiwi 2317）。"""

from typing import Any

import pytest

from bms_core.testing import assert_error, assert_no_error


class _FakeError(Exception):
    """带业务码 / 状态码的异常替身。"""

    code = 30010
    status_code = 403
    message = "职责互斥"


class _FakeResponse:
    """HTTP 响应替身（只实现 `status_code` 与 `json`）。"""

    def __init__(self, status_code: int, payload: Any) -> None:
        """保存状态码与响应体。

        Args:
            status_code: HTTP 状态码。
            payload: 响应体。
        """
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        """返回响应体。

        Returns:
            Any: 响应体。
        """
        return self._payload


@pytest.mark.kiwi_id(2317)
def test_assert_error_accepts_exception() -> None:
    """异常形态：按 `code` / `status_code` / `message` 断言。"""
    assert_error(_FakeError(), code=30010, status=403, message="职责")


@pytest.mark.kiwi_id(2317)
def test_assert_error_accepts_response() -> None:
    """响应形态：状态码取 `status_code`、业务码取 JSON。"""
    response = _FakeResponse(403, {"code": 30010, "message": "职责互斥"})

    assert_error(response, code=30010, status=403)


@pytest.mark.kiwi_id(2317)
def test_assert_error_accepts_mapping() -> None:
    """字典形态：`status` / `status_code` 均可作为状态码。"""
    assert_error({"code": 10001, "status": 400}, code=10001, status=400)
    assert_error({"code": "10001", "status_code": "400"}, code=10001, status=400)


@pytest.mark.kiwi_id(2317)
def test_assert_error_reports_all_mismatches() -> None:
    """不匹配：一次性列出 code / status / message 三类偏差。"""
    with pytest.raises(AssertionError) as exc:
        assert_error(_FakeError(), code=1, status=500, message="不存在")

    text = str(exc.value)
    assert "code 期望 1" in text
    assert "status 期望 500" in text
    assert "message 期望包含" in text


@pytest.mark.kiwi_id(2317)
def test_assert_error_rejects_unknown_target() -> None:
    """无法识别的 target：抛 TypeError（防误用）。"""
    with pytest.raises(TypeError):
        assert_error(object())


@pytest.mark.kiwi_id(2317)
def test_assert_no_error() -> None:
    """成功断言：2xx 且业务码 0 / 缺失通过；错误响应与错误码失败。"""
    assert_no_error(_FakeResponse(200, {"code": 0}))
    assert_no_error(_FakeResponse(200, {}))

    with pytest.raises(AssertionError):
        assert_no_error(_FakeResponse(500, {"code": 0}))
    with pytest.raises(AssertionError):
        assert_no_error({"code": 30010})


@pytest.mark.kiwi_id(2317)
def test_assert_error_edge_shapes() -> None:
    """边界：`bool` 不作数字；响应体非字典时只断言状态码。"""
    assert_error({"code": True, "status": 400}, status=400)
    assert_error(_FakeResponse(500, ["oops"]), status=500)
