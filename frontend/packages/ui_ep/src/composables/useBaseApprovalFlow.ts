/** 审批流编排投影：把核心能力基类 `BaseApprovalFlow` 投影为组合式（并行取数 / 会签与进度 / 提交与幂等 / 错误码处置 / 只读图形态）。 */

import {
  BaseApprovalFlow,
  resolveApprovalActions,
  resolveProgressSummary,
  type ApprovalCheckResult,
  type ApprovalDiagramMode,
  type ApprovalErrorHandlingItem,
  type ApprovalInstance,
  type ApprovalInstanceInput,
  type ApprovalJobs,
  type ApprovalPartState,
  type ApprovalPhase,
  type ApprovalProgressSummary,
  type ApprovalRecord,
  type ApprovalRecordInput,
  type ApprovalSubmitInput,
  type ApprovalSubmitResult,
  type ApprovalTask,
  type ApprovalTaskInput,
  type BaseAccess,
  type BaseNotice,
  type BasePresignedUrl,
} from '@bms/core'
import { computed, markRaw, onScopeDispose, ref, toRaw, type ComputedRef, type Ref } from 'vue'

/** 具体审批流编排件（可实例化）。 */
class ApprovalFlowState extends BaseApprovalFlow {}

/** 选项。 */
export interface UseBaseApprovalFlowOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 实例标识。 */
  instanceId?: string
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: ApprovalJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
  /** 只读图图片通路（预签名）。 */
  presigned?: BasePresignedUrl
}

/** `useBaseApprovalFlow` 返回面。 */
export interface UseBaseApprovalFlowResult {
  /** 编排基类实例。 */
  approval: BaseApprovalFlow
  /** 数据通路是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（响应式）。 */
  degraded: Ref<boolean>
  /** 是否禁用（响应式）。 */
  disabled: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 编排阶段（响应式）。 */
  phase: Ref<ApprovalPhase>
  /** 流程实例（响应式）。 */
  instance: Ref<ApprovalInstance | undefined>
  /** 审批记录（响应式）。 */
  records: Ref<ApprovalRecord[]>
  /** 当前待办任务（响应式）。 */
  currentTask: Ref<ApprovalTask | undefined>
  /** 实例取数分部状态（响应式）。 */
  instanceState: Ref<ApprovalPartState>
  /** 记录取数分部状态（响应式）。 */
  recordsState: Ref<ApprovalPartState>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 失败处置（响应式）。 */
  errorHandling: Ref<ApprovalErrorHandlingItem | undefined>
  /** 刷新未成功标记（响应式）。 */
  pendingRefresh: Ref<boolean>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 只读图形态（响应式）。 */
  diagramMode: Ref<ApprovalDiagramMode>
  /** 只读图 BPMN 快照（响应式）。 */
  diagramXml: Ref<string>
  /** 只读图图片地址（响应式）。 */
  diagramUrl: Ref<string>
  /** 是否只读（响应式）。 */
  readonly: Ref<boolean>
  /** 进度摘要（响应式）。 */
  progress: ComputedRef<ApprovalProgressSummary>
  /** 可用动作矩阵（响应式）。 */
  actions: ComputedRef<ReturnType<typeof resolveApprovalActions>>
  /** 是否可审批（响应式）。 */
  canApprove: Ref<boolean>
  /** 是否可撤回（响应式）。 */
  canWithdraw: Ref<boolean>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 切换实例标识。 */
  setInstanceId: (instanceId: string) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: ApprovalJobs) => void
  /** 注入权限上下文。 */
  setAccess: (access?: BaseAccess) => void
  /** 注入预签名能力。 */
  setPresigned: (presigned?: BasePresignedUrl) => void
  /** 注入提示通知。 */
  setNotice: (notice?: BaseNotice) => void
  /** 设置可审批（宿主下发）。 */
  setApprovable: (value: boolean) => void
  /** 设置可撤回（宿主下发）。 */
  setWithdrawable: (value: boolean) => void
  /** 装载实例。 */
  applyInstance: (input: ApprovalInstanceInput) => void
  /** 装载审批记录。 */
  applyRecords: (input: readonly ApprovalRecordInput[]) => void
  /** 装载当前待办。 */
  applyTask: (input?: ApprovalTaskInput) => void
  /** 并行取数。 */
  load: () => Promise<boolean>
  /** 重取实例与记录。 */
  reload: () => Promise<boolean>
  /** 只读图图片通路取址。 */
  loadDiagramImage: () => Promise<string | undefined>
  /** 标记只读图失败。 */
  markDiagramFailed: () => void
  /** 派生幂等键。 */
  idempotencyKey: (action: Parameters<BaseApprovalFlow['idempotencyKey']>[0], comment?: string, target?: string) => string
  /** 动作前置校验。 */
  validate: (action: Parameters<BaseApprovalFlow['validate']>[0], input?: ApprovalSubmitInput) => ApprovalCheckResult
  /** 审批提交。 */
  submit: (action: Parameters<BaseApprovalFlow['submit']>[0], input?: ApprovalSubmitInput) => Promise<ApprovalSubmitResult | undefined>
  /** 重试失败提交。 */
  retry: () => Promise<ApprovalSubmitResult | undefined>
  /** 重置编排状态。 */
  reset: () => void
}

/**
 * 使用审批流编排投影。
 *
 * @param options 选项。
 * @returns 编排基类实例与响应式面。
 */
