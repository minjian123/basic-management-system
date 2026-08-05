"""单元测试：统一异常与错误码结构。"""

from __future__ import annotations

from app.core.errors import (
    CODE_INTERNAL_ERROR,
    CODE_OK,
    CODE_TENANT_INVALID,
    CODE_VALIDATION_ERROR,
    BizError,
    error_body,
)


def test_error_body_structure() -> None:
    """统一错误响应体结构 {code, message, data}。"""
    body = error_body(10001, "参数校验失败", {"errors": []})
    assert set(body) == {"code", "message", "data"}
    assert body["code"] == 10001


def test_biz_error_fields() -> None:
    """BizError 携带错误码、消息与 HTTP 状态码。"""
    exc = BizError(CODE_TENANT_INVALID, "非法租户标识", status_code=400)
    assert exc.code == CODE_TENANT_INVALID
    assert exc.status_code == 400
    assert "非法租户" in exc.message


def test_error_code_segments() -> None:
    """错误码段位约定：0 成功、1xxxx 通用、8xxxx 租户。"""
    assert CODE_OK == 0
    assert 10000 <= CODE_VALIDATION_ERROR < 20000
    assert 10000 <= CODE_INTERNAL_ERROR < 20000
    assert 80000 <= CODE_TENANT_INVALID < 90000
