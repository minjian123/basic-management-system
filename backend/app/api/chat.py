"""AI 对话占位路由：`/api/v1/chat`（登录即可；真实流式 / 会话 / 执行随 AI 阶段）。

- 流式对话（非流式占位：收集事件后一次性返回）/ 中断；会话列表 / 详情 / 消息 / 删除；自动执行确认 / 撤销。
- 契约口径见 `app/chat/base.py`：会话为 `ai_chat_log` 审计派生视图；事件只描述语义、不绑定传输实现。
"""

from typing import Annotated

from fastapi import Depends, Query

from app.api.base import BaseRouter, require_auth
from app.api.deps import get_chat_action_gate, get_chat_session_store, get_chat_stream
from app.chat.base import BaseChatActionGate, BaseChatSessionStore, BaseChatStream
from app.llm.base import ChatMessage
from app.schemas.chat import (
    ChatStopRequest,
    ChatStopResponse,
    ChatStreamRequest,
    ChatStreamResponse,
)
from app.schemas.common import ApiResponse

router = BaseRouter(
    key="chat",
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(require_auth)],
)

StreamDep = Annotated[BaseChatStream, Depends(get_chat_stream)]
SessionDep = Annotated[BaseChatSessionStore, Depends(get_chat_session_store)]
GateDep = Annotated[BaseChatActionGate, Depends(get_chat_action_gate)]


@router.post("/stream")
async def chat_stream(stream: StreamDep, req: ChatStreamRequest) -> ApiResponse:
    """发起流式对话（非流式占位：收集事件后一次性返回）。

    Args:
        stream: 流式对话契约。
        req: 流式对话请求。

    Returns:
        ApiResponse: 统一响应，data 为 `{stream_id, events}`。
    """
    messages = [ChatMessage(content=item.content, role=item.role) for item in req.messages]
    handle = await stream.stream(messages, module=req.module, session_id=req.session_id)
    events = [event async for event in handle.events]
    return ApiResponse.ok(ChatStreamResponse(stream_id=handle.stream_id, events=events))


@router.post("/stop")
async def chat_stop(stream: StreamDep, req: ChatStopRequest) -> ApiResponse:
    """中断在途流。

    Args:
        stream: 流式对话契约。
        req: 中断请求。

    Returns:
        ApiResponse: 统一响应，data 为 `{stopped}`。
    """
    return ApiResponse.ok(ChatStopResponse(stopped=await stream.stop(req.stream_id)))


@router.get("/sessions")
async def list_chat_sessions(
    store: SessionDep,
    module: Annotated[str | None, Query(description="模式过滤（ask / report / approval / doc_qa）")] = None,
) -> ApiResponse:
    """列当前用户会话（审计派生视图）。

    Args:
        store: 会话查询契约。
        module: 模式过滤。

    Returns:
        ApiResponse: 统一响应，data 为会话列表。
    """
    return ApiResponse.ok(await store.list_sessions(module=module))


@router.get("/sessions/{session_id}")
async def get_chat_session(store: SessionDep, session_id: str) -> ApiResponse:
    """取单会话。

    Args:
        store: 会话查询契约。
        session_id: 会话标识。

    Returns:
        ApiResponse: 统一响应，data 为会话或 null。
    """
    return ApiResponse.ok(await store.get_session(session_id))


@router.get("/sessions/{session_id}/messages")
async def list_chat_messages(store: SessionDep, session_id: str) -> ApiResponse:
    """取会话消息。

    Args:
        store: 会话查询契约。
        session_id: 会话标识。

    Returns:
        ApiResponse: 统一响应，data 为消息列表。
    """
    return ApiResponse.ok(await store.list_messages(session_id))


@router.delete("/sessions/{session_id}")
async def delete_chat_session(store: SessionDep, session_id: str) -> ApiResponse:
    """删除会话。

    Args:
        store: 会话查询契约。
        session_id: 会话标识。

    Returns:
        ApiResponse: 统一响应，data 为是否删除到既有会话。
    """
    return ApiResponse.ok(await store.delete_session(session_id))


@router.post("/actions/{action_id}/confirm")
async def confirm_chat_action(gate: GateDep, action_id: str) -> ApiResponse:
    """二次确认自动执行类操作。

    Args:
        gate: 确认 / 撤销契约。
        action_id: 动作标识。

    Returns:
        ApiResponse: 统一响应，data 为确认结果。
    """
    return ApiResponse.ok(await gate.confirm_action(action_id))


@router.post("/actions/{action_id}/revoke")
async def revoke_chat_action(gate: GateDep, action_id: str) -> ApiResponse:
    """撤销已执行结果。

    Args:
        gate: 确认 / 撤销契约。
        action_id: 动作标识。

    Returns:
        ApiResponse: 统一响应，data 为撤销结果。
    """
    return ApiResponse.ok(await gate.revoke_action(action_id))
