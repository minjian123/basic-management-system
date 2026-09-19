/**
 * 导出流能力基类：取数参数同口径 / 筛选与选中范围 / 脱敏与明文 / 同步下载与超阈值异步导出 / 进度与取消 / 失败重试。
 *
 * **数据通路由宿主注入**（导出处理函数、后台任务轮询）——未注入即占位：不发请求、返回 `undefined`、写占位文案；
 * 后台任务经组合的 `BaseAsyncTask`（poller 两段）提交与轮询，结果下载经组合的 `BaseFileDownload` 触发。
 * 核心不触 DOM、不发请求。
 */

import { BaseComponent } from '../base/BaseComponent'
import {
  EXPORT_EMPTY_TEXT,
  EXPORT_PERM,
  EXPORT_PLACEHOLDER_TEXT,
  EXPORT_PLAIN_PERM,
  EXPORT_QUEUED_TEXT,
  canExportPlain,
  exportFileName,
  normalizeExportParams,
  normalizeSelectedIds,
  resolveExportDecision,
  resolveExportMode,
  type ExportQueryParams,
  type ExportScope,
} from '../domain/export'
import type { BaseAccess } from './access'
import type { BaseAsyncTask, TaskPollOutcome, TaskProgress } from './async-task'
import type { BaseFileDownload } from './file-download'
import type { BaseNotice } from './notice'

/** 导出阶段。 */
export type ExportPhase = 'idle' | 'exporting' | 'queued' | 'done' | 'failed'

/** 导出请求载荷。 */
export interface ExportRequest {
  /** 业务标识。 */
  biz: string
  /** 导出范围。 */
  scope: ExportScope
  /** 取数参数（与列表查询同口径）。 */
  params: ExportQueryParams | undefined
  /** 选中行标识（选中导出）。 */
  selectedIds: string[] | undefined
  /** 是否明文导出（已按权限收窄）。 */
  plain: boolean
  /** 文件名（含时间戳）。 */
  filename: string
}

/** 导出结果（同步文件流信息或后台任务结果）。 */
export interface ExportResult {
  /** 文件标识。 */
  fileId?: string
  /** 文件名。 */
  fileName?: string
  /** 下载地址。 */
  url?: string
  /** 一次性令牌。 */
  token?: string
  /** 是否转后台任务。 */
  async?: boolean
  /** 结果提示文案。 */
  message?: string
}

/** 导出处理函数（宿主注入；同步触发下载或提交后台任务）。 */
export type ExportHandler = (
  input: ExportRequest & { signal: { readonly aborted: boolean }; report: (progress: TaskProgress) => void },
) => Promise<ExportResult | undefined>

/** 轮询处理函数（宿主注入；后台任务进度复查）。 */
export type ExportPollHandler = (handle: unknown, attempt: number) => Promise<TaskPollOutcome<ExportResult>>

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface ExportJobs {
  /** 导出执行（同步文件流或提交后台任务）。 */
  export?: ExportHandler
  /** 后台任务轮询。 */
  poll?: ExportPollHandler
}

