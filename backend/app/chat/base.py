"""AI 对话能力域：流式对话 / 会话查询 / 自动执行确认撤销三契约（真实流式与会话随 AI 阶段回补）。

- 常量：事件类型 `CHAT_STREAM_EVENT_TYPES`、消息状态 `CHAT_MESSAGE_STATUSES`、四模式 `CHAT_MODULES`、
  引用类型 `CHAT_CITATION_TYPES`、结果形态 `CHAT_RESULT_KINDS`、动作状态 `CHAT_ACTION_STATUSES`、
  开关键 `AI_AUTO_EXECUTE_KEY` / `AI_AUTO_APPROVE_KEY`、占位流标识 `NULL_CHAT_STREAM_ID`。
- 数据契约：`ChatStreamEvent` / `ChatCitation` / `ChatMessageResult` / `ChatSessionMessage` /
  `ChatSession` / `ChatActionResult`（`BaseSchema`）+ `ChatStreamHandle`（运行时句柄）。
- `BaseChatStream`（`key = "chat_stream"`）：异步 `stream(messages, *, module, ...) -> ChatStreamHandle`
  （增量事件序列 `token` / `done` / `error` + 审计标识）与 `stop(stream_id)`。
- `BaseChatSessionStore`（`key = "chat_session_store"`）：`list_sessions` / `get_session` / `list_messages`
  / `delete_session`。
- `BaseChatActionGate`（`key = "chat_action_gate"`）：`confirm_action` / `revoke_action`。
- 提供者 `get_chat_stream` / `get_chat_session_store` / `get_chat_action_gate`（应用级单例；公共依赖经
  `app/api/deps.py` 统一导出）。

口径：**契约只描述事件语义、不绑定传输实现**（SSE / WebSocket 报文由实现决定）；会话是 `ai_chat_log`
审计数据的**派生视图**（按用户聚合，`session_id` 为分组键），不另建独立会话事实源。自动执行类操作执行前
**强制二次确认**，缺少确认的自动执行请求一律拒绝，撤销动作落审计；开关 `ai.auto_execute` /
`ai.auto_approve` 默认关闭、各自独立、`ai.auto_approve` 依赖 `ai.auto_execute` 开启（未开启时配置
拒绝保存并强制关闭），开启时仅限配置白名单（写接口 / 审批节点）——占位不读 `sys_config`。真实 Provider
调用 / 流式传输 / 会话投影 / 确认撤销执行 / 权限码 `ai:chat` 归 AI 与 RBAC 阶段上层。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import Request
from pydantic import Field

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.llm.base import ChatMessage
from app.schemas.base import BaseSchema

__all__ = [
    "AI_AUTO_APPROVE_KEY",
    "AI_AUTO_EXECUTE_KEY",
    "CHAT_ACTION_STATUSES",
    "CHAT_CITATION_TYPES",
    "CHAT_MESSAGE_ROLES",
    "CHAT_MESSAGE_STATUSES",
    "CHAT_MODULES",
    "CHAT_RESULT_KINDS",
    "CHAT_STREAM_EVENT_TYPES",
    "NULL_CHAT_STREAM_ID",
    "BaseChatActionGate",
    "BaseChatSessionStore",
    "BaseChatStream",
    "ChatActionResult",
    "ChatCitation",
    "ChatMessageResult",
    "ChatSession",
    "ChatSessionMessage",
    "ChatStreamEvent",
    "ChatStreamHandle",
    "get_chat_action_gate",
    "get_chat_session_store",
    "get_chat_stream",
]

CHAT_STREAM_EVENT_TYPES: tuple[str, ...] = ("token", "done", "error")
"""增量事件类型：`token` 增量片段 / `done` 结束 / `error` 错误。"""

CHAT_MESSAGE_STATUSES: tuple[str, ...] = ("streaming", "done", "error", "stopped")
"""消息状态（与前端 `AiMessageStatus` 同源）。"""

CHAT_MODULES: tuple[str, ...] = ("ask", "report", "approval", "doc_qa")
"""四模式：问答 / 问数 / 审批辅助 / 文档问答（与前端 `AiMode` 同源）。"""

CHAT_MESSAGE_ROLES: tuple[str, ...] = ("user", "assistant", "system")
"""消息角色。"""

CHAT_CITATION_TYPES: tuple[str, ...] = ("file", "article", "record")
"""引用来源类型（文件 / 帮助文章 / 业务记录）。"""

CHAT_RESULT_KINDS: tuple[str, ...] = ("chart", "table")
"""问数结果形态（图表复用前端图表卡 / 表格）。"""

CHAT_ACTION_STATUSES: tuple[str, ...] = ("confirmed", "revoked", "rejected", "unknown")
"""确认 / 撤销结果状态。"""

AI_AUTO_EXECUTE_KEY = "ai.auto_execute"
"""自动执行写操作开关键（`sys_config`；默认关闭，真实读取随 AI 阶段）。"""

AI_AUTO_APPROVE_KEY = "ai.auto_approve"
"""自动审批开关键（`sys_config`；默认关闭且依赖 `ai.auto_execute` 开启，真实读取随 AI 阶段）。"""

NULL_CHAT_STREAM_ID = "null-stream"
"""占位流标识（`NullChatStream` 固定返回，便于断言）。"""


class ChatStreamEvent(BaseSchema):
    """流式增量事件（`token` / `done` / `error`）。"""

    type: str = Field(description="事件类型（token / done / error）")
    stream_id: str = Field(description="流标识（供 stop 中断）")
    content: str = Field(default="", description="增量片段（done 为完整文本）")
    audit_id: str | None = Field(default=None, description="审计标识（对应 ai_chat_log.id）")
    error: str | None = Field(default=None, description="错误摘要（error 事件）")


class ChatCitation(BaseSchema):
    """对话引用来源（文档问答）。"""

    type: str = Field(default="file", description="来源类型（file / article / record）")
    title: str = Field(description="来源标题")
    id: str = Field(description="来源标识")


class ChatMessageResult(BaseSchema):
    """问数结果（图表 / 表格，复用前端图表卡）。"""

    kind: str = Field(default="chart", description="结果形态（chart / table）")
    chart_type: str | None = Field(default=None, description="图表类型（kind=chart）")
    dataset_id: str | None = Field(default=None, description="数据集标识（问数）")
    rows: list[dict[str, object]] = Field(default_factory=list[dict[str, object]], description="行数据")


class ChatSessionMessage(BaseSchema):
    """会话消息（`ai_chat_log` 审计数据派生）。"""

    id: str = Field(description="消息标识")
    session_id: str = Field(description="所属会话标识")
    role: str = Field(default="assistant", description="角色（user / assistant / system）")
    status: str = Field(default="done", description="状态（streaming / done / error / stopped）")
    content: str = Field(default="", description="消息文本")
    result: ChatMessageResult | None = Field(default=None, description="问数结果（chart / table）")
    citations: list[ChatCitation] = Field(default_factory=list[ChatCitation], description="引用来源")
    risks: list[str] = Field(default_factory=list, description="风险提示")
    audit_id: str | None = Field(default=None, description="审计标识（对应 ai_chat_log.id）")
    created_at: datetime | None = Field(default=None, description="创建时间（UTC）")


class ChatSession(BaseSchema):
    """会话（`ai_chat_log` 审计数据派生视图，按用户聚合）。"""

    id: str = Field(description="会话标识")
    title: str = Field(default="", description="会话标题")
    module: str = Field(default="ask", description="模式（ask / report / approval / doc_qa）")
    message_count: int = Field(default=0, ge=0, description="消息数")
    updated_at: datetime | None = Field(default=None, description="最近更新时间（UTC）")


class ChatActionResult(BaseSchema):
    """自动执行确认 / 撤销结果。"""

    action_id: str = Field(description="动作标识")
    ok: bool = Field(default=False, description="是否成功")
    status: str = Field(default="unknown", description="状态（confirmed / revoked / rejected / unknown）")
    detail: str | None = Field(default=None, description="补充说明")


@dataclass(frozen=True)
class ChatStreamHandle(BaseObject):
    """流式对话句柄：流标识 + 增量事件序列（运行时句柄，不走 JSON 序列化）。"""

    stream_id: str
    """流标识（供 `stop(stream_id)` 中断在途流）。"""

    events: AsyncIterator[ChatStreamEvent]
    """增量事件序列（`token` / `done` / `error`）。"""


class BaseChatStream(BasePluggable, ABC):
    """流式对话契约：发起流与中断在途流。"""

    key: str = "chat_stream"
    plugin_key: str = "chat_stream"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        module: str,
        session_id: str | None = None,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> ChatStreamHandle:
        """发起流式对话（返回句柄：流标识 + 事件序列）。

        Args:
            messages: 多轮对话消息（复用 02-18 `ChatMessage`）。
            module: 模式（`ask` / `report` / `approval` / `doc_qa`）。
            session_id: 会话标识；None 表示新会话。
            provider_key: Provider 标识（按 `sys_ai_provider` 选择端点）；None 用默认。
            model: 模型名（覆盖默认）；None 用默认。

        Returns:
            ChatStreamHandle: 流句柄（`stream_id` + 事件序列）。
        """

    @abstractmethod
    async def stop(self, stream_id: str) -> bool:
        """中断在途流。

        Args:
            stream_id: 流标识。

        Returns:
            bool: 是否命中并中断在途流。
        """


class BaseChatSessionStore(BasePluggable, ABC):
    """会话查询契约（`ai_chat_log` 审计数据的派生视图，按当前用户聚合）。"""

    key: str = "chat_session_store"
    plugin_key: str = "chat_session_store"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def list_sessions(self, *, module: str | None = None) -> Sequence[ChatSession]:
        """列当前用户会话（可按模式过滤）。

        Args:
            module: 模式过滤；None 表示全部。

        Returns:
            Sequence[ChatSession]: 会话列表（占位空集）。
        """

    @abstractmethod
    async def get_session(self, session_id: str) -> ChatSession | None:
        """取单会话。

        Args:
            session_id: 会话标识。

        Returns:
            ChatSession | None: 会话；未命中为 None。
        """

    @abstractmethod
    async def list_messages(self, session_id: str) -> Sequence[ChatSessionMessage]:
        """取会话消息（升序；分页随真实实现）。

        Args:
            session_id: 会话标识。

        Returns:
            Sequence[ChatSessionMessage]: 消息列表（占位空集）。
        """

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除会话。

        Args:
            session_id: 会话标识。

        Returns:
            bool: 是否删除到既有会话。
        """


