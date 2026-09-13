"""异常体系与统一响应模型测试（Kiwi 20）。"""

import pytest

from app.core.base import BaseObject
from app.core.error_codes import ErrorCode, ErrorSegment
from app.core.exceptions import (
    AuthError,
    BizError,
    ConcurrentConflictError,
    ConflictError,
    GeneralError,
    InternalError,
    NotFoundError,
    ParamError,
    PermissionError,
    UserOrgError,
)
from app.schemas.common import ApiResponse


@pytest.mark.kiwi_id(20)
def test_biz_error_attributes_and_base_object() -> None:
    """BizError 携带错误码 / 消息 / HTTP 状态 / 数据，且纳入 L0 继承体系。"""
    error = BizError(12345, "boom", http_status=418, data={"k": 1})
    assert (error.code, error.message, error.http_status, error.data) == (12345, "boom", 418, {"k": 1})
    assert str(error) == "boom"
    assert str(BizError(12345)) == "error.12345"
    assert isinstance(error, BaseObject) and isinstance(error, Exception)
    assert error.to_dict() == {"code": 12345, "message": "boom", "http_status": 418, "data": {"k": 1}}


@pytest.mark.kiwi_id(20)
def test_subclass_codes_and_status() -> None:
    """子类错误码（引用 ErrorCode）与 HTTP 状态正确，且均继承 BizError。"""
    cases = {
        InternalError: (ErrorCode.INTERNAL, 500),
        ParamError: (ErrorCode.PARAM, 200),
        NotFoundError: (ErrorCode.NOT_FOUND, 404),
        ConflictError: (ErrorCode.CONFLICT, 200),
        ConcurrentConflictError: (ErrorCode.CONCURRENT_CONFLICT, 409),
        AuthError: (ErrorCode.AUTH, 401),
        PermissionError: (ErrorCode.PERMISSION, 403),
    }
    for cls, (code, status) in cases.items():
        instance = cls()
        assert (instance.code, instance.http_status) == (int(code), status)
        assert issubclass(cls, BizError)


@pytest.mark.kiwi_id(20)
def test_segment_base_classes() -> None:
    """按段位分基：通用段子类继承 GeneralError；权限不足继承 UserOrgError。"""
    for cls in (InternalError, ParamError, NotFoundError, ConflictError, ConcurrentConflictError):
        assert issubclass(cls, GeneralError)
    assert issubclass(GeneralError, BizError)
    assert issubclass(UserOrgError, BizError)
    assert issubclass(PermissionError, UserOrgError)
    assert issubclass(AuthError, BizError)


@pytest.mark.kiwi_id(20)
def test_error_segments() -> None:
    """错误码段位常量与平台码位一致。"""
    assert ErrorSegment.GENERAL == 1
    assert ErrorCode.NOT_FOUND // 10000 == ErrorSegment.GENERAL
    assert ErrorCode.AUTH // 10000 == ErrorSegment.AUTH
    assert ErrorCode.PERMISSION // 10000 == ErrorSegment.USER_ORG


@pytest.mark.kiwi_id(20)
def test_api_response_ok() -> None:
    """ApiResponse 默认结构与 ok() 助手。"""
    assert ApiResponse().model_dump() == {"code": 0, "message": "ok", "data": None}
    resp = ApiResponse.ok({"a": 1})
    assert (resp.code, resp.message, resp.data) == (0, "ok", {"a": 1})
    assert ApiResponse.ok().data is None
