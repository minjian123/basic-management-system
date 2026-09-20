"""AI 对话基座契约测试（Kiwi 820）：三契约 / 常量与数据契约 / 空实现 / 依赖解析 / 占位路由 / 表声明。"""

from collections.abc import AsyncIterator, Sequence

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_chat_action_gate, get_chat_session_store, get_chat_stream
from app.chat.base import (
    AI_AUTO_APPROVE_KEY,
    AI_AUTO_EXECUTE_KEY,
    CHAT_ACTION_STATUSES,
    CHAT_CITATION_TYPES,
    CHAT_MESSAGE_STATUSES,
    CHAT_MODULES,
    CHAT_RESULT_KINDS,
    CHAT_STREAM_EVENT_TYPES,
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
from app.chat.null import NullChatActionGate, NullChatSessionStore, NullChatStream
from app.core.capability import BaseCapability, BaseNullObject
from app.core.plugin import BasePluggable, resolve_plugin
from app.llm.base import NULL_CHAT_REPLY, ChatMessage
from app.main import ApplicationFactory, lifespan
from app.models.ai import AiChatLog

API = "/api/v1/chat"


class _InMemoryChatStream(BaseChatStream):
    """测试用内存流式对话（验证停止语义；真实流式随 AI 阶段）。"""

    def __init__(self) -> None:
        self._active: dict[str, bool] = {}
        self._seq = 0

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        module: str,
        session_id: str | None = None,
        provider_key: str | None = None,
        model: str | None = None,
    ) -> ChatStreamHandle:
        del messages, module, session_id, provider_key, model
        self._seq += 1
        stream_id = f"s{self._seq}"
        self._active[stream_id] = True
        return ChatStreamHandle(stream_id=stream_id, events=self._events(stream_id))

    async def _events(self, stream_id: str) -> AsyncIterator[ChatStreamEvent]:
        yield ChatStreamEvent(type="token", stream_id=stream_id, content="你")
        if self._active.get(stream_id):
            yield ChatStreamEvent(type="done", stream_id=stream_id, content="你好", audit_id="a1")

    async def stop(self, stream_id: str) -> bool:
        if stream_id in self._active:
            self._active[stream_id] = False
            return True
        return False


