"""LLM 适配能力域：统一 Provider 契约（真实外部 / 私有化端点随 AI 阶段回补）。

- `LLM_PROVIDER_TYPES`：Provider 类型清单（`llm` / `embedding` / `ocr`，对应 `sys_ai_provider.type`）。
- `NULL_EMBEDDING_DIM` / `NULL_CHAT_REPLY` / `NULL_OCR_TEXT`：占位返回值（便于断言与链路贯穿）。
- `ChatMessage` / `ChatResult` / `EmbeddingResult` / `OcrResult`：输入与结果数据契约（frozen dataclass）。
- `BaseLlmProvider`：能力域中间层契约（`key = "llm_provider"`）——异步 `chat` / `embedding` / `ocr`，
  均带可选 `provider_key` / `model`（真实实现按 `sys_ai_provider` 选择端点与模型）。
- `get_llm_provider`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：外部 / 私有化端点切换不侵入业务（模型切换只改配置）；AI 接口独立限流与预算、RAG 管线、
八项 AI 能力、`ai_chat_log` 交互审计与安全闸门（`ai.auto_execute` / `ai.auto_approve`）归 AI 阶段上层。
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "LLM_PROVIDER_TYPES",
    "NULL_CHAT_REPLY",
    "NULL_EMBEDDING_DIM",
    "NULL_OCR_TEXT",
    "BaseLlmProvider",
    "ChatMessage",
    "ChatResult",
    "EmbeddingResult",
    "OcrResult",
    "get_llm_provider",
]

LLM_PROVIDER_TYPES: tuple[str, ...] = ("llm", "embedding", "ocr")
"""Provider 类型清单（对应 `sys_ai_provider.type`）；占位期仅登记不校验。"""

NULL_EMBEDDING_DIM = 1024
"""占位向量维度（`NullLlmProvider.embedding` 生成零向量；真实维度随所选模型）。"""

NULL_CHAT_REPLY = "null-chat-reply"
"""占位对话回复（NullLlmProvider.chat 固定返回，便于断言）。"""

NULL_OCR_TEXT = "null-ocr-text"
"""占位识别文本（NullLlmProvider.ocr 固定返回，便于断言）。"""


@dataclass(frozen=True)
class ChatMessage(BaseObject):
    """对话消息。"""

    content: str
    """消息内容。"""

    role: str = "user"
    """角色（`user` / `assistant` / `system`）。"""


@dataclass(frozen=True)
class ChatResult(BaseObject):
    """对话结果。"""

    content: str
    """回复内容。"""

    model: str | None = None
    """实际使用的模型。"""

    provider_key: str | None = None
    """实际使用的 Provider（`sys_ai_provider.provider_key`）。"""


@dataclass(frozen=True)
class EmbeddingResult(BaseObject):
    """向量化结果。"""

    vectors: tuple[tuple[float, ...], ...]
    """向量列表（每条文本一个向量，与入参 `texts` 等长）。"""

    model: str | None = None
    """实际使用的模型。"""

    provider_key: str | None = None
    """实际使用的 Provider。"""


@dataclass(frozen=True)
class OcrResult(BaseObject):
    """识别结果。"""

    text: str
    """识别文本。"""

    model: str | None = None
    """实际使用的模型。"""

    provider_key: str | None = None
    """实际使用的 Provider。"""


class BaseLlmProvider(BasePluggable, ABC):
    """LLM 适配契约：对话 / 向量化 / 识别。"""

    key: str = "llm_provider"
    plugin_key: str = "llm_provider"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> ChatResult:
        """对话（外部 API / 私有化端点）。

        Args:
            messages: 多轮对话消息。
            provider_key: Provider 标识（按 `sys_ai_provider` 选择端点）；None 用默认。
            model: 模型名（覆盖默认）；None 用默认。

        Returns:
            ChatResult: 对话结果。
        """

    @abstractmethod
    async def embedding(
        self,
        texts: Sequence[str],
        *,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> EmbeddingResult:
        """文本向量化（RAG 管线消费）。

        Args:
            texts: 待向量化文本列表。
            provider_key: Provider 标识；None 用默认。
            model: 模型名；None 用默认。

        Returns:
            EmbeddingResult: 向量化结果（与 `texts` 等长）。
        """

    @abstractmethod
    async def ocr(
        self,
        image: bytes,
        *,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> OcrResult:
        """图片文字识别（扫描件解析）。

        Args:
            image: 图片字节。
            provider_key: Provider 标识；None 用默认。
            model: 模型名；None 用默认。

        Returns:
            OcrResult: 识别结果。
        """


def get_llm_provider(request: Request) -> BaseLlmProvider:
    """取应用级 LLM Provider（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseLlmProvider: 应用装配的 Provider 实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseLlmProvider",
        resolve_plugin(
            "llm_provider",
            settings.llm_provider.provider,
            expected_version=BaseLlmProvider.contract_version,
        ),
    )
