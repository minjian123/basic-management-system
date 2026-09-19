/**
 * 打印与导出编排能力基类：预览显隐与缩放 / 模板选择 / 批量模式 / 浏览器打印阶段 / 导出与批量任务 / 进度 / 失败重试。
 *
 * 在打印模板能力基类 `BasePrintTemplate` 之上派生：模板与数据是底座，编排是其上的一层。
 * 导出与批量**处理函数由宿主注入**（服务端高保真 PDF 归后端实现）——未注入即占位：不请求、不动作；
 * 注入后阶段机、进度与失败重试真实生效。**不含 DOM 语义**（`window.print()` 与打印样式归件层）。
 */

import type { PaperName, PaperOrientation, PrintTone } from '../domain/print'
import { BasePrintTemplate } from './print-template'
import type { BaseAccess } from './access'
import type { BaseAsyncTask } from './async-task'
import type { BaseNotice } from './notice'

/** 编排阶段。 */
export type PrintPhase = 'idle' | 'printing' | 'exporting' | 'batching' | 'done' | 'failed'

/** 批量模式（逐份 / 合并）。 */
export type PrintBatchMode = 'separate' | 'merged'

/** 任务进度。 */
export interface PrintProgress {
  /** 已完成量。 */
  current: number
  /** 总量。 */
  total: number
}

/** 任务载荷（导出与批量共用）。 */
export interface PrintJobPayload {
  /** 模板键。 */
  templateKey: string
  /** 纸张。 */
  paper: PaperName
  /** 纸张方向。 */
  orientation: PaperOrientation
  /** 色调。 */
  tone: PrintTone
  /** 水印文案。 */
  watermark: string
  /** 单据键集合（单条导出为空）。 */
  keys: string[]
  /** 批量模式。 */
  mode: PrintBatchMode
}

/** 任务结果（服务端返回的文件信息）。 */
export interface PrintJobResult {
  /** 文件标识。 */
  fileId?: string
  /** 文件名。 */
  fileName?: string
  /** 下载 / 分享地址。 */
  url?: string
  /** 结果提示文案。 */
  message?: string
}

/** 任务处理函数（宿主注入；`report` 回传进度）。 */
export type PrintJobHandler = (
  payload: PrintJobPayload,
  report: (progress: PrintProgress) => void,
) => Promise<PrintJobResult>

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface PrintJobs {
  /** 导出 PDF（服务端高保真）。 */
  exportPdf?: PrintJobHandler
  /** 批量打印（多单据逐份 / 合并，交异步任务）。 */
  batchPrint?: PrintJobHandler
}

/** 任务种类。 */
type PrintJobKind = 'export' | 'batch'

/** 占位提示文案（导出 / 批量处理未注入）。 */
export const PRINT_JOB_PLACEHOLDER = '导出未就绪（占位）'

/** 缩放步长。 */
const ZOOM_STEP = 0.1

/** 打印与导出编排能力基类（抽象）。 */
export abstract class BasePrint extends BasePrintTemplate {
  /** 能力键。 */
  readonly identifier: string = 'print'
  /** 预览显隐（受控；件层 `v-model:visible` 同步）。 */
  previewVisible = false
  /** 缩放（夹取到 `minZoom` ~ `maxZoom`）。 */
  zoom = 1
  /** 缩放下限。 */
  minZoom = 0.6
  /** 缩放上限。 */
  maxZoom = 1.2
  /** 批量模式（逐份 / 合并）。 */
  batchMode: PrintBatchMode = 'separate'
  /** 导出许可（模板 / 业务开关；为假时件层隐藏导出入口）。 */
  allowExport = true
  /** 打印权限码（空串表示不校验）。 */
  printPerm = ''
  /** 导出权限码（空串表示不校验）。 */
  exportPerm = ''
  /** 编排阶段。 */
  phase: PrintPhase = 'idle'
  /** 任务进度。 */
  progress: PrintProgress = { current: 0, total: 0 }
  /** 失败文案。 */
  errorMessage = ''
  /** 最近一次任务结果。 */
  lastResult: PrintJobResult | undefined
  /** 宿主注入的处理函数集。 */
  jobs: PrintJobs = {}
  /** 异步任务能力（注入时经其提交并回传进度；未注入直接等待处理函数）。 */
  task: BaseAsyncTask<PrintJobResult> | undefined
  /** 权限上下文（注入且声明权限码时按权限过滤；未注入不校验）。 */
  access: BaseAccess | undefined
  /** 提示通知（注入时按结果提示；未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 最近一次任务种类（重试用）。 */
  private lastKind: PrintJobKind | undefined
  /** 最近一次任务的单据键（重试用）。 */
  private lastKeys: string[] = []

