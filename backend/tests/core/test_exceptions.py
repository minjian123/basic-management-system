"""异常体系与统一响应模型测试（Kiwi 20）。"""

import pytest

from app.core.exceptions import (
    AuthError,
    BizError,
    ConcurrentConflictError,
    ConflictError,
    InternalError,
    NotFoundError,
    ParamError,
    PermissionError,
)
from app.schemas.common import ApiResponse


@pytest.mark.kiwi_id(20)
def test_biz_error_attributes() -> None:
    """BizError 携带错误码 / 消息 / HTTP 状态 / 数据。"""
    error = BizError(12345, "boom", http_status=418, data={"k": 1})
    assert (error.code, error.message, error.http_status, error.data) == (12345, "boom", 418, {"k": 1})
    assert str(error) == "boom"
    assert BizError(12345).message is None


@pytest.mark.kiwi_id(20)
def test_subclass_codes_and_status() -> None:
    """子类错误码与 HTTP 状态正确，且均继承 BizError。"""
    cases = {
        InternalError: (10000, 500),
        ParamError: (10001, 200),
        NotFoundError: (10002, 404),
        ConflictError: (10003, 200),
        ConcurrentConflictError: (10004, 409),
        AuthError: (20001, 401),
        PermissionError: (30001, 403),
    }
    for cls, (code, status) in cases.items():
        instance = cls()
        assert (instance.code, instance.http_status) == (code, status)
        assert issubclass(cls, BizError)


@pytest.mark.kiwi_id(20)
def test_api_response_ok() -> None:
    """ApiResponse 默认结构与 ok() 助手。"""
    assert ApiResponse().model_dump() == {"code": 0, "message": "ok", "data": None}
    resp = ApiResponse.ok({"a": 1})
    assert (resp.code, resp.message, resp.data) == (0, "ok", {"a": 1})
    assert ApiResponse.ok().data is None