/** 导出流能力基类（抽象）。 */
export abstract class BaseExportFlow extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'export-flow'
  /** 依赖能力键。 */
  override readonly depends = ['async-task', 'file-download', 'access', 'notice']
  /** 业务标识。 */
  biz = ''
  /** 业务中文名（文件名前缀缺省取此值）。 */
  bizName = ''
  /** 当前筛选与排序参数。 */
  params: ExportQueryParams | undefined
  /** 选中行标识。 */
  selectedIds: string[] | undefined
  /** 导出范围。 */
  scope: ExportScope = 'filtered'
  /** 异步阈值（0 = 前端不判断）。 */
  asyncThreshold = 0
  /** 当前筛选总条数。 */
  total = 0
  /** 是否申请明文导出（需 `data:plain` 权限码）。 */
  plain = false
  /** 文件名前缀（缺省取业务中文名 / 业务标识）。 */
  filenamePrefix = ''
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false
  /** 实际发起的请求计数（占位期恒 0）。 */
  requestCount = 0
  /** 当前阶段。 */
  phase: ExportPhase = 'idle'
  /** 任务进度。 */
  progress: TaskProgress = { value: 0, total: 0 }
  /** 失败文案。 */
  errorMessage = ''
  /** 最近一次结果。 */
  lastResult: ExportResult | undefined
  /** 宿主注入的处理函数集。 */
  jobs: ExportJobs = {}
  /** 异步任务（组合；后台导出经其 poller 两段）。 */
  task: BaseAsyncTask<ExportResult> | undefined
  /** 下载触发（组合；结果下载经其触发）。 */
  download: BaseFileDownload | undefined
  /** 权限上下文（未注入不校验导出权限）。 */
  access: BaseAccess | undefined
  /** 提示通知（未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 当前中断信号（导出时重建）。 */
  #signal: { aborted: boolean } = { aborted: false }

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否进行中（导出 / 排队）。 */
  get busy(): boolean {
    return this.phase === 'exporting' || this.phase === 'queued'
  }

  /** 导出处理函数是否已注入（未注入即占位）。 */
  get exportReady(): boolean {
    return this.jobs.export !== undefined
  }

  /** 是否走后台异步通路。 */
  get asyncMode(): boolean {
    return resolveExportMode({ total: this.total, threshold: this.asyncThreshold }) === 'async'
  }

  /** 当前筛选是否无数据。 */
  get empty(): boolean {
    return this.total <= 0
  }

  /** 是否可导出（就绪 ∧ 有权 ∧ 范围合法 ∧ 有数据 ∧ 非进行中）。 */
  get canExport(): boolean {
    return !this.busy && resolveExportDecision(this.decisionInput()).allowed
  }

  /** 是否按明文导出（申请明文且持 `data:plain`）。 */
  get plainAllowed(): boolean {
    return canExportPlain(this.plain, this.access !== undefined && this.access.has(EXPORT_PLAIN_PERM))
  }

  /** 导出载荷（取数参数同口径、选中集合归一并含时间戳文件名）。 */
  get plan(): ExportRequest {
    const params = normalizeExportParams(this.params)
    const prefix = this.filenamePrefix !== '' ? this.filenamePrefix : this.bizName !== '' ? this.bizName : this.biz
    return {
      biz: this.biz,
      scope: this.scope,
      params: Object.keys(params).length === 0 ? undefined : params,
      selectedIds: this.scope === 'selected' ? normalizeSelectedIds(this.selectedIds) : undefined,
      plain: this.plainAllowed,
      filename: exportFileName(prefix, new Date()),
    }
  }

  /**
   * 设置就绪态（占位语义开关）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    if (this.ready === value) {
      return
    }
    this.ready = value
    this.touch()
  }

  /**
   * 设置业务标识与中文名。
   *
   * @param biz 业务标识。
   * @param bizName 业务中文名（缺省用业务标识）。
   */
  setBiz(biz: string, bizName?: string): void {
    this.biz = biz
    this.bizName = bizName ?? biz
    this.touch()
  }

  /**
   * 设置取数参数（与列表查询同口径）。
   *
   * @param params 取数参数。
   */
  setParams(params?: Record<string, unknown>): void {
    this.params = params
    this.touch()
  }

  /**
   * 设置导出范围与选中行。
   *
   * @param scope 导出范围。
   * @param selectedIds 选中行标识（选中导出用）。
   */
  setScope(scope: ExportScope, selectedIds?: readonly (string | number)[]): void {
    this.scope = scope
    if (selectedIds !== undefined) {
      this.selectedIds = normalizeSelectedIds(selectedIds)
    }
    this.touch()
  }

  /**
   * 设置选中行标识。
   *
   * @param ids 选中行标识。
   */
  setSelected(ids?: readonly (string | number)[]): void {
    this.selectedIds = normalizeSelectedIds(ids)
    this.touch()
  }

  /**
   * 设置当前筛选总条数。
   *
   * @param total 总条数。
   */
  setTotal(total: number): void {
    this.total = Number.isFinite(total) && total > 0 ? Math.floor(total) : 0
    this.touch()
  }

  /**
   * 设置是否申请明文导出。
   *
   * @param plain 是否申请明文。
   */
  setPlain(plain: boolean): void {
    if (this.plain === plain) {
      return
    }
    this.plain = plain
    this.touch()
  }

  /**
   * 设置异步阈值。
   *
   * @param threshold 行数阈值（0 = 前端不判断）。
   */
  setThreshold(threshold: number): void {
    this.asyncThreshold = Number.isFinite(threshold) && threshold > 0 ? Math.floor(threshold) : 0
    this.touch()
  }

  /**
   * 设置外部禁用。
   *
   * @param disabled 是否禁用。
   */
  setDisabled(disabled: boolean): void {
    if (this.disabled === disabled) {
      return
    }
    this.disabled = disabled
    this.touch()
  }

  /**
   * 触发导出（处理函数未注入即占位不动作）。
   *
   * @returns 导出结果；占位 / 未就绪 / 无权限 / 无数据 / 未选中 / 进行中 / 取消时返回 `undefined`。
   */
  async export(): Promise<ExportResult | undefined> {
    const decision = resolveExportDecision(this.decisionInput())
    if (!decision.allowed) {
      if (decision.reason === 'degraded' || decision.reason === 'empty') {
        this.errorMessage = decision.reason === 'empty' ? EXPORT_EMPTY_TEXT : EXPORT_PLACEHOLDER_TEXT
        this.touch()
      }
      return undefined
    }
    const handler = this.jobs.export
    if (handler === undefined) {
      this.errorMessage = EXPORT_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    if (this.busy) {
      return undefined
    }
    const request = this.plan
    const signal = { aborted: false }
    this.#signal = signal
    this.errorMessage = ''
    this.progress = { value: 0, total: this.total }
    this.requestCount += 1
    const report = (progress: TaskProgress): void => {
      this.progress = progress
      this.touch()
    }
    try {
      if (decision.mode === 'async' && this.task !== undefined && this.jobs.poll !== undefined) {
        this.phase = 'queued'
        this.touch()
        const poll = this.jobs.poll
        this.task.submitter = async () => handler({ ...request, signal, report })
        this.task.poller = async (handle, attempt) => {
          const outcome = await poll(handle, attempt)
          if (outcome.progress !== undefined) {
            this.progress = outcome.progress
            this.touch()
          }
          return outcome
        }
        this.task.abort = () => {
          signal.aborted = true
        }
        await this.task.submit()
        if (this.task.status === 'error') {
          return this.fail('后台导出任务失败')
        }
        if (this.task.status === 'canceled' || signal.aborted) {
          this.phase = 'idle'
          this.touch()
          return undefined
        }
        return this.settle(this.task.result, true, request.filename)
      }
      this.phase = 'exporting'
      this.touch()
      const result = await handler({ ...request, signal, report })
      if (signal.aborted) {
        this.phase = 'idle'
        this.touch()
        return undefined
      }
      return this.settle(result, decision.mode === 'async', request.filename)
    } catch (error) {
      if (signal.aborted) {
        this.phase = 'idle'
        this.touch()
        return undefined
      }
      return this.fail(error instanceof Error && error.message !== '' ? error.message : '导出失败')
    }
  }

  /** 取消导出（后台任务经任务取消；同步请求经中断信号）。 */
  cancel(): void {
    this.#signal.aborted = true
    this.task?.cancel()
    if (this.busy) {
      this.phase = 'idle'
      this.touch()
    }
  }

  /**
   * 重试上一次失败导出（同参数重放）。
   *
   * @returns 导出结果；非失败态时返回 `undefined`。
   */
  async retry(): Promise<ExportResult | undefined> {
    if (this.phase !== 'failed') {
      return undefined
    }
    return this.export()
  }

  /** 复位编排状态（保留取数参数、范围与权限上下文）。 */
  reset(): void {
    this.phase = 'idle'
    this.errorMessage = ''
    this.progress = { value: 0, total: 0 }
    this.lastResult = undefined
    this.#signal = { aborted: false }
    this.touch()
  }

  /**
   * 决策输入（就绪 / 禁用 / 权限 / 范围 / 数据量）。
   */
  private decisionInput(): {
    ready: boolean
    disabled: boolean
    permAllowed: boolean
    scope: ExportScope
    selectedIds: string[] | undefined
    total: number
    threshold: number
  } {
    return {
      ready: this.ready,
      disabled: this.disabled,
      permAllowed: this.isAllowed(EXPORT_PERM),
      scope: this.scope,
      selectedIds: this.selectedIds,
      total: this.total,
      threshold: this.asyncThreshold,
    }
  }

  /**
   * 是否具备某权限码（权限上下文未注入或权限码为空时视为有权）。
   *
   * @param perm 权限码。
   * @returns 是否具备。
   */
  private isAllowed(perm: string): boolean {
    if (perm === '' || this.access === undefined) {
      return true
    }
    return this.access.has(perm)
  }

  /**
   * 结果汇总（记录结果、阶段置完成、必要时触发下载与提示）。
   *
   * @param result 处理函数返回结果（可为 `undefined`）。
   * @param queued 是否后台异步通路。
   * @param filename 请求文件名（结果未给文件名时兜底）。
   */
  private settle(result: ExportResult | undefined, queued: boolean, filename: string): ExportResult {
    const final: ExportResult = queued ? { async: true, ...(result ?? {}) } : { ...(result ?? {}) }
    const message = final.message ?? (queued ? EXPORT_QUEUED_TEXT : '导出完成')
    this.lastResult = final
    this.phase = 'done'
    const url = final.url
    if (this.download !== undefined && ((url !== undefined && url !== '') || final.token !== undefined)) {
      void this.download.download({
        url,
        token: final.token,
        biz: this.biz,
        kind: 'export',
        filename: final.fileName ?? filename,
      })
    }
    if (this.notice !== undefined) {
      this.notice.enqueue(message, queued ? 'info' : 'success')
    }
    this.touch()
    return { ...final, message }
  }

  /**
   * 失败处置（阶段置失败、写文案、提示）。
   *
   * @param message 失败文案。
   */
  private fail(message: string): undefined {
    this.phase = 'failed'
    this.errorMessage = message
    if (this.notice !== undefined) {
      this.notice.enqueue(message, 'error')
    }
    this.touch()
    return undefined
  }

  /** 通知变更（已释放时跳过）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
