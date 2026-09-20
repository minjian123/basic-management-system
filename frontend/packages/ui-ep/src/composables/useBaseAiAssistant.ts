/** AI 助手组件基类投影：把核心 `BaseAiAssistant` 投影为组合式（四模式 / 会话 / 流式 / 二次确认与撤销）。 */

import {
  AI_CHAT_PERM,
  BaseAccess,
  BaseAiAssistant,
  type AiAssistantPhase,
  type AiJobs,
  type AiMessage,
  type AiMode,
  type AiPendingAction,
  type AiSession,
  type AiStreamAdapter,
  type BaseOptionSource,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体权限上下文（投影内部使用）。 */
class ProjectionAccess extends BaseAccess {}

/** 具体 AI 助手（可实例化）。 */
class AssistantState extends BaseAiAssistant {}

/** 投影选项。 */
export interface UseBaseAiAssistantOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 初始模式。 */
  mode?: AiMode
  /** 初始会话列表。 */
  sessions?: AiSession[]
  /** 初始消息流。 */
  messages?: AiMessage[]
  /** 自动执行开关。 */
  autoExecute?: boolean
  /** 自动审批开关。 */
  autoApprove?: boolean
  /** 取数处理函数（未注入即占位零请求）。 */
  jobs?: AiJobs
  /** 流式适配器（未注入即占位）。 */
  stream?: AiStreamAdapter
  /** 权限上下文（优先于 `accessCodes`）。 */
  access?: BaseAccess
  /** 权限码集合（便捷入口，内部构造权限上下文）。 */
  accessCodes?: readonly string[]
  /** 选项源能力（数据集 / 文件）。 */
  optionSource?: BaseOptionSource
}

/** `useBaseAiAssistant` 返回面。 */
export interface UseBaseAiAssistantResult {
  /** AI 助手基类实例。 */
  center: BaseAiAssistant
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 编排阶段（响应式）。 */
  phase: Ref<AiAssistantPhase>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 错误码（响应式）。 */
  errorCode: Ref<number | undefined>
  /** 当前模式（响应式）。 */
  mode: Ref<AiMode>
  /** 会话列表（响应式）。 */
  sessions: Ref<AiSession[]>
  /** 当前会话标识（响应式）。 */
  activeSessionId: Ref<string>
  /** 消息流（响应式）。 */
  messages: Ref<AiMessage[]>
  /** 是否流式输出中（响应式）。 */
  streaming: Ref<boolean>
  /** 流式消息标识（响应式）。 */
  streamingMessageId: Ref<string>
  /** 自动执行开关（响应式）。 */
  autoExecute: Ref<boolean>
  /** 自动审批开关（响应式）。 */
  autoApprove: Ref<boolean>
  /** 待确认动作（响应式）。 */
  pendingAction: Ref<AiPendingAction | undefined>
  /** 是否持对话权限（响应式）。 */
  canChat: Ref<boolean>
  /** 是否持管理权限（响应式）。 */
  canManage: Ref<boolean>
  /** 是否可发送（响应式）。 */
  canSend: Ref<boolean>
  /** 是否可停止（响应式）。 */
  canStopStreaming: Ref<boolean>
  /** 自动执行是否可用（响应式）。 */
  canAutoExecute: Ref<boolean>
  /** 自动审批是否可用（响应式）。 */
  autoApproveAvailable: Ref<boolean>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入取数处理函数。 */
  setJobs: (jobs: AiJobs) => void
  /** 注入 / 移除流式适配器。 */
  setStream: (adapter: AiStreamAdapter | undefined) => void
  /** 设置权限码集合。 */
  setAccessCodes: (codes: readonly string[]) => void
  /** 设置模式。 */
  setMode: (mode: AiMode) => boolean
  /** 设置会话列表。 */
  setSessions: (sessions: readonly AiSession[]) => void
  /** 设置消息流。 */
  setMessages: (messages: readonly AiMessage[]) => void
  /** 切换会话。 */
  selectSession: (id: string) => boolean
  /** 新建会话。 */
  newSession: (mode?: AiMode) => AiSession
  /** 删除会话。 */
  removeSession: (id: string) => Promise<boolean>
  /** 追加本地消息。 */
  appendLocalMessage: (message: unknown) => AiMessage | undefined
  /** 设置自动执行开关。 */
  setAutoExecute: (value: boolean) => void
  /** 设置自动审批开关。 */
  setAutoApprove: (value: boolean) => void
  /** 设置待确认动作。 */
  setPendingAction: (action: unknown) => void
  /** 会话取数。 */
  loadSessions: (input?: { mode?: AiMode | 'all'; keyword?: string }) => Promise<AiSession[] | undefined>
  /** 消息取数。 */
  loadMessages: (sessionId?: string) => Promise<AiMessage[] | undefined>
  /** 发送消息。 */
  send: (input: { content: string; datasetId?: string; fileIds?: string[] }) => Promise<AiMessage | undefined>
  /** 追加流式片段。 */
  appendChunk: (delta: string) => void
  /** 停止。 */
  stop: () => Promise<boolean>
  /** 重新生成。 */
  regenerate: (messageId?: string) => Promise<AiMessage | undefined>
  /** 重试。 */
  retry: () => Promise<AiMessage | undefined>
  /** 确认执行。 */
  confirmAction: (actionId?: string) => Promise<boolean>
  /** 撤销。 */
  revokeAction: (actionId?: string) => Promise<boolean>
  /** 加载数据集选项。 */
  refreshDatasets: () => Promise<void>
  /** 释放（解绑订阅并释放基类实例）。 */
  dispose: () => void
}

