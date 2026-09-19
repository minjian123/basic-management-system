/** 导入流投影：把核心能力基类 `BaseImportFlow` 投影为组合式（文件校验 / 幂等键 / 阶段与进度 / 错误行报告 / 下载）。 */

import {
  BaseImportFlow,
  type BaseAccess,
  type BaseNotice,
  type BaseUploadEngine,
  type BaseFileDownload,
  type DownloadResult,
  type ImportErrorRow,
  type ImportFileMeta,
  type ImportJobs,
  type ImportPhase,
  type ImportResult,
  type ImportStep,
  type ImportSummaryState,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体导入流件（可实例化）。 */
class ImportFlow extends BaseImportFlow {}

/** 选项。 */
export interface UseBaseImportFlowOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 业务标识（后端路径段）。 */
  biz?: string
  /** 业务中文名（标题与错误明细文件名）。 */
  bizName?: string
  /** 接受的文件类型。 */
  accept?: string
  /** 文件大小上限（字节；0 表示不限）。 */
  maxSize?: number
  /** 模板下载参数。 */
  templateParams?: Record<string, unknown>
  /** 全部成功后是否自动关闭。 */
  successAutoClose?: boolean
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: ImportJobs
  /** 上传引擎（组合；进度与取消由其承载）。 */
  engine?: BaseUploadEngine<unknown>
  /** 下载触发能力（组合；模板与错误明细下载经其触发）。 */
  download?: BaseFileDownload
  /** 权限上下文（未注入不校验）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
}

/** `useBaseImportFlow` 返回面。 */
export interface UseBaseImportFlowResult {
  /** 导入流基类实例。 */
  flow: BaseImportFlow
  /** 数据通路是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 是否进行中（上传 / 解析，响应式）。 */
  busy: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<ImportPhase>
  /** 当前步骤（响应式）。 */
  step: Ref<ImportStep>
  /** 上传进度（响应式）。 */
  progress: Ref<number>
  /** 幂等键（响应式）。 */
  idempotencyKey: Ref<string>
  /** 已选文件元信息（响应式）。 */
  fileMeta: Ref<ImportFileMeta | undefined>
  /** 是否已选可用文件（通过校验且未清空，响应式）。 */
  hasFile: Ref<boolean>
  /** 文件校验失败文案（响应式）。 */
  fileError: Ref<string>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 导入结果（响应式）。 */
  result: Ref<ImportResult | undefined>
  /** 当前页错误行（响应式）。 */
  errorRows: Ref<ImportErrorRow[]>
  /** 错误行当前页码（响应式）。 */
  errorPage: Ref<number>
  /** 错误行总页数（响应式）。 */
  errorPageCount: Ref<number>
  /** 错误行是否截断（响应式）。 */
  errorTruncated: Ref<boolean>
  /** 结果汇总态（响应式）。 */
  summary: Ref<ImportSummaryState>
  /** 是否可提交导入（响应式）。 */
  canImport: Ref<boolean>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 设置业务标识与中文名。 */
  setBiz: (biz: string, bizName?: string) => void
  /** 注入处理函数集（整体替换；未注入的项按占位）。 */
  setJobs: (jobs: ImportJobs) => void
  /** 选择文件（映射 `File` 为元信息后交核心校验）。 */
  selectFile: (file: unknown, meta: ImportFileMeta) => boolean
  /** 清空已选文件与幂等键。 */
  clearFile: () => void
  /** 切换错误行页码（夹取）。 */
  setErrorPage: (page: number) => void
  /** 提交导入。 */
  submit: () => Promise<ImportResult | undefined>
  /** 取消导入。 */
  cancel: () => void
  /** 重试失败导入（同幂等键）。 */
  retry: () => Promise<ImportResult | undefined>
  /** 重新导入（回选文件步并重置）。 */
  reset: () => void
  /** 下载模板。 */
  downloadTemplate: () => Promise<DownloadResult | undefined>
  /** 下载错误明细。 */
  downloadErrors: () => Promise<DownloadResult | undefined>
}

/**
 * 使用导入流投影。
 *
 * @param options 选项。
 * @returns 导入流基类实例与响应式面。
 */
export function useBaseImportFlow(options: UseBaseImportFlowOptions = {}): UseBaseImportFlowResult {
  const flow = new ImportFlow()
  if (options.accept !== undefined) {
    flow.accept = options.accept
  }
  if (options.maxSize !== undefined) {
    flow.maxSize = options.maxSize
  }
  flow.templateParams = options.templateParams
  flow.successAutoClose = options.successAutoClose ?? false
  if (options.biz !== undefined) {
    flow.setBiz(options.biz, options.bizName)
  }
  if (options.jobs !== undefined) {
    flow.jobs = options.jobs
  }
  if (options.engine !== undefined) {
    flow.engine = markRaw(toRaw(options.engine))
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
  flow.setReady(options.ready ?? false)

  const ready = ref(flow.ready)
  const degraded = ref(flow.degraded)
  const busy = ref(flow.busy)
  const phase = ref<ImportPhase>(flow.phase)
  const step = ref<ImportStep>(flow.step)
  const progress = ref(flow.progress)
  const idempotencyKey = ref(flow.idempotencyKey)
  const fileMeta = ref<ImportFileMeta | undefined>(flow.fileMeta)
  const hasFile = ref(flow.file !== undefined)
  const fileError = ref(flow.fileError)
  const errorMessage = ref(flow.errorMessage)
  const result = ref<ImportResult | undefined>(flow.result)
  const errorRows = ref<ImportErrorRow[]>(flow.errorRows)
  const errorPage = ref(flow.errorPage)
  const errorPageCount = ref(flow.errorPageCount)
  const errorTruncated = ref(flow.errorTruncated)
  const summary = ref<ImportSummaryState>(flow.summary)
  const canImport = ref(flow.canImport)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = flow.ready
    degraded.value = flow.degraded
    busy.value = flow.busy
    phase.value = flow.phase
    step.value = flow.step
    progress.value = flow.progress
    idempotencyKey.value = flow.idempotencyKey
    fileMeta.value = flow.fileMeta
    hasFile.value = flow.file !== undefined
    fileError.value = flow.fileError
    errorMessage.value = flow.errorMessage
    result.value = flow.result
    errorRows.value = flow.errorRows
    errorPage.value = flow.errorPage
    errorPageCount.value = flow.errorPageCount
    errorTruncated.value = flow.errorTruncated
    summary.value = flow.summary
    canImport.value = flow.canImport
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
    step,
    progress,
    idempotencyKey,
    fileMeta,
    hasFile,
    fileError,
    errorMessage,
    result,
    errorRows,
    errorPage,
    errorPageCount,
    errorTruncated,
    summary,
    canImport,
    setReady: (value) => {
      flow.setReady(value)
      sync()
    },
    setBiz: (biz, bizName) => {
      flow.setBiz(biz, bizName)
      sync()
    },
    setJobs: (jobs) => {
      flow.jobs = jobs
      sync()
    },
    selectFile: (file, meta) => {
      const applied = flow.selectFile(file, meta)
      sync()
      return applied
    },
    clearFile: () => {
      flow.clearFile()
      sync()
    },
    setErrorPage: (page) => {
      flow.setErrorPage(page)
      sync()
    },
    submit: async () => {
      const value = await flow.submit()
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
    downloadTemplate: async () => {
      const value = await flow.downloadTemplate()
      sync()
      return value
    },
    downloadErrors: async () => {
      const value = await flow.downloadErrors()
      sync()
      return value
    },
  }
}
