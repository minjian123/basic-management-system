"""归档库会话依赖：只读 / 写会话可从应用装配解析。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.db.session import get_archive_read_db, get_archive_write_db

pytestmark = pytest.mark.kiwi_id(2516)


def _request(app: FastAPI) -> Request:
    """构造绑定到应用实例的请求（仅供会话依赖取 `app.state`）。"""
    return Request({"type": "http", "app": app, "headers": []})


async def test_archive_session_dependencies(service_app: FastAPI) -> None:
    """只读 / 写归档库依赖都能产出可用会话。"""
    for dependency in (get_archive_read_db, get_archive_write_db):
        generator = dependency(_request(service_app))
        try:
            session = await anext(generator)
            assert session is not None
        finally:
            await generator.aclose()
