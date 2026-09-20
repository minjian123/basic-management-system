/**
 * 审批流编排能力基类：实例与记录**并行取数**（单失败不整体报错）、会签聚合与进度摘要、
 * 审批提交（内容派生幂等键 / 防重复提交 / 提交后刷新）、错误码处置（60005 按成功、60009 置只读）、
 * 只读图形态（XML / 图片 / 三级降级）。
 *
 * **数据通路由宿主注入**（取实例、取记录、取只读图图片、提交）——未注入即占位：不发请求、返回 `undefined`、
 * 写占位文案；只读图图片通路经组合的 `BasePresignedUrl` 承载。核心不触 DOM、不发请求；工作流引擎执行归后端。
 */

import { BasePlaceholderState } from './placeholder-state'
import {
  APPROVAL_ACTION_LABELS,
  APPROVAL_COMMENT_MAX,
  APPROVAL_DUPLICATE_TEXT,
  APPROVAL_PLACEHOLDER_TEXT,
  deriveApprovalKey,
  normalizeInstance,
  normalizeRecords,
  normalizeTask,
  resolveApprovalActions,
  resolveApprovalErrorCode,
  resolveDiagramMode,
  resolveErrorHandling,
  resolveProgressSummary,
  resolveReadonlyInstance,
  validateAction,
  type ApprovalAction,
  type ApprovalCheckResult,
  type ApprovalDiagramMode,
  type ApprovalErrorHandlingItem,
  type ApprovalInstance,
  type ApprovalInstanceInput,
  type ApprovalPhase,
  type ApprovalPartState,
  type ApprovalProgressSummary,
  type ApprovalRecord,
  type ApprovalRecordInput,
  type ApprovalSubmitPayload,
  type ApprovalSubmitResult,
  type ApprovalTask,
  type ApprovalTaskInput,
} from '../domain/approval'
import type { BaseAccess } from './access'
import type { BaseNotice } from './notice'
import type { BasePresignedUrl, PresignedResult } from './presigned-url'

/** 取实例详情处理函数（宿主注入；未注入即占位）。 */
export type ApprovalLoadInstanceHandler = (input: {
  /** 实例标识。 */
  instanceId: string
}) => Promise<ApprovalInstanceInput | undefined>

/** 取审批记录处理函数（宿主注入；未注入即占位）。 */
export type ApprovalLoadRecordsHandler = (input: {
  /** 实例标识。 */
  instanceId: string
}) => Promise<readonly ApprovalRecordInput[] | undefined>

/** 取只读图图片地址处理函数（宿主注入；未注入即降级）。 */
export type ApprovalLoadDiagramHandler = () => Promise<PresignedResult | undefined>

/** 提交处理函数（单入口，宿主按动作路由端点；未注入即占位）。 */
export type ApprovalSubmitHandler = (payload: ApprovalSubmitPayload) => Promise<ApprovalSubmitResult | undefined>

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface ApprovalJobs {
  /** 取实例详情。 */
  loadInstance?: ApprovalLoadInstanceHandler
  /** 取审批记录。 */
  loadRecords?: ApprovalLoadRecordsHandler
  /** 取只读图图片地址（预签名通路）。 */
  loadDiagramUrl?: ApprovalLoadDiagramHandler
  /** 审批提交（单入口，载荷含动作）。 */
  submit?: ApprovalSubmitHandler
}

/** 审批提交 / 校验入参。 */
export interface ApprovalSubmitInput {
  /** 意见。 */
  comment?: string
  /** 目标（驳回退回节点 / 转办对象）。 */
  target?: string
}