/**
 * 使用 AI 助手组件基类投影。
 *
 * @param options 选项。
 * @returns AI 助手基类实例与响应式面。
 */
export function useBaseAiAssistant(options: UseBaseAiAssistantOptions = {}): UseBaseAiAssistantResult {
  const center = new AssistantState()
  if (options.mode !== undefined) {
    center.setMode(options.mode)
  }
  if (options.sessions !== undefined) {
    center.setSessions(options.sessions)
  }
  if (options.messages !== undefined) {
    center.setMessages(options.messages)
  }
  if (options.autoExecute !== undefined) {
    center.setAutoExecute(options.autoExecute)
  }
  if (options.autoApprove !== undefined) {
    center.setAutoApprove(options.autoApprove)
  }
  if (options.jobs !== undefined) {
    center.setJobs(options.jobs)
  }
  if (options.stream !== undefined) {
    center.setStream(markRaw(toRaw(options.stream)))
  }
  if (options.access !== undefined) {
    center.setAccess(markRaw(toRaw(options.access)))
  } else if (options.accessCodes !== undefined) {
    const access = new ProjectionAccess()
    access.setCodes(options.accessCodes)
    center.setAccess(access)
  }
  if (options.optionSource !== undefined) {
    center.setOptionSource(options.optionSource)
  }
  center.setReady(options.ready ?? false)

  const ready = ref(center.ready)
  const degraded = ref(center.degraded)
  const phase = ref<AiAssistantPhase>(center.phase)
  const errorMessage = ref(center.errorMessage)
  const errorCode = ref<number | undefined>(center.errorCode)
  const mode = ref<AiMode>(center.mode)
  const sessions = ref<AiSession[]>([...center.sessions])
  const activeSessionId = ref(center.activeSessionId)
  const messages = ref<AiMessage[]>([...center.messages])
  const streaming = ref(center.streaming)
  const streamingMessageId = ref(center.streamingMessageId)
  const autoExecute = ref(center.autoExecute)
  const autoApprove = ref(center.autoApprove)
  const pendingAction = ref<AiPendingAction | undefined>(center.pendingAction)
  const canChat = ref(center.canChat)
  const canManage = ref(center.canManage)
  const canSend = ref(center.canSend)
  const canStopStreaming = ref(center.canStopStreaming)
  const canAutoExecute = ref(center.canAutoExecute)
  const autoApproveAvailable = ref(center.autoApproveAvailable)
  const requestCount = ref(center.requestCount)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = center.ready
    degraded.value = center.degraded
    phase.value = center.phase
    errorMessage.value = center.errorMessage
    errorCode.value = center.errorCode
    mode.value = center.mode
    sessions.value = [...center.sessions]
    activeSessionId.value = center.activeSessionId
    messages.value = [...center.messages]
    streaming.value = center.streaming
    streamingMessageId.value = center.streamingMessageId
    autoExecute.value = center.autoExecute
    autoApprove.value = center.autoApprove
    pendingAction.value = center.pendingAction
    canChat.value = center.canChat
    canManage.value = center.canManage
    canSend.value = center.canSend
    canStopStreaming.value = center.canStopStreaming
    canAutoExecute.value = center.canAutoExecute
    autoApproveAvailable.value = center.autoApproveAvailable
    requestCount.value = center.requestCount
  }

  const off = center.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    center.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

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
      const access = new ProjectionAccess()
      access.setCodes(codes)
      run(() => center.setAccess(access))
    },
    setMode: (value) => run(() => center.setMode(value)),
    setSessions: (value) => run(() => center.setSessions(value)),
    setMessages: (value) => run(() => center.setMessages(value)),
    selectSession: (id) => run(() => center.selectSession(id)),
    newSession: (value) => run(() => center.newSession(value)),
    removeSession: async (id) => {
      const value = await center.removeSession(id)
      sync()
      return value
    },
    appendLocalMessage: (message) => run(() => center.appendLocalMessage(message)),
    setAutoExecute: (value) => run(() => center.setAutoExecute(value)),
    setAutoApprove: (value) => run(() => center.setAutoApprove(value)),
    setPendingAction: (action) => run(() => center.setPendingAction(action)),
    loadSessions: async (input) => {
      const value = await center.loadSessions(input)
      sync()
      return value
    },
    loadMessages: async (sessionId) => {
      const value = await center.loadMessages(sessionId)
      sync()
      return value
    },
    send: async (input) => {
      const value = await center.send(input)
      sync()
      return value
    },
    appendChunk: (delta) => {
      center.appendChunk(delta)
      sync()
    },
    stop: async () => {
      const value = await center.stop()
      sync()
      return value
    },
    regenerate: async (messageId) => {
      const value = await center.regenerate(messageId)
      sync()
      return value
    },
    retry: async () => {
      const value = await center.retry()
      sync()
      return value
    },
    confirmAction: async (actionId) => {
      const value = await center.confirmAction(actionId)
      sync()
      return value
    },
    revokeAction: async (actionId) => {
      const value = await center.revokeAction(actionId)
      sync()
      return value
    },
    refreshDatasets: async () => {
      await center.refreshDatasets()
      sync()
    },
    dispose: () => {
      off()
      center.dispose()
    },
  }
}

/** 供宿主复用的对话权限码。 */
export const AI_CHAT_PERMISSION = AI_CHAT_PERM