class _InMemoryChatSessionStore(BaseChatSessionStore):
    """测试用内存会话查询（验证派生视图查询口径）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, list[ChatSessionMessage]] = {}

    def add(self, session: ChatSession, messages: Sequence[ChatSessionMessage] = ()) -> ChatSession:
        self._sessions[session.id] = session
        self._messages[session.id] = list(messages)
        return session

    async def list_sessions(self, *, module: str | None = None) -> Sequence[ChatSession]:
        items = [s for s in self._sessions.values() if module is None or s.module == module]
        return sorted(items, key=lambda s: s.id)

    async def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    async def list_messages(self, session_id: str) -> Sequence[ChatSessionMessage]:
        return self._messages.get(session_id, [])

    async def delete_session(self, session_id: str) -> bool:
        self._messages.pop(session_id, None)
        return self._sessions.pop(session_id, None) is not None


class _InMemoryChatActionGate(BaseChatActionGate):
    """测试用内存确认 / 撤销（验证确认前置与撤销状态）。"""

    def __init__(self) -> None:
        self._confirmed: set[str] = set()

    async def confirm_action(self, action_id: str) -> ChatActionResult:
        self._confirmed.add(action_id)
        return ChatActionResult(action_id=action_id, ok=True, status="confirmed")

    async def revoke_action(self, action_id: str) -> ChatActionResult:
        if action_id not in self._confirmed:
            return ChatActionResult(action_id=action_id, ok=False, status="rejected", detail="未确认")
        return ChatActionResult(action_id=action_id, ok=True, status="revoked")


@pytest.mark.kiwi_id(820)
def test_contract_inheritance_and_identity() -> None:
    """三契约继承与能力域标识；三空实现占位标记。"""
    for contract in (BaseChatStream, BaseChatSessionStore, BaseChatActionGate):
        assert issubclass(contract, BasePluggable)
        assert issubclass(contract, BaseCapability)
    assert BaseChatStream.key == BaseChatStream.plugin_key == "chat_stream"
    assert BaseChatSessionStore.key == BaseChatSessionStore.plugin_key == "chat_session_store"
    assert BaseChatActionGate.key == BaseChatActionGate.plugin_key == "chat_action_gate"

    for null_cls in (NullChatStream, NullChatSessionStore, NullChatActionGate):
        assert issubclass(null_cls, BaseNullObject)

    stream = NullChatStream()
    assert stream.placeholder is True
    assert "占位实现" in stream.describe()


@pytest.mark.kiwi_id(820)
def test_constants_and_data_contracts() -> None:
    """常量取值与数据契约字段集 / 默认值。"""
    assert CHAT_STREAM_EVENT_TYPES == ("token", "done", "error")
    assert CHAT_MESSAGE_STATUSES == ("streaming", "done", "error", "stopped")
    assert CHAT_MODULES == ("ask", "report", "approval", "doc_qa")
    assert CHAT_CITATION_TYPES == ("file", "article", "record")
    assert CHAT_RESULT_KINDS == ("chart", "table")
    assert CHAT_ACTION_STATUSES == ("confirmed", "revoked", "rejected", "unknown")
    assert AI_AUTO_EXECUTE_KEY == "ai.auto_execute"
    assert AI_AUTO_APPROVE_KEY == "ai.auto_approve"

    assert set(ChatStreamEvent.model_fields) == {"type", "stream_id", "content", "audit_id", "error"}
    assert set(ChatSession.model_fields) == {"id", "title", "module", "message_count", "updated_at"}
    assert set(ChatSessionMessage.model_fields) == {
        "id",
        "session_id",
        "role",
        "status",
        "content",
        "result",
        "citations",
        "risks",
        "audit_id",
        "created_at",
    }
    assert set(ChatActionResult.model_fields) == {"action_id", "ok", "status", "detail"}

    event = ChatStreamEvent(type="token", stream_id="s1")
    assert event.content == ""
    assert event.audit_id is None
    assert event.error is None

    session = ChatSession(id="sess-1")
    assert session.title == ""
    assert session.module == "ask"
    assert session.message_count == 0
    assert session.updated_at is None

    message = ChatSessionMessage(id="m1", session_id="sess-1")
    assert message.role == "assistant"
    assert message.status == "done"
    assert message.result is None
    assert message.citations == []
    assert message.risks == []
    assert message.audit_id is None

    result = ChatActionResult(action_id="a1")
    assert result.ok is False
    assert result.status == "unknown"
    assert result.detail is None


@pytest.mark.kiwi_id(820)
async def test_null_stream_fixed_returns() -> None:
    """占位流式：句柄流标识固定、事件序列单条 done、stop 恒 False。"""
    stream = NullChatStream()
    handle = await stream.stream([ChatMessage(content="hi")], module="ask")
    assert isinstance(handle, ChatStreamHandle)
    assert handle.stream_id == NULL_CHAT_STREAM_ID

    events = [event async for event in handle.events]
    assert len(events) == 1
    assert events[0].type == "done"
    assert events[0].stream_id == NULL_CHAT_STREAM_ID
    assert events[0].content == NULL_CHAT_REPLY

    assert await stream.stop(NULL_CHAT_STREAM_ID) is False


@pytest.mark.kiwi_id(820)
async def test_null_session_store_and_action_gate() -> None:
    """占位会话查询空集 / None；占位确认撤销恒 unknown。"""
    store = NullChatSessionStore()
    assert await store.list_sessions() == ()
    assert await store.list_sessions(module="report") == ()
    assert await store.get_session("sess-1") is None
    assert await store.list_messages("sess-1") == ()
    assert await store.delete_session("sess-1") is False

    gate = NullChatActionGate()
    confirmed = await gate.confirm_action("a1")
    assert confirmed.status == "unknown"
    assert confirmed.ok is False
    revoked = await gate.revoke_action("a1")
    assert revoked.status == "unknown"
    assert revoked.action_id == "a1"


@pytest.mark.kiwi_id(820)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配三空实现；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.chat_stream, NullChatStream)
        assert isinstance(app.state.chat_session_store, NullChatSessionStore)
        assert isinstance(app.state.chat_action_gate, NullChatActionGate)
        assert resolve_plugin("chat_stream", None) is app.state.chat_stream
        assert resolve_plugin("chat_session_store", None) is app.state.chat_session_store
        assert resolve_plugin("chat_action_gate", None) is app.state.chat_action_gate


@pytest.mark.kiwi_id(820)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：单条 done / stop false / 会话空 / 确认撤销 unknown。"""
    streamed = await client.post(f"{API}/stream", json={"messages": [{"content": "hi"}], "module": "ask"})
    assert streamed.status_code == 200
    data = streamed.json()["data"]
    assert data["stream_id"] == NULL_CHAT_STREAM_ID
    assert len(data["events"]) == 1
    assert data["events"][0] == {
        "type": "done",
        "stream_id": NULL_CHAT_STREAM_ID,
        "content": NULL_CHAT_REPLY,
        "audit_id": None,
        "error": None,
    }

    stopped = await client.post(f"{API}/stop", json={"stream_id": NULL_CHAT_STREAM_ID})
    assert stopped.json()["data"] == {"stopped": False}

    sessions = await client.get(f"{API}/sessions")
    assert sessions.json()["data"] == []

    filtered = await client.get(f"{API}/sessions", params={"module": "report"})
    assert filtered.json()["data"] == []

    detail = await client.get(f"{API}/sessions/sess-1")
    assert detail.json()["data"] is None

    messages = await client.get(f"{API}/sessions/sess-1/messages")
    assert messages.json()["data"] == []

    deleted = await client.delete(f"{API}/sessions/sess-1")
    assert deleted.json()["data"] is False

    confirmed = await client.post(f"{API}/actions/a1/confirm")
    assert confirmed.json()["data"]["status"] == "unknown"

    revoked = await client.post(f"{API}/actions/a1/revoke")
    assert revoked.json()["data"]["status"] == "unknown"