/** 审批流编排能力基类（抽象）。 */
export abstract class BaseApprovalFlow extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'approval-flow'
  /** 依赖能力键。 */
  override readonly depends = ['placeholder-state', 'presigned-url', 'access', 'notice']
  /** 实例标识。 */
  instanceId = ''
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false

  /**
   * 切换就绪态（占位态强制禁用）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    this.ready = value
    this.disabled = !value
    this.touch()
  }
  /** 占位态强制禁用（随就绪态联动）。 */
  override disabled = true
  /** 编排阶段。 */
  phase: ApprovalPhase = 'idle'
  /** 流程实例。 */
  instance: ApprovalInstance | undefined
  /** 审批记录。 */
  records: ApprovalRecord[] = []
  /** 当前待办任务。 */
  currentTask: ApprovalTask | undefined
  /** 实例取数分部状态。 */
  instanceState: ApprovalPartState = 'idle'
  /** 记录取数分部状态。 */
  recordsState: ApprovalPartState = 'idle'
  /** 失败文案。 */
  errorMessage = ''
  /** 失败处置（按错误码解析）。 */
  errorHandling: ApprovalErrorHandlingItem | undefined
  /** 最近一次提交结果。 */
  lastResult: ApprovalSubmitResult | undefined
  /** 刷新未成功标记（处理函数未注入或刷新失败时为真）。 */
  pendingRefresh = false
  /** 只读图是否已判定失败（依赖加载 / XML 解析失败）。 */
  diagramFailed = false
  /** 只读图 BPMN 定义快照。 */
  diagramXml = ''
  /** 只读图图片地址（预签名通路）。 */
  diagramUrl = ''
  /** 宿主下发：可撤回（发起人且实例未结束，判定归后端）。 */
  withdrawable = false
  /** 宿主下发：可审批（缺省按「持有待办」判定；下发 `false` 可显式否定，如当前人非审批人）。 */
  approvable = true
  /** 权限上下文（未注入不校验）。 */
  access: BaseAccess | undefined
  /** 提示通知（未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 预签名能力（组合；只读图图片通路）。 */
  presigned: BasePresignedUrl | undefined
  /** 宿主注入的处理函数集。 */
  jobs: ApprovalJobs = {}
  /** 取数进行中标记（防并发取数）。 */
  #loading = false
  /** 提交进行中标记（防重复提交）。 */
  #submitting = false
  /** 引擎异常置只读标记（60009）。 */
  #abnormal = false
  /** 重试入参（失败提交的最近一次动作与入参）。 */
  #retryAction: { action: ApprovalAction; comment?: string; target?: string } | undefined


  /** 是否进行中（取数 / 提交）。 */
  get busy(): boolean {
    return this.#loading || this.#submitting
  }

  /** 审批意见长度上限（Unicode 码点）。 */
  get commentMax(): number {
    return APPROVAL_COMMENT_MAX
  }

  /** 是否可审批（实例进行中 ∧ 有待办 ∧ 有权）。 */
  get canApprove(): boolean {
    return this.ready && !this.readonly && this.approvable && this.#allowed()
  }

  /** 是否可撤回（实例进行中 ∧ 宿主判定为发起人）。 */
  get canWithdraw(): boolean {
    return this.ready && !this.readonly && this.withdrawable
  }

  /** 是否只读（实例已结束 / 已驳回 / 异常，或引擎异常错误码命中）。 */
  get readonly(): boolean {
    return this.#abnormal || resolveReadonlyInstance(this.instance?.status)
  }

  /** 可用动作矩阵。 */
  get actions(): ReturnType<typeof resolveApprovalActions> {
    return resolveApprovalActions({
      status: this.#abnormal ? 'abnormal' : this.instance?.status,
      canApprove: this.canApprove,
      canWithdraw: this.canWithdraw,
      hasTask: this.currentTask !== undefined,
      taskId: this.currentTask?.taskId,
    })
  }

  /** 进度摘要。 */
  get progress(): ApprovalProgressSummary {
    if (this.instance === undefined) {
      return { done: 0, total: 0, activeName: '' }
    }
    return resolveProgressSummary(this.instance)
  }

  /** 只读图形态（三级判定）。 */
  get diagramMode(): ApprovalDiagramMode {
    return resolveDiagramMode({ bpmnXml: this.diagramXml, url: this.diagramUrl, failed: this.diagramFailed })
  }

  /** 取数处理是否已注入。 */
  get loadReady(): boolean {
    return this.jobs.loadInstance !== undefined || this.jobs.loadRecords !== undefined
  }

  /** 提交处理是否已注入。 */
  get submitReady(): boolean {
    return this.jobs.submit !== undefined
  }


  /**
   * 切换实例标识（清空装载结果，须重新取数）。
   *
   * @param instanceId 实例标识。
   */
  setInstanceId(instanceId: string): void {
    if (this.instanceId === instanceId) {
      return
    }
    this.instanceId = instanceId
    this.instance = undefined
    this.records = []
    this.currentTask = undefined
    this.instanceState = 'idle'
    this.recordsState = 'idle'
    this.errorMessage = ''
    this.errorHandling = undefined
    this.diagramFailed = false
    this.diagramXml = ''
    this.diagramUrl = ''
    this.phase = 'idle'
    this.touch()
  }

  /**
   * 注入处理函数集（未注入的项按占位）。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: ApprovalJobs): void {
    this.jobs = jobs
    this.touch()
  }

  /**
   * 注入权限上下文（未注入视为有权，后端兜底）。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.touch()
  }

  /**
   * 注入预签名能力（只读图图片通路）。
   *
   * @param presigned 预签名能力实例。
   */
  setPresigned(presigned: BasePresignedUrl | undefined): void {
    this.presigned = presigned
    this.touch()
  }

  /**
   * 注入提示通知（未注入不发通知）。
   *
   * @param notice 提示通知。
   */
  setNotice(notice: BaseNotice | undefined): void {
    this.notice = notice
    this.touch()
  }

  /**
   * 装载实例详情（下发即已装载；空节点集置空态）。
   *
   * @param input 实例装载输入。
   */
  applyInstance(input: ApprovalInstanceInput): void {
    const instance = normalizeInstance(input)
    if (instance.id !== '') {
      this.instanceId = instance.id
    }
    this.instance = instance
    this.instanceState = instance.nodes.length === 0 ? 'empty' : 'ready'
    this.diagramXml = instance.bpmnXml
    this.diagramFailed = false
    this.touch()
  }

  /**
   * 装载审批记录（空集置空态）。
   *
   * @param input 记录装载输入。
   */
  applyRecords(input: readonly ApprovalRecordInput[]): void {
    this.records = normalizeRecords(input)
    this.recordsState = this.records.length === 0 ? 'empty' : 'ready'
    this.touch()
  }

  /**
   * 装载当前待办任务。
   *
   * @param input 待办装载输入。
   */
  applyTask(input?: ApprovalTaskInput): void {
    this.currentTask = normalizeTask(input)
    this.touch()
  }

  /**
   * 并行取数（实例与记录各自结算；单失败不整体报错）。
   *
   * @returns 是否全部成功。
   */
  async load(): Promise<boolean> {
    if (!this.ready || this.#loading || !this.loadReady) {
      return false
    }
    const instanceHandler = this.jobs.loadInstance
    const recordsHandler = this.jobs.loadRecords
    this.#loading = true
    this.phase = 'loading'
    this.errorMessage = ''
    this.errorHandling = undefined
    if (instanceHandler !== undefined) {
      this.instanceState = 'loading'
    }
    if (recordsHandler !== undefined) {
      this.recordsState = 'loading'
    }
    this.touch()

    const tasks: Promise<void>[] = []
    if (instanceHandler !== undefined) {
      this.requestCount += 1
      tasks.push(
        instanceHandler({ instanceId: this.instanceId })
          .then((input) => {
            if (this.isDisposed) {
              return
            }
            if (input === undefined) {
              this.instanceState = 'empty'
              return
            }
            this.applyInstance(input)
          })
          .catch((error: unknown) => {
            this.failPart('instance', error)
          }),
      )
    }
    if (recordsHandler !== undefined) {
      this.requestCount += 1
      tasks.push(
        recordsHandler({ instanceId: this.instanceId })
          .then((input) => {
            if (this.isDisposed) {
              return
            }
            if (input === undefined) {
              this.recordsState = 'empty'
              return
            }
            this.applyRecords(input)
          })
          .catch((error: unknown) => {
            this.failPart('records', error)
          }),
      )
    }

    await Promise.all(tasks)
    if (this.isDisposed) {
      return false
    }
    this.#loading = false
    const instanceFailed = this.instanceState === 'error'
    const recordsFailed = this.recordsState === 'error'
    this.pendingRefresh = instanceFailed || recordsFailed
    this.phase = instanceFailed && recordsFailed ? 'failed' : 'done'
    this.touch()
    return !instanceFailed && !recordsFailed
  }

  /**
   * 重取实例与审批记录（提交后刷新 / 失败重试）。
   *
   * @returns 是否全部成功。
   */
  async reload(): Promise<boolean> {
    return this.load()
  }

  /**
   * 只读图图片通路取址（经组合的预签名能力；未注入即降级）。
   *
   * @returns 可用地址；未注入或失败时返回已有值 / `undefined`。
   */
  async loadDiagramImage(): Promise<string | undefined> {
    if (!this.ready) {
      return undefined
    }
    const url = await this.runDiagramFetch()
    if (this.isDisposed) {
      return undefined
    }
    this.diagramUrl = url ?? ''
    this.diagramFailed = false
    this.touch()
    return url
  }

  /** 标记只读图失败（件层依赖加载 / XML 解析失败时调用）。 */
  markDiagramFailed(): void {
    this.diagramFailed = true
    this.touch()
  }

  /**
   * 派生幂等键（内容派生：同内容同键、内容变更换键）。
   *
   * @param action 动作。
   * @param comment 意见。
   * @param target 目标（驳回退回节点 / 转办对象）。
   * @returns 幂等键。
   */
  idempotencyKey(action: ApprovalAction, comment?: string, target?: string): string {
    return deriveApprovalKey(this.currentTask?.taskId, action, comment, target)
  }

  /**
   * 校验动作前置条件（意见必填 / 目标必填 / 动作可用）。
   *
   * @param action 动作。
   * @param input 入参（意见、目标）。
   * @returns 校验结果。
   */
  validate(action: ApprovalAction, input: ApprovalSubmitInput = {}): ApprovalCheckResult {
    return validateAction(action, {
      comment: input.comment,
      target: input.target,
      canApprove: this.canApprove,
      canWithdraw: this.canWithdraw,
      hasTask: this.currentTask !== undefined,
    })
  }

  /**
   * 审批提交（携带内容派生幂等键；进行中重复提交不动作）。
   *
   * @param action 动作。
   * @param input 入参（意见、目标）。
   * @returns 提交结果；占位 / 只读 / 进行中 / 校验失败 / 失败时返回 `undefined`。
   */
  async submit(action: ApprovalAction, input: ApprovalSubmitInput = {}): Promise<ApprovalSubmitResult | undefined> {
    if (!this.ready) {
      return undefined
    }
    const handler = this.jobs.submit
    if (handler === undefined) {
      this.errorMessage = APPROVAL_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    const check = this.validate(action, input)
    if (!check.valid) {
      this.errorMessage = check.message
      this.touch()
      return undefined
    }
    if (this.readonly || this.busy) {
      return undefined
    }
    const payload: ApprovalSubmitPayload = {
      action,
      taskId: this.currentTask?.taskId,
      comment: input.comment,
      target: input.target,
      idempotencyKey: this.idempotencyKey(action, input.comment, input.target),
    }
    this.#retryAction = { action, comment: input.comment, target: input.target }
    this.#submitting = true
    this.phase = 'submitting'
    this.errorMessage = ''
    this.errorHandling = undefined
    this.requestCount += 1
    this.touch()
    try {
      const result = await handler(payload)
      if (this.isDisposed) {
        return undefined
      }
      const duplicated = result?.duplicate === true
      this.lastResult = result ?? {}
      this.phase = 'done'
      this.#retryAction = undefined
      this.notice?.enqueue(
        duplicated ? APPROVAL_DUPLICATE_TEXT : `审批已提交（${APPROVAL_ACTION_LABELS[action]}）`,
        duplicated ? 'info' : 'success',
      )
      await this.reload()
      return this.lastResult
    } catch (error) {
      return this.handleSubmitError(error)
    } finally {
      this.#submitting = false
      this.touch()
    }
  }

  /**
   * 重试上次失败提交（复用同一幂等键）。
   *
   * @returns 提交结果；非失败态时返回 `undefined`。
   */
  async retry(): Promise<ApprovalSubmitResult | undefined> {
    if (this.phase !== 'failed') {
      return undefined
    }
    const pending = this.#retryAction
    if (pending === undefined) {
      return undefined
    }
    this.phase = 'idle'
    return this.submit(pending.action, { comment: pending.comment, target: pending.target })
  }

  /** 重置编排状态（阶段回 `idle` 并清错误，保留装载结果）。 */
  reset(): void {
    this.phase = 'idle'
    this.errorMessage = ''
    this.errorHandling = undefined
    this.pendingRefresh = false
    this.#retryAction = undefined
    this.touch()
  }

  /** 是否具备审批写权限（未注入权限上下文视为有权）。 */
  #allowed(): boolean {
    if (this.access === undefined) {
      return true
    }
    return this.access.has('wf:approve')
  }

  /**
   * 处理提交异常（60005 按成功；60009 置只读；按需刷新）。
   *
   * @param error 错误对象。
   * @returns 提交结果；失败时返回 `undefined`。
   */
  private async handleSubmitError(error: unknown): Promise<ApprovalSubmitResult | undefined> {
    const handling = resolveErrorHandling(resolveApprovalErrorCode(error))
    if (handling?.handling === 'duplicated') {
      this.errorHandling = handling
      this.lastResult = { duplicate: true }
      this.phase = 'done'
      this.notice?.enqueue(APPROVAL_DUPLICATE_TEXT, 'info')
      await this.reload()
      return this.lastResult
    }
    if (this.isDisposed) {
      return undefined
    }
    this.errorHandling = handling
    this.phase = 'failed'
    this.errorMessage = error instanceof Error && error.message !== '' ? error.message : '审批提交失败'
    if (handling?.readOnly === true) {
      this.#abnormal = true
    }
    this.notice?.enqueue(this.errorMessage, 'error')
    if (handling?.refresh === true) {
      // 刷新会重写阶段与文案，故刷新后复原失败面（错误码处置结果优先于取数结论）。
      const message = this.errorMessage
      await this.reload()
      this.phase = 'failed'
      this.errorMessage = message
      this.errorHandling = handling
      this.touch()
    }
    return undefined
  }

  /**
   * 取只读图图片地址（注入处理函数优先；否则经预签名能力；皆无则降级）。
   *
   * @returns 地址；不可用时返回 `undefined`。
   */
  private async runDiagramFetch(): Promise<string | undefined> {
    const handler = this.jobs.loadDiagramUrl
    if (handler !== undefined) {
      const result = await handler()
      return result?.url
    }
    if (this.presigned !== undefined) {
      return this.presigned.get()
    }
    return undefined
  }

  /**
   * 记分部失败（单失败不整体报错）。
   *
   * @param part 分部（`instance` / `records`）。
   * @param error 错误对象。
   */
  private failPart(part: 'instance' | 'records', error: unknown): void {
    if (this.isDisposed) {
      return
    }
    if (part === 'instance') {
      this.instanceState = 'error'
    } else {
      this.recordsState = 'error'
    }
    if (this.errorMessage === '') {
      this.errorMessage = error instanceof Error && error.message !== '' ? error.message : '审批数据加载失败'
    }
    this.errorHandling = resolveErrorHandling(resolveApprovalErrorCode(error)) ?? this.errorHandling
    this.touch()
  }

  /** 广播生命周期更新。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