export function useBaseApprovalFlow(options: UseBaseApprovalFlowOptions = {}): UseBaseApprovalFlowResult {
  const approval = new ApprovalFlowState()
  if (options.instanceId !== undefined) {
    approval.setInstanceId(options.instanceId)
  }
  if (options.jobs !== undefined) {
    approval.setJobs(options.jobs)
  }
  if (options.access !== undefined) {
    approval.setAccess(markRaw(toRaw(options.access)))
  }
  if (options.notice !== undefined) {
    approval.setNotice(markRaw(toRaw(options.notice)))
  }
  if (options.presigned !== undefined) {
    approval.setPresigned(markRaw(toRaw(options.presigned)))
  }
  approval.setReady(options.ready ?? false)

  const ready = ref(approval.ready)
  const degraded = ref(approval.degraded)
  const disabled = ref(approval.disabled)
  const busy = ref(approval.busy)
  const phase = ref<ApprovalPhase>(approval.phase)
  const instance = ref<ApprovalInstance | undefined>(approval.instance)
  const records = ref<ApprovalRecord[]>(approval.records)
  const currentTask = ref<ApprovalTask | undefined>(approval.currentTask)
  const instanceState = ref<ApprovalPartState>(approval.instanceState)
  const recordsState = ref<ApprovalPartState>(approval.recordsState)
  const errorMessage = ref(approval.errorMessage)
  const errorHandling = ref<ApprovalErrorHandlingItem | undefined>(approval.errorHandling)
  const pendingRefresh = ref(approval.pendingRefresh)
  const requestCount = ref(approval.requestCount)
  const diagramMode = ref<ApprovalDiagramMode>(approval.diagramMode)
  const diagramXml = ref(approval.diagramXml)
  const diagramUrl = ref(approval.diagramUrl)
  const readonlyState = ref(approval.readonly)
  const canApprove = ref(approval.canApprove)
  const canWithdraw = ref(approval.canWithdraw)

  /** 从编排基类实例同步响应式面（集合面重建）。 */
  const sync = (): void => {
    ready.value = approval.ready
    degraded.value = approval.degraded
    disabled.value = approval.disabled
    busy.value = approval.busy
    phase.value = approval.phase
    instance.value = approval.instance
    records.value = approval.records
    currentTask.value = approval.currentTask
    instanceState.value = approval.instanceState
    recordsState.value = approval.recordsState
    errorMessage.value = approval.errorMessage
    errorHandling.value = approval.errorHandling
    pendingRefresh.value = approval.pendingRefresh
    requestCount.value = approval.requestCount
    diagramMode.value = approval.diagramMode
    diagramXml.value = approval.diagramXml
    diagramUrl.value = approval.diagramUrl
    readonlyState.value = approval.readonly
    canApprove.value = approval.canApprove
    canWithdraw.value = approval.canWithdraw
  }

  const off = approval.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  // 派生面必须读**响应式面**（核心基类字段非响应式；直接读实例会让 computed 首次求值后永久缓存）。
  const progress = computed<ApprovalProgressSummary>(() => {
    const current = instance.value
    if (current === undefined) {
      return { done: 0, total: 0, activeName: '' }
    }
    return resolveProgressSummary(current)
  })
  const actions = computed(() =>
    resolveApprovalActions({
      status: instance.value?.status,
      canApprove: canApprove.value,
      canWithdraw: canWithdraw.value,
      hasTask: currentTask.value !== undefined,
      taskId: currentTask.value?.taskId,
    }),
  )

  return {
    approval,
    ready,
    degraded,
    disabled,
    busy,
    phase,
    instance,
    records,
    currentTask,
    instanceState,
    recordsState,
    errorMessage,
    errorHandling,
    pendingRefresh,
    requestCount,
    diagramMode,
    diagramXml,
    diagramUrl,
    readonly: readonlyState,
    progress,
    actions,
    canApprove,
    canWithdraw,
    setReady: (value) => {
      approval.setReady(value)
      sync()
    },
    setInstanceId: (instanceId) => {
      approval.setInstanceId(instanceId)
      sync()
    },
    setJobs: (jobs) => {
      approval.setJobs(jobs)
      sync()
    },
    setAccess: (access) => {
      approval.setAccess(access === undefined ? undefined : markRaw(toRaw(access)))
      sync()
    },
    setPresigned: (presigned) => {
      approval.setPresigned(presigned === undefined ? undefined : markRaw(toRaw(presigned)))
      sync()
    },
    setNotice: (notice) => {
      approval.setNotice(notice === undefined ? undefined : markRaw(toRaw(notice)))
      sync()
    },
    setApprovable: (value) => {
      approval.approvable = value
      sync()
    },
    setWithdrawable: (value) => {
      approval.withdrawable = value
      sync()
    },
    applyInstance: (input) => {
      approval.applyInstance(input)
      sync()
    },
    applyRecords: (input) => {
      approval.applyRecords(input)
      sync()
    },
    applyTask: (input) => {
      approval.applyTask(input)
      sync()
    },
    load: async () => {
      const result = await approval.load()
      sync()
      return result
    },
    reload: async () => {
      const result = await approval.reload()
      sync()
      return result
    },
    loadDiagramImage: async () => {
      const result = await approval.loadDiagramImage()
      sync()
      return result
    },
    markDiagramFailed: () => {
      approval.markDiagramFailed()
      sync()
    },
    idempotencyKey: (action, comment, target) => approval.idempotencyKey(action, comment, target),
    validate: (action, input) => approval.validate(action, input),
    submit: async (action, input) => {
      const result = await approval.submit(action, input)
      sync()
      return result
    },
    retry: async () => {
      const result = await approval.retry()
      sync()
      return result
    },
    reset: () => {
      approval.reset()
      sync()
    },
  }
}
