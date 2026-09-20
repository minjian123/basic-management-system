/**
 * AI 助手编排能力基类：四模式会话与消息、流式接收与停止、重生成、结果与引用装配、
 * 自动执行强制二次确认与撤销。
 *
 * 组合权限、提示、数据状态、选项源与异步任务能力基类；会话 / 消息 / 对话处理函数与流式适配器
 * 由宿主注入，**未注入即占位零请求**；核心不依赖 Vue / DOM / 浏览器 API。
 */

import { BaseComponent } from '../base/BaseComponent'
import {
  AI_CHAT_PERM,
  AI_MANAGE_PERM,
  applyActionConfirm,
  applyActionExecute,
  applyActionFail,
  applyActionRevoke,
  canAutoExecute as canAutoExecuteNow,
  autoApproveAvailable as autoApproveAvailableNow,
  canRevokeAction,
  deriveAiKey,
  deriveSessionTitle,
  failMessage,
  finishMessage,
  normalizeAiMessage,
  normalizeAiMessages,
  normalizeAiMode,
  normalizeAiSessions,
  normalizeAiSessionsPage,
  normalizePendingAction,
  reduceStream,
  requiresConfirm,
  resolveAiErrorText,
  resolveRegenerateInput,
  sortSessions,
  startStreamMessage,
  stopMessage,
  validatePrompt,
  type AiMessage,
  type AiMode,
  type AiPendingAction,
  type AiSession,
} from '../domain/ai-chat'
import { BaseAccess } from './access'
import { BaseAsyncTask } from './async-task'
import { BaseDataState } from './data-state'
import { BaseNotice } from './notice'
import { BaseOptionSource } from './option-source'

/** 对话请求载荷（与后端 `POST /api/v1/ai/chat` 同源）。 */
export interface AiChatRequest {
  /** 模式。 */
  mode: AiMode
  /** 问题内容。 */
  content: string
  /** 会话标识。 */
  sessionId?: string
  /** 数据集标识（智能问数）。 */
  datasetId?: string
  /** 文件标识集合（文档问答）。 */
  fileIds?: string[]
}

/** 注入的处理函数集（未注入即占位不请求）。 */
export interface AiJobs {
  /** 会话列表取数。 */
  loadSessions?: (input: { mode?: AiMode | 'all'; keyword?: string }) => Promise<unknown>
  /** 会话消息取数。 */
  loadMessages?: (input: { sessionId: string }) => Promise<unknown>
  /** 非流式兜底对话。 */
  chat?: (input: AiChatRequest) => Promise<unknown>
  /** 停止在途流（通知后端）。 */
  stop?: (input: { sessionId?: string; messageId?: string }) => Promise<boolean | undefined>
  /** 重新生成。 */
  regenerate?: (input: { sessionId?: string; messageId: string }) => Promise<unknown>
  /** 确认并执行动作（返回审计与可撤销）。 */
  confirmAction?: (input: {
    actionId: string
    payload?: Record<string, unknown>
  }) => Promise<{ revocable?: boolean; auditId?: string } | undefined>
  /** 撤销动作。 */
  revokeAction?: (input: { actionId: string }) => Promise<boolean | undefined>
  /** 删除会话。 */
  removeSession?: (id: string) => Promise<boolean | undefined>
}

/** 流式完成载荷。 */
export interface AiStreamDonePayload {
  /** 审计记录标识。 */
  auditId?: string
  /** 结构化结果（图表 / 表格）。 */
  result?: unknown
  /** 引用来源。 */
  citations?: unknown
  /** 风险提示。 */
  risks?: unknown
}

/** 流式回调。 */
export interface AiStreamHandlers {
  /** 接收片段。 */
  onChunk(chunk: string): void
  /** 流式完成。 */
  onDone(payload?: AiStreamDonePayload): void
  /** 流式失败。 */
  onError(error: unknown): void
}

/** 流式适配器接口（宿主注入；核心不依赖浏览器 API）。 */
export interface AiStreamAdapter {
  /**
   * 发起一次流式对话。
   *
   * @param input 请求与回调。
   * @returns 可中止句柄。
   */
  start(input: { request: AiChatRequest; handlers: AiStreamHandlers }): { abort(): void }
}

