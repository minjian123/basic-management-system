"""LLM 适配基座契约测试（Kiwi 48）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_llm_provider
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.llm.base import (
    LLM_PROVIDER_TYPES,
    NULL_CHAT_REPLY,
    NULL_EMBEDDING_DIM,
    NULL_OCR_TEXT,
    BaseLlmProvider,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    OcrResult,
)
from bms_core.llm.null import NullLlmProvider
from bms_platform.main import ApplicationFactory, lifespan


@pytest.mark.kiwi_id(48)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseLlmProvider, BaseCapability)
    assert issubclass(NullLlmProvider, BaseLlmProvider)
    assert issubclass(NullLlmProvider, BaseNullObject)
    assert BaseLlmProvider.key == "llm_provider"

    provider = NullLlmProvider()
    assert provider.placeholder is True
    assert "占位实现" in provider.describe()


@pytest.mark.kiwi_id(48)
def test_constants() -> None:
    """Provider 类型清单与占位向量维度常量。"""
    assert LLM_PROVIDER_TYPES == ("llm", "embedding", "ocr")
    assert len(set(LLM_PROVIDER_TYPES)) == len(LLM_PROVIDER_TYPES)
    assert NULL_EMBEDDING_DIM == 1024


@pytest.mark.kiwi_id(48)
def test_data_contracts_defaults_and_frozen() -> None:
    """`ChatMessage` 与三结果契约默认值正确且不可变。"""
    message = ChatMessage(content="你好")
    assert message.role == "user"
    assert ChatResult(content="x").model is None
    assert EmbeddingResult(vectors=((0.0,),)).provider_key is None
    assert OcrResult(text="x").provider_key is None

    field = "role"
    with pytest.raises(FrozenInstanceError):
        setattr(message, field, "system")


@pytest.mark.kiwi_id(48)
async def test_null_chat_fixed() -> None:
    """占位 chat 恒定返回占位回复（model / provider_key 回显）。"""
    provider = NullLlmProvider()
    result = await provider.chat([ChatMessage(content="hi")], provider_key="p1", model="m1")
    assert result == ChatResult(content=NULL_CHAT_REPLY, model="m1", provider_key="p1")
    assert result.content == "null-chat-reply"


@pytest.mark.kiwi_id(48)
async def test_null_embedding_zero_vectors() -> None:
    """占位 embedding 返回固定维度零向量（条数 == texts 条数）。"""
    provider = NullLlmProvider()
    result = await provider.embedding(["a", "b", "c"], provider_key="p1", model="m1")
    assert len(result.vectors) == 3
    assert all(len(vector) == NULL_EMBEDDING_DIM for vector in result.vectors)
    assert all(value == 0.0 for vector in result.vectors for value in vector)
    assert result.model == "m1"
    assert result.provider_key == "p1"


@pytest.mark.kiwi_id(48)
async def test_null_ocr_fixed() -> None:
    """占位 ocr 恒定返回占位文本（model / provider_key 回显）。"""
    provider = NullLlmProvider()
    result = await provider.ocr(b"\x89PNG", provider_key="p1", model="m1")
    assert result == OcrResult(text=NULL_OCR_TEXT, model="m1", provider_key="p1")
    assert result.text == "null-ocr-text"


@pytest.mark.kiwi_id(48)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位 Provider；路由经 get_llm_provider 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.llm_provider, NullLlmProvider)

        @app.get("/llm-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            provider: Annotated[BaseLlmProvider, Depends(get_llm_provider)],
        ) -> dict[str, object]:
            chat = await provider.chat([ChatMessage(content="hi")])
            return {"key": provider.key, "type": type(provider).__name__, "reply": chat.content}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/llm-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "llm_provider", "type": "NullLlmProvider", "reply": "null-chat-reply"}
