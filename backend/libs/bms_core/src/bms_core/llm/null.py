"""llm 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.llm.base.py 迁入）。"""

from collections.abc import Sequence

from bms_core.core.capability import BaseNullObject
from bms_core.llm.base import (
    NULL_CHAT_REPLY,
    NULL_EMBEDDING_DIM,
    NULL_OCR_TEXT,
    BaseLlmProvider,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    OcrResult,
)

__all__ = [
    "NullLlmProvider",
]


class NullLlmProvider(BaseLlmProvider, BaseNullObject):
    """占位 LLM Provider：固定返回（不调模型，未接入真实实现时使用）。"""

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> ChatResult:
        """恒定返回占位回复。

        Args:
            messages: 对话消息（占位忽略）。
            provider_key: Provider 标识（占位回显）。
            model: 模型名（占位回显）。

        Returns:
            ChatResult: 占位回复（content 为 `NULL_CHAT_REPLY`）。
        """
        return ChatResult(content=NULL_CHAT_REPLY, model=model, provider_key=provider_key)

    async def embedding(
        self,
        texts: Sequence[str],
        *,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> EmbeddingResult:
        """恒定返回固定维度零向量。

        Args:
            texts: 待向量化文本（占位仅取条数）。
            provider_key: Provider 标识（占位回显）。
            model: 模型名（占位回显）。

        Returns:
            EmbeddingResult: 零向量结果（每条维度 `NULL_EMBEDDING_DIM`）。
        """
        zero_vector = tuple(0.0 for _ in range(NULL_EMBEDDING_DIM))
        return EmbeddingResult(
            vectors=tuple(zero_vector for _ in texts),
            model=model,
            provider_key=provider_key,
        )

    async def ocr(
        self,
        image: bytes,
        *,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> OcrResult:
        """恒定返回占位识别文本。

        Args:
            image: 图片字节（占位忽略）。
            provider_key: Provider 标识（占位回显）。
            model: 模型名（占位回显）。

        Returns:
            OcrResult: 占位识别结果（text 为 `NULL_OCR_TEXT`）。
        """
        return OcrResult(text=NULL_OCR_TEXT, model=model, provider_key=provider_key)
