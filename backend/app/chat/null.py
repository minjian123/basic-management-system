"""chat 能力域缺省实现（Null Object）：单次 done / 空会话 / unknown 结果，不做真实流与执行。"""

from collections.abc import AsyncIterator, Sequence

from app.chat.base import (
    NULL_CHAT_STREAM_ID,
    BaseChatActionGate,
    BaseChatSessionStore,
    BaseChatStream,
    ChatActionResult,
    ChatSession,
    ChatSessionMessage,
    ChatStreamEvent,
    ChatStreamHandle,
)
from app.core.capability import BaseNullObject
from app.llm.base import NULL_CHAT_REPLY, ChatMessage

__all__ = [
    "NullChatActionGate",
    "NullChatSessionStore",
    "NullChatStream",
]


class NullChatStream(BaseChatStream, BaseNullObject):
    """占位流式对话：固定返回单次 `done`（占位文本），不调模型、不流式传输。"""

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        module: str,
        session_id: str | None = None,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> ChatStreamHandle:
        """发起流式对话（占位单次 `done`）。

        Args:
            messages: 对话消息（占位忽略）。
            module: 模式（占位忽略）。
            session_id: 会话标识（占位忽略）。
            provider_key: Provider 标识（占位忽略）。
            model: 模型名（占位忽略）。

        Returns:
            ChatStreamHandle: 占位句柄（`stream_id` 固定，事件序列为单条 `done`）。
        """
        del messages, module, session_id, provider_key, model
        return ChatStreamHandle(stream_id=NULL_CHAT_STREAM_ID, events=self._events())

    async def _events(self) -> AsyncIterator[ChatStreamEvent]:
        """占位事件序列：单条 `done`。

        Yields:
            ChatStreamEvent: 单条结束事件（`content` 为 `NULL_CHAT_REPLY`）。
        """
        yield ChatStreamEvent(type="done", stream_id=NULL_CHAT_STREAM_ID, content=NULL_CHAT_REPLY)

    async def stop(self, stream_id: str) -> bool:
        """中断在途流（占位恒无在途流）。

        Args:
            stream_id: 流标识（占位忽略）。

        Returns:
            bool: False。
        """
        del stream_id
        return False


class NullChatSessionStore(BaseChatSessionStore, BaseNullObject):
    """占位会话查询：空集 / None，不查 `ai_chat_log`。"""

    async def list_sessions(self, *, module: str | None = None) -> Sequence[ChatSession]:
        """列当前用户会话（占位恒空）。

        Args:
            module: 模式过滤（占位忽略）。

        Returns:
            Sequence[ChatSession]: 空元组。
        """
        del module
        return ()

    async def get_session(self, session_id: str) -> ChatSession | None:
        """取单会话（占位恒未命中）。

        Args:
            session_id: 会话标识（占位忽略）。

        Returns:
            ChatSession | None: None。
        """
        del session_id
        return None

    async def list_messages(self, session_id: str) -> Sequence[ChatSessionMessage]:
        """取会话消息（占位恒空）。

        Args:
            session_id: 会话标识（占位忽略）。

        Returns:
            Sequence[ChatSessionMessage]: 空元组。
        """
        del session_id
        return ()

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（占位恒无既有会话）。

        Args:
            session_id: 会话标识（占位忽略）。

        Returns:
            bool: False。
        """
        del session_id
        return False


class NullChatActionGate(BaseChatActionGate, BaseNullObject):
    """占位确认 / 撤销：恒定 `unknown`，不执行、不落审计。"""

    async def confirm_action(self, action_id: str) -> ChatActionResult:
        """二次确认自动执行类操作（占位恒未接入）。

        Args:
            action_id: 动作标识（占位回显）。

        Returns:
            ChatActionResult: 占位结果（`status = unknown`）。
        """
        return ChatActionResult(
            action_id=action_id,
            ok=False,
            status="unknown",
            detail="占位实现（未接入真实执行）",
        )

    async def revoke_action(self, action_id: str) -> ChatActionResult:
        """撤销已执行结果（占位恒未接入）。

        Args:
            action_id: 动作标识（占位回显）。

        Returns:
            ChatActionResult: 占位结果（`status = unknown`）。
        """
        return ChatActionResult(
            action_id=action_id,
            ok=False,
            status="unknown",
            detail="占位实现（未接入真实执行）",
        )
