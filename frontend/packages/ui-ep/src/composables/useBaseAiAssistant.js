/** AI 助手组件基类投影：把核心 `BaseAiAssistant` 投影为组合式（四模式 / 会话 / 流式 / 二次确认与撤销）。 */
import { AI_CHAT_PERM, BaseAccess, BaseAiAssistant, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体权限上下文（投影内部使用）。 */
class ProjectionAccess extends BaseAccess {
}
/** 具体 AI 助手（可实例化）。 */
class AssistantState extends BaseAiAssistant {
}
/**
 * 使用 AI 助手组件基类投影。
 *
 * @param options 选项。
 * @returns AI 助手基类实例与响应式面。
 */
export function useBaseAiAssistant(options = {}) {
    const center = new AssistantState();
    if (options.mode !== undefined) {
        center.setMode(options.mode);
    }
    if (options.sessions !== undefined) {
        center.setSessions(options.sessions);
    }
    if (options.messages !== undefined) {
        center.setMessages(options.messages);
    }
    if (options.autoExecute !== undefined) {
        center.setAutoExecute(options.autoExecute);
    }
    if (options.autoApprove !== undefined) {
        center.setAutoApprove(options.autoApprove);
    }
    if (options.jobs !== undefined) {
        center.setJobs(options.jobs);
    }
    if (options.stream !== undefined) {
        center.setStream(markRaw(toRaw(options.stream)));
    }
    if (options.access !== undefined) {
        center.setAccess(markRaw(toRaw(options.access)));
    }
    else if (options.accessCodes !== undefined) {
        const access = new ProjectionAccess();
        access.setCodes(options.accessCodes);
        center.setAccess(access);
    }
    if (options.optionSource !== undefined) {
        center.setOptionSource(options.optionSource);
    }
    center.setReady(options.ready ?? false);
    const ready = ref(center.ready);
    const degraded = ref(center.degraded);
    const phase = ref(center.phase);
    const errorMessage = ref(center.errorMessage);
    const errorCode = ref(center.errorCode);
    const mode = ref(center.mode);
    const sessions = ref([...center.sessions]);
    const activeSessionId = ref(center.activeSessionId);
    const messages = ref([...center.messages]);
    const streaming = ref(center.streaming);
    const streamingMessageId = ref(center.streamingMessageId);
    const autoExecute = ref(center.autoExecute);
    const autoApprove = ref(center.autoApprove);
    const pendingAction = ref(center.pendingAction);
    const canChat = ref(center.canChat);
    const canManage = ref(center.canManage);
    const canSend = ref(center.canSend);
    const canStopStreaming = ref(center.canStopStreaming);
    const canAutoExecute = ref(center.canAutoExecute);
    const autoApproveAvailable = ref(center.autoApproveAvailable);
    const requestCount = ref(center.requestCount);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = center.ready;
        degraded.value = center.degraded;
        phase.value = center.phase;
        errorMessage.value = center.errorMessage;
        errorCode.value = center.errorCode;
        mode.value = center.mode;
        sessions.value = [...center.sessions];
        activeSessionId.value = center.activeSessionId;
        messages.value = [...center.messages];
        streaming.value = center.streaming;
        streamingMessageId.value = center.streamingMessageId;
        autoExecute.value = center.autoExecute;
        autoApprove.value = center.autoApprove;
        pendingAction.value = center.pendingAction;
        canChat.value = center.canChat;
        canManage.value = center.canManage;
        canSend.value = center.canSend;
        canStopStreaming.value = center.canStopStreaming;
        canAutoExecute.value = center.canAutoExecute;
        autoApproveAvailable.value = center.autoApproveAvailable;
        requestCount.value = center.requestCount;
    };
    const off = center.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        center.dispose();
    });
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    return {
        center,
        ready,
        degraded,
        phase,
        errorMessage,
        errorCode,
        mode,
        sessions,
        activeSessionId,
        messages,
        streaming,
        streamingMessageId,
        autoExecute,
        autoApprove,
        pendingAction,
        canChat,
        canManage,
        canSend,
        canStopStreaming,
        canAutoExecute,
        autoApproveAvailable,
        requestCount,
        setReady: (value) => run(() => center.setReady(value)),
        setJobs: (jobs) => run(() => center.setJobs(jobs)),
        setStream: (adapter) => run(() => center.setStream(adapter === undefined ? undefined : markRaw(toRaw(adapter)))),
        setAccessCodes: (codes) => {
            const access = new ProjectionAccess();
            access.setCodes(codes);
            run(() => center.setAccess(access));
        },
        setMode: (value) => run(() => center.setMode(value)),
        setSessions: (value) => run(() => center.setSessions(value)),
        setMessages: (value) => run(() => center.setMessages(value)),
        selectSession: (id) => run(() => center.selectSession(id)),
        newSession: (value) => run(() => center.newSession(value)),
        removeSession: async (id) => {
            const value = await center.removeSession(id);
            sync();
            return value;
        },
        appendLocalMessage: (message) => run(() => center.appendLocalMessage(message)),
        setAutoExecute: (value) => run(() => center.setAutoExecute(value)),
        setAutoApprove: (value) => run(() => center.setAutoApprove(value)),
        setPendingAction: (action) => run(() => center.setPendingAction(action)),
        loadSessions: async (input) => {
            const value = await center.loadSessions(input);
            sync();
            return value;
        },
        loadMessages: async (sessionId) => {
            const value = await center.loadMessages(sessionId);
            sync();
            return value;
        },
        send: async (input) => {
            const value = await center.send(input);
            sync();
            return value;
        },
        appendChunk: (delta) => {
            center.appendChunk(delta);
            sync();
        },
        stop: async () => {
            const value = await center.stop();
            sync();
            return value;
        },
        regenerate: async (messageId) => {
            const value = await center.regenerate(messageId);
            sync();
            return value;
        },
        retry: async () => {
            const value = await center.retry();
            sync();
            return value;
        },
        confirmAction: async (actionId) => {
            const value = await center.confirmAction(actionId);
            sync();
            return value;
        },
        revokeAction: async (actionId) => {
            const value = await center.revokeAction(actionId);
            sync();
            return value;
        },
        refreshDatasets: async () => {
            await center.refreshDatasets();
            sync();
        },
        dispose: () => {
            off();
            center.dispose();
        },
    };
}
/** 供宿主复用的对话权限码。 */
export const AI_CHAT_PERMISSION = AI_CHAT_PERM;