@pytest.mark.kiwi_id(820)
async def test_ai_chat_log_table_declaration() -> None:
    """表声明：ai_chat_log 表名与关键字段存在（派生视图分组键）。"""
    assert AiChatLog.__tablename__ == "ai_chat_log"
    for field_name in ("user_id", "tenant_id", "session_id", "module", "status", "tokens", "cost"):
        assert field_name in AiChatLog.__table__.columns


@pytest.mark.kiwi_id(820)
async def test_routes_with_in_memory_implementations() -> None:
    """占位路由 + 内存实现：停止语义、会话查询与删除、确认前置。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        stream = _InMemoryChatStream()
        store = _InMemoryChatSessionStore()
        store.add(
            ChatSession(id="sess-1", title="问数", module="report", message_count=1),
            [ChatSessionMessage(id="m1", session_id="sess-1", content="上月销量")],
        )
        gate = _InMemoryChatActionGate()
        app.dependency_overrides[get_chat_stream] = lambda: stream
        app.dependency_overrides[get_chat_session_store] = lambda: store
        app.dependency_overrides[get_chat_action_gate] = lambda: gate
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sessions = await client.get(f"{API}/sessions", params={"module": "report"})
            assert len(sessions.json()["data"]) == 1
            assert (await client.get(f"{API}/sessions/sess-1")).json()["data"]["title"] == "问数"
            assert len((await client.get(f"{API}/sessions/sess-1/messages")).json()["data"]) == 1

            streamed = await client.post(f"{API}/stream", json={"messages": [{"content": "hi"}]})
            stream_id = streamed.json()["data"]["stream_id"]
            assert streamed.json()["data"]["events"][-1]["type"] == "done"
            assert (await client.post(f"{API}/stop", json={"stream_id": stream_id})).json()["data"] == {"stopped": True}

            rejected = await client.post(f"{API}/actions/a1/revoke")
            assert rejected.json()["data"]["status"] == "rejected"
            await client.post(f"{API}/actions/a1/confirm")
            assert (await client.post(f"{API}/actions/a1/revoke")).json()["data"]["status"] == "revoked"

            assert (await client.delete(f"{API}/sessions/sess-1")).json()["data"] is True
            assert (await client.get(f"{API}/sessions/sess-1")).json()["data"] is None
