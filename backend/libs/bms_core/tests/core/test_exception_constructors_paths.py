"""低频异常构造路径补齐用例（`bms_core/core/exceptions.py`）。"""

from __future__ import annotations

from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import (
    ClientConflictError,
    LocalLoginGuardError,
    MenuFieldPermissionMismatchError,
    MenuLinkBrokenError,
    MenuPlatformReadonlyError,
    OidcInvalidScopeError,
    RoleSeparationConflictError,
)


def test_rare_exception_constructors_carry_codes_and_status() -> None:
    """低频异常构造子：按登记错误码与 HTTP 状态构造。"""
    assert LocalLoginGuardError("x").http_status == 429
    assert RoleSeparationConflictError("x").http_status == 403
    assert MenuLinkBrokenError("x").code == ErrorCode.MENU_LINK_BROKEN
    assert MenuPlatformReadonlyError("x").http_status == 403
    assert MenuFieldPermissionMismatchError("x").code == ErrorCode.MENU_FIELD_PERMISSION_MISMATCH
    assert OidcInvalidScopeError("x").http_status == 400
    assert ClientConflictError("x").http_status == 409
