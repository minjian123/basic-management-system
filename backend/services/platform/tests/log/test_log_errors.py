"""审计日志错误码护栏（06_01）：码位与 HTTP 状态稳定。"""

import pytest

from bms_core.core.error_codes import ERROR_CODE_HTTP_STATUS, ErrorCode
from bms_core.core.exceptions import (
    LoginLogNotFoundError,
    LogTimeRangeExceededError,
    OperationLogNotFoundError,
)
from bms_platform.domains.log.schema import month_shift, parse_month, shard_table_name

pytestmark = pytest.mark.kiwi_id(2407)


def test_error_codes_and_http_status() -> None:
    """90201 / 90203 / 90301：码位、HTTP 状态与登记映射一致。"""
    operation = OperationLogNotFoundError()
    assert (operation.code, operation.http_status) == (90201, 404)
    assert ERROR_CODE_HTTP_STATUS[ErrorCode.OPERATION_LOG_NOT_FOUND] == 404

    time_range = LogTimeRangeExceededError()
    assert (time_range.code, time_range.http_status) == (90203, 400)
    assert ERROR_CODE_HTTP_STATUS[ErrorCode.LOG_TIME_RANGE_EXCEEDED] == 400

    login = LoginLogNotFoundError()
    assert (login.code, login.http_status) == (90301, 404)
    assert ERROR_CODE_HTTP_STATUS[ErrorCode.LOGIN_LOG_NOT_FOUND] == 404


def test_month_helpers_reject_invalid_values() -> None:
    """月份键：形态 / 越界即拒；加减跨年正确；分片名带月份后缀。"""
    with pytest.raises(ValueError):
        parse_month("20261")
    with pytest.raises(ValueError):
        parse_month("202613")
    assert parse_month("202611") == (2026, 11)
    assert month_shift("202612", 1) == "202701"
    assert month_shift("202601", -1) == "202512"
    assert shard_table_name("operation", "202611") == "sys_operation_log_202611"