  /** 是否任务进行中（打印 / 导出 / 批量）。 */
  get busy(): boolean {
    return this.phase === 'printing' || this.phase === 'exporting' || this.phase === 'batching'
  }

  /** 是否可打印（非任务中且有打印权限）。 */
  get canPrint(): boolean {
    return !this.busy && this.isAllowed(this.printPerm)
  }

  /** 是否可导出（非任务中、有导出许可且有导出权限）。 */
  get canExport(): boolean {
    return this.allowExport && !this.busy && this.isAllowed(this.exportPerm)
  }

  /** 是否可批量打印（非任务中、有打印权限且注入批量处理）。 */
  get canBatch(): boolean {
    return !this.busy && this.isAllowed(this.printPerm) && this.batchReady
  }

  /** 导出处理是否已注入（未注入即占位）。 */
  get exportReady(): boolean {
    return this.jobs.exportPdf !== undefined
  }

  /** 批量处理是否已注入（未注入即占位）。 */
  get batchReady(): boolean {
    return this.jobs.batchPrint !== undefined
  }

  /**
   * 是否具备某权限码（权限上下文未注入或权限码为空时视为有权）。
   *
   * @param perm 权限码。
   */
  isAllowed(perm: string): boolean {
    if (perm === '' || this.access === undefined) {
      return true
    }
    return this.access.has(perm)
  }

  /** 打开预览。 */
  open(): void {
    if (this.previewVisible) {
      return
    }
    this.previewVisible = true
    this.touch()
  }

  /** 关闭预览。 */
  close(): void {
    if (!this.previewVisible) {
      return
    }
    this.previewVisible = false
    this.touch()
  }

  /**
   * 切换预览显隐。
   *
   * @returns 切换后的显隐态。
   */
  togglePreview(): boolean {
    this.previewVisible = !this.previewVisible
    this.touch()
    return this.previewVisible
  }

  /**
   * 设置缩放（夹取到下限与上限之间）。
   *
   * @param value 缩放值。
   * @returns 夹取后的缩放值。
   */
  setZoom(value: number): number {
    if (!Number.isFinite(value)) {
      return this.zoom
    }
    const clamped = Math.min(this.maxZoom, Math.max(this.minZoom, value))
    const next = Math.round(clamped * 100) / 100
    if (next === this.zoom) {
      return this.zoom
    }
    this.zoom = next
    this.touch()
    return next
  }

  /**
   * 放大一档（不少于下限，不超上限）。
   *
   * @returns 放大后的缩放值。
   */
  zoomIn(): number {
    return this.setZoom(this.zoom + ZOOM_STEP)
  }

  /**
   * 缩小一档（不少于下限，不超上限）。
   *
   * @returns 缩小后的缩放值。
   */
  zoomOut(): number {
    return this.setZoom(this.zoom - ZOOM_STEP)
  }

  /**
   * 设置批量模式（逐份 / 合并）。
   *
   * @param mode 批量模式。
   */
  setBatchMode(mode: PrintBatchMode): void {
    if (this.batchMode === mode) {
      return
    }
    this.batchMode = mode
    this.touch()
  }

  /**
   * 设置导出许可。
   *
   * @param value 是否允许导出。
   */
  setAllowExport(value: boolean): void {
    if (this.allowExport === value) {
      return
    }
    this.allowExport = value
    this.touch()
  }

  /**
   * 记录浏览器打印调起（阶段置 `printing`；`window.print()` 由件层调用）。
   */
  beginPrint(): void {
    if (this.busy) {
      return
    }
    this.phase = 'printing'
    this.errorMessage = ''
    this.touch()
  }

  /**
   * 记录浏览器打印结束（阶段置 `done`；浏览器打印结果前端不可感知，只记调起）。
   *
   * @returns 打印结果（提示文案）。
   */
  finishPrint(): PrintJobResult {
    const result: PrintJobResult = { message: '已调起浏览器打印' }
    this.lastResult = result
    this.phase = 'done'
    this.touch()
    return result
  }

