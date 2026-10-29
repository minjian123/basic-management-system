"""refresh cookie 策略用例（`HttpSessionCookiePolicy`）：清理口径与端点函数逐条等价。"""

from __future__ import annotations

from fastapi import Response

from bms_identity.domains.auth.schemas.auth import (
    REFRESH_COOKIE_LEGACY_PATHS,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
)
from bms_identity.domains.auth.services.cookie_policy import HttpSessionCookiePolicy, delete_refresh_cookie


def test_cookie_policy_clear_refresh_matches_endpoint() -> None:
    """清理：策略实现与端点函数下发同一组删除 cookie（新路径 + 历史路径逐个删）。"""
    direct = Response()
    delete_refresh_cookie(direct)
    via_policy = Response()
    HttpSessionCookiePolicy().clear_refresh(via_policy)

    expected = [header.lower() for header in direct.headers.getlist("set-cookie")]
    actual = [header.lower() for header in via_policy.headers.getlist("set-cookie")]
    assert actual == expected
    paths = (REFRESH_COOKIE_PATH, *REFRESH_COOKIE_LEGACY_PATHS)
    assert len(actual) == len(paths)
    for index, path in enumerate(paths):
        assert REFRESH_COOKIE_NAME.lower() in actual[index]
        assert f"path={path}".lower() in actual[index]
