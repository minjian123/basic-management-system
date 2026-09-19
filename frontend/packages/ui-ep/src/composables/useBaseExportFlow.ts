/** 导出流投影：把核心能力基类 `BaseExportFlow` 投影为组合式（取数参数 / 范围 / 脱敏 / 同步与异步通路 / 进度与取消）。 */

import {
  BaseExportFlow,
  type BaseAccess,
  type BaseAsyncTask,
  type BaseFileDownload,
  type BaseNotice,
  type ExportJobs,
  type ExportPhase,
  type ExportRequest,
  type ExportResult,
  type ExportScope,
  type TaskProgress,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体导出流件（可实例化）。 */
class ExportFlow extends BaseExportFlow {}

/** 选项。 */
export interface UseBaseExportFlowOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 业务标识。 */
  biz?: string
  /** 业务中文名（文件名前缀缺省取此值）。 */
  bizName?: string
  /** 当前筛选与排序参数。 */
  params?: Record<string, unknown>
  /** 选中行标识。 */
  selectedIds?: readonly (string | number)[]
  /** 导出范围（缺省 `filtered`）。 */
  scope?: ExportScope
  /** 异步阈值（0 = 前端不判断）。 */
  asyncThreshold?: number
  /** 当前筛选总条数。 */
  total?: number
  /** 是否申请明文导出。 */
  plain?: boolean
  /** 文件名前缀。 */
  filenamePrefix?: string
  /** 外部禁用。 */
  disabled?: boolean
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: ExportJobs
  /** 异步任务能力（后台导出经其 poller 两段）。 */
  task?: BaseAsyncTask<ExportResult>
  /** 下载触发能力（组合；结果下载经其触发）。 */
  download?: BaseFileDownload
  /** 权限上下文（未注入不校验）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
}

/** `useBaseExportFlow` 返回面。 */
export interface UseBaseExportFlowResult {
  /** 导出流基类实例。 */
  flow: BaseExportFlow
  /** 数据通路是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 是否进行中（导出 / 排队，响应式）。 */
  busy: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<ExportPhase>
  /** 任务进度（响应式）。 */
  progress: Ref<TaskProgress>
  /** 是否可导出（响应式）。 */
  canExport: Ref<boolean>
  /** 是否走后台异步通路（响应式）。 */
  asyncMode: Ref<boolean>
  /** 当前筛选是否无数据（响应式）。 */
  empty: Ref<boolean>
  /** 导出处理是否已注入（响应式）。 */
  exportReady: Ref<boolean>
  /** 是否按明文导出（响应式）。 */
  plainAllowed: Ref<boolean>
  /** 最近一次结果（响应式）。 */
  lastResult: Ref<ExportResult | undefined>
  /** 导出载荷（响应式）。 */
  plan: Ref<ExportRequest>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 设置业务标识与中文名。 */
  setBiz: (biz: string, bizName?: string) => void
  /** 设置取数参数。 */
  setParams: (params?: Record<string, unknown>) => void
  /** 设置导出范围与选中行。 */
  setScope: (scope: ExportScope, selectedIds?: readonly (string | number)[]) => void
  /** 设置选中行标识。 */
  setSelected: (ids?: readonly (string | number)[]) => void
  /** 设置当前筛选总条数。 */
  setTotal: (total: number) => void
  /** 设置是否申请明文导出。 */
  setPlain: (plain: boolean) => void
  /** 设置异步阈值。 */
  setThreshold: (threshold: number) => void
  /** 设置外部禁用。 */
  setDisabled: (disabled: boolean) => void
  /** 注入处理函数集（整体替换；未注入的项按占位）。 */
  setJobs: (jobs: ExportJobs) => void
  /** 触发导出。 */
  run: () => Promise<ExportResult | undefined>
  /** 取消导出。 */
  cancel: () => void
  /** 重试失败导出（同参数重放）。 */
  retry: () => Promise<ExportResult | undefined>
  /** 复位编排状态。 */
  reset: () => void
}

/**
 * 使用导出流投影。
 *
 * @param options 选项。
 * @returns 导出流基类实例与响应式面。
 */
export function useBaseExportFlow(options: UseBaseExportFlowOptions = {}): UseBaseExportFlowResult {
  const flow = new ExportFlow()
  if (options.biz !== undefined) {
    flow.setBiz(options.biz, options.bizName)
  }
  if (options.params !== undefined) {
    flow.setParams(options.params)
  }
  if (options.scope !== undefined || options.selectedIds !== undefined) {
    flow.setScope(options.scope ?? 'filtered', options.selectedIds)
  }
  if (options.asyncThreshold !== undefined) {
    flow.setThreshold(options.asyncThreshold)
  }
  if (options.total !== undefined) {
    flow.setTotal(options.total)
  }
  if (options.plain !== undefined) {
    flow.setPlain(options.plain)
  }
  if (options.filenamePrefix !== undefined) {
    flow.filenamePrefix = options.filenamePrefix
  }
  if (options.jobs !== undefined) {
    flow.jobs = options.jobs
  }
  if (options.task !== undefined) {
    flow.task = markRaw(toRaw(options.task))
  }
  if (options.download !== undefined) {
    flow.download = markRaw(toRaw(options.download))
  }
  if (options.access !== undefined) {
    flow.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    flow.notice = markRaw(toRaw(options.notice))
  }
  flow.setDisabled(options.disabled ?? false)
  flow.setReady(options.ready ?? false)

  const ready = ref(flow.ready)
  const degraded = ref(flow.degraded)
  const busy = ref(flow.busy)
  const phase = ref<ExportPhase>(flow.phase)
  const progress = ref<TaskProgress>({ ...flow.progress })
  const canExport = ref(flow.canExport)
  const asyncMode = ref(flow.asyncMode)
  const empty = ref(flow.empty)
  const exportReady = ref(flow.exportReady)
  const plainAllowed = ref(flow.plainAllowed)
  const lastResult = ref<ExportResult | undefined>(flow.lastResult)
  const plan = ref<ExportRequest>(flow.plan)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = flow.ready
    degraded.value = flow.degraded
    busy.value = flow.busy
    phase.value = flow.phase
    progress.value = { ...flow.progress }
    canExport.value = flow.canExport
    asyncMode.value = flow.asyncMode
    empty.value = flow.empty
    exportReady.value = flow.exportReady
    plainAllowed.value = flow.plainAllowed
    lastResult.value = flow.lastResult
    plan.value = flow.plan
  }

  const off = flow.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    flow,
    ready,
    degraded,
    busy,
    phase,
    progress,
    canExport,
    asyncMode,
    empty,
    exportReady,
    plainAllowed,
    lastResult,
    plan,
    setReady: (value) => {
      flow.setReady(value)
      sync()
    },
    setBiz: (biz, bizName) => {
      flow.setBiz(biz, bizName)
      sync()
    },
    setParams: (params) => {
      flow.setParams(params)
      sync()
    },
    setScope: (scope, selectedIds) => {
      flow.setScope(scope, selectedIds)
      sync()
    },
    setSelected: (ids) => {
      flow.setSelected(ids)
      sync()
    },
    setTotal: (total) => {
      flow.setTotal(total)
      sync()
    },
    setPlain: (plain) => {
      flow.setPlain(plain)
      sync()
    },
    setThreshold: (threshold) => {
      flow.setThreshold(threshold)
      sync()
    },
    setDisabled: (disabled) => {
      flow.setDisabled(disabled)
      sync()
    },
    setJobs: (jobs) => {
      flow.jobs = jobs
      sync()
    },
    run: async () => {
      const value = await flow.export()
      sync()
      return value
    },
    cancel: () => {
      flow.cancel()
      sync()
    },
    retry: async () => {
      const value = await flow.retry()
      sync()
      return value
    },
    reset: () => {
      flow.reset()
      sync()
    },
  }
}