  /**
   * 导出 PDF（服务端高保真；处理函数未注入即占位不动作）。
   *
   * @returns 导出结果；无许可 / 任务中 / 未注入处理时返回 `undefined`。
   */
  async exportPdf(): Promise<PrintJobResult | undefined> {
    if (!this.canExport) {
      return undefined
    }
    return this.runJob('export', this.buildPayload([]))
  }

  /**
   * 批量打印（多单据；处理函数未注入即占位不动作）。
   *
   * @param keys 单据键集合。
   * @returns 批量结果；无单据 / 无权限 / 任务中 / 未注入处理时返回 `undefined`。
   */
  async batchPrint(keys: string[]): Promise<PrintJobResult | undefined> {
    if (keys.length === 0 || !this.canBatch) {
      return undefined
    }
    return this.runJob('batch', this.buildPayload([...keys]))
  }

  /**
   * 重试上一次失败的任务。
   *
   * @returns 任务结果；非失败态 / 无上次任务 / 未注入处理时返回 `undefined`。
   */
  async retry(): Promise<PrintJobResult | undefined> {
    if (this.phase !== 'failed' || this.lastKind === undefined) {
      return undefined
    }
    const kind = this.lastKind
    const keys = [...this.lastKeys]
    if (kind === 'export' ? !this.canExport : keys.length === 0 || !this.canBatch) {
      return undefined
    }
    return this.runJob(kind, this.buildPayload(keys))
  }

  /** 重置编排状态（保留模板、数据与导出许可）。 */
  reset(): void {
    this.phase = 'idle'
    this.errorMessage = ''
    this.progress = { current: 0, total: 0 }
    this.lastResult = undefined
    this.lastKind = undefined
    this.lastKeys = []
    this.touch()
  }

  /**
   * 构造任务载荷。
   *
   * @param keys 单据键集合。
   */
  private buildPayload(keys: string[]): PrintJobPayload {
    return {
      templateKey: this.template?.key ?? '',
      paper: this.paper,
      orientation: this.orientation,
      tone: this.tone,
      watermark: this.watermarkText,
      keys,
      mode: this.batchMode,
    }
  }

  /**
   * 执行任务（占位 → 阶段推进 → 结果汇总 / 失败）。
   *
   * @param kind 任务种类。
   * @param payload 任务载荷。
   */
  private async runJob(kind: PrintJobKind, payload: PrintJobPayload): Promise<PrintJobResult | undefined> {
    const handler = kind === 'export' ? this.jobs.exportPdf : this.jobs.batchPrint
    if (handler === undefined) {
      this.errorMessage = PRINT_JOB_PLACEHOLDER
      this.touch()
      return undefined
    }
    this.phase = kind === 'export' ? 'exporting' : 'batching'
    this.errorMessage = ''
    this.lastKind = kind
    this.lastKeys = [...payload.keys]
    this.progress = { current: 0, total: Math.max(1, payload.keys.length) }
    this.touch()

    /** 进度上报（同步到进度并广播）。 */
    const report = (progress: PrintProgress): void => {
      this.progress = { current: progress.current, total: progress.total }
      this.touch()
    }

    try {
      const task = this.task
      let result: PrintJobResult
      if (task === undefined) {
        result = await handler(payload, report)
      } else {
        let failure: unknown
        task.executor = async (taskReport) => {
          taskReport({ value: this.progress.current, total: this.progress.total })
          try {
            return await handler(payload, (progress) => {
              report(progress)
              taskReport({ value: progress.current, total: progress.total })
            })
          } catch (error) {
            failure = error
            throw error
          }
        }
        await task.submit()
        if (task.status === 'error') {
          return this.fail(failure)
        }
        result = task.result ?? {}
      }
      return this.settle(result)
    } catch (error) {
      return this.fail(error)
    }
  }

  /**
   * 结果汇总（记录结果、阶段置完成、提示）。
   *
   * @param result 任务结果。
   */
  private settle(result: PrintJobResult): PrintJobResult {
    this.lastResult = result
    this.phase = 'done'
    if (this.notice !== undefined) {
      this.notice.enqueue(result.message ?? '导出完成', 'success')
    }
    this.touch()
    return result
  }

  /**
   * 失败处置（阶段置失败、写文案、提示）。
   *
   * @param error 失败原因。
   */
  private fail(error: unknown): undefined {
    this.phase = 'failed'
    this.errorMessage = error instanceof Error && error.message !== '' ? error.message : '导出失败'
    if (this.notice !== undefined) {
      this.notice.enqueue(this.errorMessage, 'error')
    }
    this.touch()
    return undefined
  }
}
