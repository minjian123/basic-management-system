"""收件人解析：平台用户只读出口的地址 / locale / 空用户 / 非法响应。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

import json

import pytest

from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.servicecall.base import ServiceResponse
from bms_notification.domains.notification.services.recipient import RecipientInfo, RecipientResolver

pytestmark = pytest.mark.kiwi_id(2519)


class _Client:
    def __init__(self, *, status: int = 200, body: object | None = None) -> None:
        self.status = status
        self.body = body

    async def call(self, request: object) -> ServiceResponse:
        del request
        return ServiceResponse(status_code=self.status, content=json.dumps(self.body or {}).encode())


async def test_resolve_success() -> None:
    """取到邮箱 / 手机号 / locale。"""
    client = _Client(
        body={
            "code": 0,
            "data": {
                "list": [{"email": "a@b.c", "phone": "13800000000", "locale": "en-US"}],
                "total": 1,
            },
        }
    )
    info = await RecipientResolver(client=client).resolve(1)  # pyright: ignore[reportArgumentType]
    assert info == RecipientInfo(email="a@b.c", phone="13800000000", locale="en-US")


async def test_resolve_empty_and_invalid() -> None:
    """空用户返回空；非 2xx / 结构非法抛服务不可用。"""
    empty = await RecipientResolver(client=_Client(body={"data": {"list": []}})).resolve(1)  # pyright: ignore[reportArgumentType]
    assert empty == RecipientInfo()
    with pytest.raises(ServiceUnavailableError):
        await RecipientResolver(client=_Client(status=500)).resolve(1)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ServiceUnavailableError):
        await RecipientResolver(client=_Client(body={"data": {"list": [1]}})).resolve(1)  # pyright: ignore[reportArgumentType]
