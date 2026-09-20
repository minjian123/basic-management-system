"""出站集成基座契约测试（Kiwi 52）：契约 / 标识 / 常量 / 数据契约 / 占位固定成功 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_http_client, get_webhook_sender
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import ApplicationFactory, lifespan
from app.outbound.http import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, BaseHttpClient, HttpResponse
from app.outbound.null import NullHttpClient, NullWebhookSender
from app.outbound.webhook import BaseWebhookSender, WebhookResult


@pytest.mark.kiwi_id(52)
def test_inheritance_and_keys() -> None:
    """两契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseHttpClient, BaseCapability)
    assert issubclass(NullHttpClient, BaseHttpClient)
    assert issubclass(NullHttpClient, BaseNullObject)
    assert BaseHttpClient.key == "http_client"

    assert issubclass(BaseWebhookSender, BaseCapability)
    assert issubclass(NullWebhookSender, BaseWebhookSender)
    assert issubclass(NullWebhookSender, BaseNullObject)
    assert BaseWebhookSender.key == "webhook_sender"

    for placeholder in (NullHttpClient(), NullWebhookSender()):
        assert placeholder.placeholder is True
        assert "占位实现" in placeholder.describe()


@pytest.mark.kiwi_id(52)
def test_constants() -> None:
    """默认超时与最大重试次数常量。"""
    assert DEFAULT_TIMEOUT == 10
    assert DEFAULT_MAX_RETRIES == 3


@pytest.mark.kiwi_id(52)
def test_data_contracts_defaults_and_frozen() -> None:
    """`HttpResponse` / `WebhookResult` 默认值正确且不可变。"""
    response = HttpResponse(status_code=200, headers={}, content=b"")
    assert response.status_code == 200

    result = WebhookResult(delivered=True)
    assert result.status_code is None
    assert result.attempts == 1

    field = "delivered"
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, False)


@pytest.mark.kiwi_id(52)
async def test_null_http_client_fixed() -> None:
    """占位 HTTP 客户端固定返回成功响应（不外呼）。"""
    client = NullHttpClient()
    response = await client.request("GET", "https://example.com", timeout=5)
    assert response == HttpResponse(status_code=200, headers={}, content=b"")


@pytest.mark.kiwi_id(52)
async def test_null_webhook_sender_fixed() -> None:
    """占位 Webhook 发送器固定返回投递成功（不外呼）。"""
    sender = NullWebhookSender()
    result = await sender.send("https://example.com/hook", {"id": "1"}, secret="s")
    assert result == WebhookResult(delivered=True, status_code=200, attempts=1)
    assert result.delivered is True


@pytest.mark.kiwi_id(52)
async def test_dependency_providers_resolve() -> None:
    """依赖解析：应用装配两占位单例；路由经两提供者取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.http_client, NullHttpClient)
        assert isinstance(app.state.webhook_sender, NullWebhookSender)

        @app.get("/outbound-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            client: Annotated[BaseHttpClient, Depends(get_http_client)],
            sender: Annotated[BaseWebhookSender, Depends(get_webhook_sender)],
        ) -> dict[str, object]:
            response = await client.request("GET", "https://example.com")
            result = await sender.send("https://example.com/hook", {})
            return {
                "http_key": client.key,
                "http_status": response.status_code,
                "webhook_key": sender.key,
                "delivered": result.delivered,
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/outbound-probe")

        assert resp.status_code == 200
        assert resp.json() == {
            "http_key": "http_client",
            "http_status": 200,
            "webhook_key": "webhook_sender",
            "delivered": True,
        }
