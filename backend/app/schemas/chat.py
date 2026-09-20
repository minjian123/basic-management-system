"""AI 对话占位路由请求 / 响应契约（会话 / 事件 / 动作数据契约见 `app/chat/base.py`）。"""

from pydantic import Field

from app.chat.base import ChatStreamEvent
from app.schemas.base import BaseSchema

__all__ = [
    "ChatMessageInput",
    "ChatStopRequest",
    "ChatStopResponse",
    "ChatStreamRequest",
    "ChatStreamResponse",
]


class ChatMessageInput(BaseSchema):
    """流式请求中的单条消息（路由内转 `app.llm.base.ChatMessage`）。"""

    content: str = Field(description="消息内容")
    role: str = Field(default="user", description="角色（user / assistant / system）")


class ChatStreamRequest(BaseSchema):
    """发起流式对话请求。"""

    messages: list[ChatMessageInput] = Field(default_factory=list[ChatMessageInput], description="多轮对话消息")
    module: str = Field(default="ask", description="模式（ask / report / approval / doc_qa）")
    session_id: str | None = Field(default=None, description="会话标识；缺省为新会话")


class ChatStreamResponse(BaseSchema):
    """流式对话响应（占位路由收集事件后一次性返回）。"""

    stream_id: str = Field(description="流标识")
    events: list[ChatStreamEvent] = Field(default_factory=list[ChatStreamEvent], description="增量事件序列")


class ChatStopRequest(BaseSchema):
    """中断在途流请求。"""

    stream_id: str = Field(description="流标识")


class ChatStopResponse(BaseSchema):
    """中断在途流响应。"""

    stopped: bool = Field(default=False, description="是否命中并中断在途流")