class BaseChatActionGate(BasePluggable, ABC):
    """自动执行确认 / 撤销契约（安全闸门；真实执行 / 审计随 AI 阶段）。"""

    key: str = "chat_action_gate"
    plugin_key: str = "chat_action_gate"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def confirm_action(self, action_id: str) -> ChatActionResult:
        """二次确认自动执行类操作（缺少确认的自动执行请求一律拒绝）。

        Args:
            action_id: 动作标识。

        Returns:
            ChatActionResult: 确认结果。
        """

    @abstractmethod
    async def revoke_action(self, action_id: str) -> ChatActionResult:
        """撤销已执行结果（撤销动作落审计）。

        Args:
            action_id: 动作标识。

        Returns:
            ChatActionResult: 撤销结果。
        """


def get_chat_stream(request: Request) -> BaseChatStream:
    """取应用级流式对话契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseChatStream: 应用装配的流式对话实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseChatStream",
        resolve_plugin(
            "chat_stream",
            settings.chat_stream.provider,
            expected_version=BaseChatStream.contract_version,
        ),
    )


def get_chat_session_store(request: Request) -> BaseChatSessionStore:
    """取应用级会话查询契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseChatSessionStore: 应用装配的会话查询实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseChatSessionStore",
        resolve_plugin(
            "chat_session_store",
            settings.chat_session_store.provider,
            expected_version=BaseChatSessionStore.contract_version,
        ),
    )


def get_chat_action_gate(request: Request) -> BaseChatActionGate:
    """取应用级自动执行确认 / 撤销契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseChatActionGate: 应用装配的确认 / 撤销实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseChatActionGate",
        resolve_plugin(
            "chat_action_gate",
            settings.chat_action_gate.provider,
            expected_version=BaseChatActionGate.contract_version,
        ),
    )