/** 助手阶段。 */
export type AiAssistantPhase = 'idle' | 'loading' | 'streaming' | 'ready' | 'error'

/**
 * 解析异常上的错误码（`code` 字段）。
 *
 * @param error 异常。
 * @returns 错误码或 `undefined`。
 */
function errorCodeOf(error: unknown): number | undefined {
  if (error !== null && typeof error === 'object' && 'code' in error) {
    const code = (error as { code?: unknown }).code
    const numeric = typeof code === 'number' ? code : Number(code)
    if (Number.isInteger(numeric)) {
      return numeric
    }
  }
  return undefined
}

/**
 * 解析异步返回值为流式完成载荷（兼容对象 / 字符串）。
 *
 * @param value 原始返回。
 * @returns 完成载荷。
 */
function toDonePayload(value: unknown): AiStreamDonePayload | undefined {
  if (value === null || typeof value !== 'object') {
    return undefined
  }
  const raw = value as Record<string, unknown>
  return {
    auditId: raw.auditId ?? raw.audit_id,
    result: raw.result,
    citations: raw.citations,
    risks: raw.risks,
  } as AiStreamDonePayload
}

/** AI 助手编排能力基类（抽象）。 */
export abstract class BaseAiAssistant extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'ai-assistant'
  /** 依赖登记。 */
  override readonly depends = ['access', 'notice', 'data-state', 'option-source', 'async-task']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 占位态请求计数（占位态恒 0）。 */
  requestCount = 0
  /** 当前模式。 */
  mode: AiMode = 'ask'
  /** 会话列表。 */
  sessions: AiSession[] = []
  /** 当前会话标识。 */
  activeSessionId = ''
  /** 消息流。 */
  messages: AiMessage[] = []
  /** 是否流式输出中。 */
  streaming = false
  /** 流式消息标识。 */
  streamingMessageId = ''
  /** 自动执行开关。 */
  autoExecute = false
  /** 自动审批开关。 */
  autoApprove = false
  /** 待确认动作。 */
  pendingAction: AiPendingAction | undefined = undefined
  /** 编排阶段。 */
  phase: AiAssistantPhase = 'idle'
  /** 错误文案。 */
  errorMessage = ''
  /** 错误码。 */
  errorCode: number | undefined = undefined
  /** 注入的处理函数集。 */
  jobs: AiJobs = {}
  /** 流式适配器（未注入即占位）。 */
  stream: AiStreamAdapter | undefined = undefined
  /** 权限上下文。 */
  access: BaseAccess | undefined = undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined = undefined
  /** 数据状态能力。 */
  dataState: BaseDataState | undefined = undefined
  /** 选项源能力（数据集 / 文件）。 */
  optionSource: BaseOptionSource | undefined = undefined
  /** 异步任务能力。 */
  asyncTask: BaseAsyncTask | undefined = undefined
  /** 在途流句柄。 */
  #streamHandle: { abort(): void } | undefined = undefined
  /** 是否取数中（防重复）。 */
  #busy = false

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否进行中（会话 / 消息取数）。 */
  get busy(): boolean {
    return this.#busy || this.phase === 'loading'
  }

  /** 是否持对话权限（未注入权限上下文视为有权）。 */
  get canChat(): boolean {
    return this.access === undefined || this.access.has(AI_CHAT_PERM)
  }

  /** 是否持审计 / 模型管理权限（未注入视为无权）。 */
  get canManage(): boolean {
    return this.access?.has(AI_MANAGE_PERM) ?? false
  }

  /** 当前会话。 */
  get activeSession(): AiSession | undefined {
    return this.sessions.find((session) => session.id === this.activeSessionId)
  }

  /** 是否可发送（就绪 ∧ 有权 ∧ 非流式中）。 */
  get canSend(): boolean {
    return this.ready && this.canChat && !this.streaming
  }

  /** 是否可停止（流式中）。 */
  get canStopStreaming(): boolean {
    return this.streaming
  }

  /** 自动执行是否可用。 */
  get canAutoExecute(): boolean {
    return canAutoExecuteNow(this.autoExecute, this.canChat)
  }

  /** 自动审批是否可用（依赖自动执行）。 */
  get autoApproveAvailable(): boolean {
    return autoApproveAvailableNow(this.autoExecute, this.autoApprove)
  }

  /**
   * 切换就绪态。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    if (this.ready === value) {
      return
    }
    this.ready = value
    if (!value) {
      this.#abortStream()
      this.streaming = false
      this.streamingMessageId = ''
    }
    this.notifyLifecycle('update')
  }

  /**
   * 注入处理函数集。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: AiJobs): void {
    this.jobs = { ...jobs }
    this.notifyLifecycle('update')
  }

  /**
   * 注入 / 移除流式适配器。
   *
   * @param adapter 适配器；`undefined` 表示移除。
   */
  setStream(adapter: AiStreamAdapter | undefined): void {
    this.stream = adapter
    this.notifyLifecycle('update')
  }

  /**
   * 注入权限上下文。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.notifyLifecycle('update')
  }

  /**
   * 注入提示通知。
   *
   * @param notice 提示通知。
   */
  setNotice(notice: BaseNotice | undefined): void {
    this.notice = notice
    this.notifyLifecycle('update')
  }

  /**
   * 注入数据状态能力。
   *
   * @param state 数据状态能力。
   */
  setDataState(state: BaseDataState | undefined): void {
    this.dataState = state
    this.notifyLifecycle('update')
  }

  /**
   * 注入选项源能力。
   *
   * @param source 选项源能力。
   */
  setOptionSource(source: BaseOptionSource | undefined): void {
    this.optionSource = source
    this.notifyLifecycle('update')
  }

  /**
   * 注入异步任务能力。
   *
   * @param task 异步任务能力。
   */
  setAsyncTask(task: BaseAsyncTask | undefined): void {
    this.asyncTask = task
    this.notifyLifecycle('update')
  }

  /**
   * 设置模式（流式中忽略）。
   *
   * @param mode 模式。
   * @returns 是否生效。
   */
  setMode(mode: unknown): boolean {
    if (this.streaming) {
      return false
    }
    const next = normalizeAiMode(mode)
    if (next === this.mode) {
      return true
    }
    this.mode = next
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置会话列表（当前会话失效时回落首个）。
   *
   * @param sessions 会话数组。
   */
  setSessions(sessions: unknown): void {
    this.sessions = sortSessions(normalizeAiSessions(sessions))
    if (this.activeSessionId === '' || !this.sessions.some((session) => session.id === this.activeSessionId)) {
      this.activeSessionId = this.sessions[0]?.id ?? ''
    }
    this.notifyLifecycle('update')
  }

  /**
   * 设置消息流。
   *
   * @param messages 消息数组。
   */
  setMessages(messages: unknown): void {
    this.messages = normalizeAiMessages(messages)
    this.notifyLifecycle('update')
  }

  /**
   * 切换当前会话（清空消息，等待使用方装载）。
   *
   * @param id 会话标识。
   * @returns 是否切换成功。
   */
  selectSession(id: string): boolean {
    if (!this.sessions.some((session) => session.id === id)) {
      return false
    }
    this.#abortStream()
    this.streaming = false
    this.streamingMessageId = ''
    this.activeSessionId = id
    this.messages = []
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 新建会话（置于最前并选中）。
   *
   * @param mode 模式（缺省当前模式）。
   * @returns 新会话。
   */
  newSession(mode?: AiMode): AiSession {
    const session: AiSession = {
      id: '',
      title: '新会话',
      mode: normalizeAiMode(mode ?? this.mode),
      updatedAt: new Date().toISOString(),
    }
    let index = this.sessions.length + 1
    const used = new Set(this.sessions.map((item) => item.id))
    while (used.has(`s-${index}`)) {
      index += 1
    }
    session.id = `s-${index}`
    this.sessions = [session, ...this.sessions]
    this.activeSessionId = session.id
    this.messages = []
    this.notifyLifecycle('update')
    return session
  }

  /**
   * 删除会话（本地即时 + 注入时提交 + 失败回滚）。
   *
   * @param id 会话标识。
   * @returns 是否成功。
   */
  async removeSession(id: string): Promise<boolean> {
    const index = this.sessions.findIndex((session) => session.id === id)
    if (index < 0) {
      return false
    }
    const before = [...this.sessions]
    const beforeActive = this.activeSessionId
    this.sessions = this.sessions.filter((session) => session.id !== id)
    if (this.activeSessionId === id) {
      this.activeSessionId = this.sessions[0]?.id ?? ''
      this.messages = []
    }
    this.notifyLifecycle('update')
    if (!this.ready || this.jobs.removeSession === undefined) {
      return true
    }
    this.requestCount += 1
    try {
      const ok = await this.jobs.removeSession(id)
      if (ok === false) {
        this.sessions = before
        this.activeSessionId = beforeActive
        this.notifyLifecycle('update')
        return false
      }
      return true
    } catch (error) {
      this.sessions = before
      this.activeSessionId = beforeActive
      this.reportError(error, { scope: 'BaseAiAssistant.removeSession' })
      this.notifyLifecycle('update')
      return false
    }
  }

  /**
   * 追加本地消息（外部驱动的种子 / 乐观追加，不发请求）。
   *
   * @param message 消息。
   * @returns 归一消息或 `undefined`（脏项）。
   */
  appendLocalMessage(message: unknown): AiMessage | undefined {
    const normalized = normalizeAiMessage(message)
    if (normalized === undefined) {
      return undefined
    }
    this.messages = [...this.messages, normalized]
    this.notifyLifecycle('update')
    return normalized
  }

  /**
   * 设置自动执行开关。
   *
   * @param value 开关。
   */
  setAutoExecute(value: boolean): void {
    this.autoExecute = value
    this.notifyLifecycle('update')
  }

  /**
   * 设置自动审批开关。
   *
   * @param value 开关。
   */
  setAutoApprove(value: boolean): void {
    this.autoApprove = value
    this.notifyLifecycle('update')
  }

  /**
   * 设置待确认动作（本地驱动，不发请求）。
   *
   * @param action 待确认动作。
   */
  setPendingAction(action: unknown): void {
    this.pendingAction = normalizePendingAction(action)
    this.notifyLifecycle('update')
  }

  /**
   * 会话取数（占位 / 未注入处理函数时零请求）。
   *
   * @param input 筛选条件。
   * @returns 会话数组或 `undefined`。
   */
  async loadSessions(input: { mode?: AiMode | 'all'; keyword?: string } = {}): Promise<AiSession[] | undefined> {
    if (this.degraded || this.jobs.loadSessions === undefined) {
      return undefined
    }
    this.#busy = true
    this.requestCount += 1
    this.phase = 'loading'
    const token = this.dataState?.begin()
    this.notifyLifecycle('update')
    try {
      const page = normalizeAiSessionsPage(await this.jobs.loadSessions(input))
      this.sessions = sortSessions(page.items)
      if (this.activeSessionId === '' || !this.sessions.some((session) => session.id === this.activeSessionId)) {
        this.activeSessionId = this.sessions[0]?.id ?? ''
      }
      this.errorMessage = ''
      this.errorCode = undefined
      this.phase = 'ready'
      if (token !== undefined) {
        this.dataState?.settle(token, this.sessions.length > 0 ? 'ready' : 'empty')
      }
      this.notifyLifecycle('update')
      return this.sessions.map((session) => ({ ...session }))
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.errorCode = errorCodeOf(error)
      this.phase = 'error'
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.reportError(error, { scope: 'BaseAiAssistant.loadSessions' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 会话消息取数（占位 / 未注入处理函数时零请求）。
   *
   * @param sessionId 会话标识（缺省当前会话）。
   * @returns 消息数组或 `undefined`。
   */
  async loadMessages(sessionId?: string): Promise<AiMessage[] | undefined> {
    const target = sessionId ?? this.activeSessionId
    if (this.degraded || this.jobs.loadMessages === undefined || target === '') {
      return undefined
    }
    this.#busy = true
    this.requestCount += 1
    this.phase = 'loading'
    const token = this.dataState?.begin()
    this.notifyLifecycle('update')
    try {
      this.messages = normalizeAiMessages(await this.jobs.loadMessages({ sessionId: target }))
      this.errorMessage = ''
      this.errorCode = undefined
      this.phase = 'ready'
      if (token !== undefined) {
        this.dataState?.settle(token, this.messages.length > 0 ? 'ready' : 'empty')
      }
      this.notifyLifecycle('update')
      return this.messages.map((message) => ({ ...message }))
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.errorCode = errorCodeOf(error)
      this.phase = 'error'
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.reportError(error, { scope: 'BaseAiAssistant.loadMessages' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 发送消息（追加用户与助手消息并驱动流 / 非流式兜底）。
   *
   * @param input 发送入参。
   * @returns 助手占位消息或 `undefined`（不可发送）。
   */
  async send(input: { content: string; datasetId?: string; fileIds?: string[] }): Promise<AiMessage | undefined> {
    if (!this.canSend || !validatePrompt(input.content).valid) {
      return undefined
    }
    const session = this.#ensureSession(input.content)
    const userMessage: AiMessage = {
      id: this.#nextMessageId(),
      role: 'user',
      status: 'done',
      content: input.content,
      createdAt: new Date().toISOString(),
    }
    this.messages = [...this.messages, userMessage]
    const assistant = this.#pushAssistantPlaceholder()
    const request: AiChatRequest = {
      mode: this.mode,
      content: input.content,
      sessionId: session.id,
    }
    if (input.datasetId !== undefined && input.datasetId !== '') {
      request.datasetId = input.datasetId
    }
    if (input.fileIds !== undefined && input.fileIds.length > 0) {
      request.fileIds = [...input.fileIds]
    }
    return this.#dispatch(request, assistant)
  }

  /**
   * 追加流式片段（由适配器回调驱动）。
   *
   * @param delta 片段。
   */
  appendChunk(delta: string): void {
    const id = this.streamingMessageId
    if (!this.streaming || id === '') {
      return
    }
    this.#patchMessage(id, (message) => reduceStream(message, { type: 'chunk', delta }))
  }

  /**
   * 停止流式输出（中断在途流，保留已接收内容）。
   *
   * @returns 是否生效。
   */
  async stop(): Promise<boolean> {
    if (!this.streaming) {
      return false
    }
    const id = this.streamingMessageId
    this.#abortStream()
    this.#patchMessage(id, (message) => stopMessage(message))
    this.streaming = false
    this.streamingMessageId = ''
    this.phase = 'ready'
    this.notifyLifecycle('update')
    if (this.ready && this.jobs.stop !== undefined) {
      this.requestCount += 1
      try {
        await this.jobs.stop({ sessionId: this.activeSessionId, messageId: id })
      } catch (error) {
        this.reportError(error, { scope: 'BaseAiAssistant.stop' })
      }
    }
    return true
  }

  /**
   * 重新生成（复用原问题，不重复追加用户消息）。
   *
   * @param messageId 目标助手消息标识（缺省最近失败 / 已停止消息）。
   * @returns 新助手占位消息或 `undefined`。
   */
  async regenerate(messageId?: string): Promise<AiMessage | undefined> {
    const target =
      messageId ?? [...this.messages].reverse().find((message) => message.status === 'error' || message.status === 'stopped')?.id
    if (target === undefined) {
      return undefined
    }
    const input = resolveRegenerateInput(this.messages, target, this.mode)
    if (input === undefined) {
      return undefined
    }
    this.messages = this.messages.filter((message) => message.id !== target)
    const assistant = this.#pushAssistantPlaceholder()
    const request: AiChatRequest = {
      mode: input.mode,
      content: input.content,
      ...(this.activeSessionId !== '' ? { sessionId: this.activeSessionId } : {}),
    }
    return this.#dispatch(request, assistant)
  }

  /** 对最近失败 / 已停止消息重生成。 */
  async retry(): Promise<AiMessage | undefined> {
    return this.regenerate()
  }

  /**
   * 确认并执行动作（强制二次确认）。
   *
   * @param actionId 动作标识（缺省当前待确认动作）。
   * @returns 是否成功。
   */
  async confirmAction(actionId?: string): Promise<boolean> {
    const action = this.pendingAction
    if (action === undefined || (actionId !== undefined && action.id !== actionId)) {
      return false
    }
    if (!this.canAutoExecute) {
      this.#failWith(10208)
      return false
    }
    if (!action.confirmable) {
      this.#failWith(10210)
      return false
    }
    if (!requiresConfirm(action)) {
      this.#failWith(10211)
      return false
    }
    this.pendingAction = applyActionConfirm(action)
    this.notifyLifecycle('update')
    if (!this.ready || this.jobs.confirmAction === undefined) {
      return true
    }
    this.requestCount += 1
    try {
      const result = await this.jobs.confirmAction({
        actionId: action.id,
        payload: { idempotencyKey: deriveAiKey({ actionId: action.id }) },
      })
      this.pendingAction = applyActionExecute(this.pendingAction, {
        auditId: result?.auditId,
        revocable: result?.revocable,
      })
      this.notifyLifecycle('update')
      return true
    } catch (error) {
      this.pendingAction = applyActionFail(this.pendingAction)
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.errorCode = errorCodeOf(error)
      this.reportError(error, { scope: 'BaseAiAssistant.confirmAction' })
      this.notifyLifecycle('update')
      return false
    }
  }

  /**
   * 撤销动作（可撤销时；本地乐观 + 失败回滚）。
   *
   * @param actionId 动作标识（缺省当前待确认动作）。
   * @returns 是否成功。
   */
  async revokeAction(actionId?: string): Promise<boolean> {
    const action = this.pendingAction
    if (action === undefined || (actionId !== undefined && action.id !== actionId)) {
      return false
    }
    if (!canRevokeAction(action)) {
      this.#failWith(10212)
      return false
    }
    const before = action
    this.pendingAction = applyActionRevoke(action)
    this.notifyLifecycle('update')
    if (!this.ready || this.jobs.revokeAction === undefined) {
      return true
    }
    this.requestCount += 1
    try {
      const ok = await this.jobs.revokeAction({ actionId: action.id })
      if (ok === false) {
        this.pendingAction = before
        this.notifyLifecycle('update')
        return false
      }
      return true
    } catch (error) {
      this.pendingAction = before
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.errorCode = errorCodeOf(error)
      this.reportError(error, { scope: 'BaseAiAssistant.revokeAction' })
      this.notifyLifecycle('update')
      return false
    }
  }

  /** 加载数据集选项（经选项源能力，未注入加载器即零请求）。 */
  async refreshDatasets(): Promise<void> {
    if (this.optionSource === undefined) {
      return
    }
    await this.optionSource.load()
    this.notifyLifecycle('update')
  }

  /** 释放：中止在途流。 */
  protected override onDispose(): void {
    this.#abortStream()
    super.onDispose()
  }

  /**
   * 确保存在当前会话（无则按问题内容新建）。
   *
   * @param content 问题内容。
   * @returns 当前会话。
   */
  #ensureSession(content: string): AiSession {
    const existing = this.activeSession
    if (existing !== undefined) {
      return existing
    }
    const session = this.newSession(this.mode)
    session.title = deriveSessionTitle(content)
    this.sessions = [session, ...this.sessions.filter((item) => item.id !== session.id)]
    return session
  }

  /**
   * 追加助手流式占位消息。
   *
   * @returns 新占位消息。
   */
  #pushAssistantPlaceholder(): AiMessage {
    const message = startStreamMessage({
      id: this.#nextMessageId(),
      role: 'assistant',
      createdAt: new Date().toISOString(),
    })
    this.messages = [...this.messages, message]
    this.streaming = true
    this.streamingMessageId = message.id
    this.phase = 'streaming'
    this.errorMessage = ''
    this.errorCode = undefined
    this.notifyLifecycle('update')
    return message
  }

  /**
   * 驱动一次对话（流式优先，其次非流式兜底，皆无则仅本地占位）。
   *
   * @param request 请求。
   * @param assistant 助手占位消息。
   * @returns 助手消息（流式返回占位；非流式返回填充后消息）。
   */
  async #dispatch(request: AiChatRequest, assistant: AiMessage): Promise<AiMessage | undefined> {
    if (this.stream !== undefined) {
      this.requestCount += 1
      this.#streamHandle = this.stream.start({
        request,
        handlers: {
          onChunk: (chunk) => this.appendChunk(chunk),
          onDone: (payload) => this.#finishStreaming(payload),
          onError: (error) => this.#failStreaming(error),
        },
      })
      return assistant
    }
    if (this.jobs.chat !== undefined) {
      this.requestCount += 1
      const token = this.dataState?.begin()
      try {
        const payload = toDonePayload(await this.jobs.chat(request))
        this.#finishStreaming(payload)
        if (token !== undefined) {
          this.dataState?.settle(token, 'ready')
        }
        return this.messages.find((message) => message.id === assistant.id)
      } catch (error) {
        this.#failStreaming(error)
        if (token !== undefined) {
          this.dataState?.settle(token, 'error')
        }
        return undefined
      }
    }
    return assistant
  }

  /**
   * 完成流式（合并结果 / 引用 / 风险 / 审计）。
   *
   * @param payload 完成载荷。
   */
  #finishStreaming(payload?: AiStreamDonePayload): void {
    const id = this.streamingMessageId
    if (id === '') {
      return
    }
    this.#patchMessage(id, (message) =>
      finishMessage(message, {
        content: message.content,
        result: payload?.result as AiMessage['result'],
        citations: payload?.citations as AiMessage['citations'],
        risks: payload?.risks as AiMessage['risks'],
        auditId: payload?.auditId as string | undefined,
      }),
    )
    this.streaming = false
    this.streamingMessageId = ''
    this.#streamHandle = undefined
    this.phase = 'ready'
    this.notifyLifecycle('update')
  }

  /**
   * 流式失败（置错误态 + 错误码提示）。
   *
   * @param error 异常。
   */
  #failStreaming(error: unknown): void {
    const id = this.streamingMessageId
    const message = error instanceof Error ? error.message : String(error)
    if (id !== '') {
      this.#patchMessage(id, (item) => failMessage(item, message))
    }
    this.streaming = false
    this.streamingMessageId = ''
    this.#streamHandle = undefined
    this.errorMessage = message
    this.errorCode = errorCodeOf(error)
    this.phase = 'error'
    this.notice?.enqueue(this.errorCode !== undefined ? resolveAiErrorText(this.errorCode) : message, 'error')
    this.reportError(error, { scope: 'BaseAiAssistant.stream' })
    this.notifyLifecycle('update')
  }

  /**
   * 替换指定消息（不可变映射）。
   *
   * @param id 消息标识。
   * @param mapper 映射函数。
   */
  #patchMessage(id: string, mapper: (message: AiMessage) => AiMessage): void {
    this.messages = this.messages.map((message) => (message.id === id ? mapper(message) : message))
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /** 中止在途流句柄（幂等）。 */
  #abortStream(): void {
    try {
      this.#streamHandle?.abort()
    } catch (error) {
      this.reportError(error, { scope: 'BaseAiAssistant.abort' })
    }
    this.#streamHandle = undefined
  }

  /**
   * 记录错误码并提示。
   *
   * @param code 错误码。
   */
  #failWith(code: number): void {
    this.errorCode = code
    this.errorMessage = resolveAiErrorText(code)
    this.notice?.enqueue(this.errorMessage, 'warning')
    this.notifyLifecycle('update')
  }

  /** 派生下一个消息标识。 */
  #nextMessageId(): string {
    let index = this.messages.length + 1
    const used = new Set(this.messages.map((message) => message.id))
    while (used.has(`m-${index}`)) {
      index += 1
    }
    return `m-${index}`
  }
}
