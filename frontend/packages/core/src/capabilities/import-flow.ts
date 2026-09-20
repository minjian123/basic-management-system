/**
 * 导入流能力基类：模板下载 / 文件校验 / 内容派生幂等键 / 上传解析阶段 / 错误行报告 / 失败重试与重置。
 *
 * **数据通路由宿主注入**（执行导入、模板与错误明细下载）——未注入即占位：不发请求、返回 `undefined`、写占位文案；
 * 上传进度与取消经组合的 `BaseUploadEngine` 承载，导出关联下载经组合的 `BaseFileDownload` 承载。
 * Excel 解析、模板列核对与行级校验归后端；核心不触 DOM、不发请求。
 */

import { BasePlaceholderState } from './placeholder-state'
import {
  IMPORT_ACCEPT,
  IMPORT_DEFAULT_MAX_SIZE,
  IMPORT_ERROR_PAGE_SIZE,
  IMPORT_PERM,
  IMPORT_PLACEHOLDER_TEXT,
  checkImportFile,
  deriveImportKey,
  errorReportFileName,
  normalizeImportResult,
  paginateImportErrors,
  resolveImportSummary,
  templateFileName,
  type ImportErrorRow,
  type ImportFileMeta,
  type ImportResult,
  type ImportResultInput,
  type ImportSummaryState,
} from '../domain/import'
import type { BaseAccess } from './access'
import type { BaseNotice } from './notice'
import type { BaseFileDownload, DownloadRequest, DownloadResult } from './file-download'
import type { BaseUploadEngine, UploadProgressReporter } from './upload-engine'

/** 导入步骤（与件层三步一致）。 */
export type ImportStep = 'select' | 'uploading' | 'result'

/** 导入阶段。 */
export type ImportPhase = 'idle' | 'uploading' | 'parsing' | 'done' | 'failed'

/** 中断信号（最小结构；与浏览器 `AbortSignal` 结构兼容，核心不依赖 DOM 类型）。 */
export interface ImportAbortSignal {
  /** 是否已请求中断。 */
  readonly aborted: boolean
}

/** 执行导入处理函数（宿主注入；`report` 回传上传进度、`signal` 用于中断）。 */
export type ImportExecuteHandler = (input: {
  biz: string
  file: unknown
  idempotencyKey: string
  report: UploadProgressReporter
  signal: ImportAbortSignal
}) => Promise<ImportResultInput | undefined>

/** 下载处理函数（模板 / 错误明细；返回取址参数或 `undefined`）。 */
export type ImportDownloadHandler = (input: {
  biz: string
  kind: 'template' | 'errors'
  params?: Record<string, unknown>
  idempotencyKey?: string
  filename: string
}) => Promise<DownloadRequest | undefined>

/** 导入下载请求参数（核心内部与件层共用）。 */
export interface ImportDownloadInput {
  /** 用途（模板 / 错误明细）。 */
  kind: 'template' | 'errors'
  /** 文件名。 */
  filename: string
  /** 模板参数（模板下载用）。 */
  params?: Record<string, unknown>
}

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface ImportJobs {
  /** 执行导入（multipart xlsx + `Idempotency-Key`）。 */
  execute?: ImportExecuteHandler
  /** 模板下载取址。 */
  downloadTemplate?: ImportDownloadHandler
  /** 错误明细下载取址。 */
  downloadErrors?: ImportDownloadHandler
}

/** 导入流能力基类（抽象）。 */
export abstract class BaseImportFlow extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'import-flow'
  /** 依赖能力键。 */
  override readonly depends = ['placeholder-state', 'upload-engine', 'file-download', 'access', 'notice']
  /** 业务标识（后端路径段，如 `users`）。 */
  biz = ''
  /** 业务中文名（标题与错误明细文件名）。 */
  bizName = ''
  /** 接受的文件类型（白名单）。 */
  accept: string = IMPORT_ACCEPT
  /** 文件大小上限（字节；0 表示不限）。 */
  maxSize: number = IMPORT_DEFAULT_MAX_SIZE
  /** 模板下载参数。 */
  templateParams: Record<string, unknown> | undefined
  /** 全部成功后是否自动关闭（件层消费）。 */
  successAutoClose = false
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false

  /**
   * 切换就绪态（就绪以 `touch` 刷新）。
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
  /** 当前步骤。 */
  step: ImportStep = 'select'
  /** 当前阶段。 */
  phase: ImportPhase = 'idle'
  /** 上传进度（0 ~ 100）。 */
  progress = 0
  /** 已选文件（透传给执行处理函数）。 */
  file: unknown | undefined
  /** 已选文件元信息。 */
  fileMeta: ImportFileMeta | undefined
  /** 文件校验失败文案。 */
  fileError = ''
  /** 幂等键（内容派生；选定合法文件时生成）。 */
  idempotencyKey = ''
  /** 导入结果。 */
  result: ImportResult | undefined
  /** 失败文案。 */
  errorMessage = ''
  /** 错误行当前页码。 */
  errorPage = 1
  /** 错误行每页行数。 */
  errorPageSize: number = IMPORT_ERROR_PAGE_SIZE
  /** 宿主注入的处理函数集。 */
  jobs: ImportJobs = {}
  /** 上传引擎（组合；进度与取消由其承载）。 */
  engine: BaseUploadEngine<unknown> | undefined
  /** 下载触发（组合；模板与错误明细下载经其触发）。 */
  download: BaseFileDownload | undefined
  /** 权限上下文（未注入不校验）。 */
  access: BaseAccess | undefined
  /** 提示通知（未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 当前中断信号（提交时重建）。 */
  #signal: { aborted: boolean } | undefined


  /** 是否进行中（上传 / 解析）。 */
  get busy(): boolean {
    return this.phase === 'uploading' || this.phase === 'parsing'
  }

  /** 是否可提交导入（就绪 ∧ 有权 ∧ 非进行中）。 */
  get canImport(): boolean {
    return this.ready && !this.busy && this.isAllowed(IMPORT_PERM)
  }

  /** 错误行总页数（至少 1）。 */
  get errorPageCount(): number {
    return this.errorPageView.pageCount
  }

  /** 当前页错误行。 */
  get errorRows(): ImportErrorRow[] {
    return this.errorPageView.rows
  }

  /** 是否触发展示上限截断。 */
  get errorTruncated(): boolean {
    return this.errorPageView.truncated
  }

  /** 结果汇总态。 */
  get summary(): ImportSummaryState {
    return resolveImportSummary(this.result ?? normalizeImportResult(undefined))
  }

  /** 当前错误行分页视图。 */
  private get errorPageView(): ReturnType<typeof paginateImportErrors> {
    return paginateImportErrors(this.result?.errors ?? [], this.errorPage, this.errorPageSize)
  }


  /**
   * 设置业务标识与中文名。
   *
   * @param biz 业务标识（后端路径段）。
   * @param bizName 业务中文名（缺省用业务标识）。
   */
  setBiz(biz: string, bizName?: string): void {
    this.biz = biz
    this.bizName = bizName ?? biz
    this.touch()
  }

  /**
   * 选择文件并做类型 / 大小 / 空文件校验。
   *
   * 合法则生成内容派生幂等键；不合法则清空文件与幂等键并返回 `false`。
   *
   * @param file 文件对象（透传执行处理函数）。
   * @param meta 文件元信息（校验与幂等键输入）。
   * @returns 是否通过校验。
   */
  selectFile(file: unknown, meta: ImportFileMeta): boolean {
    const check = checkImportFile(meta, { accept: this.accept, maxSize: this.maxSize })
    this.fileMeta = meta
    this.fileError = check.message
    this.result = undefined
    this.errorMessage = ''
    this.errorPage = 1
    this.phase = 'idle'
    this.step = 'select'
    if (!check.valid) {
      this.file = undefined
      this.idempotencyKey = ''
      this.touch()
      return false
    }
    this.file = file
    this.idempotencyKey = deriveImportKey(this.biz, meta)
    this.touch()
    return true
  }

  /** 清空已选文件与幂等键（新一次导入）。 */
  clearFile(): void {
    this.file = undefined
    this.fileMeta = undefined
    this.fileError = ''
    this.idempotencyKey = ''
    this.progress = 0
    this.phase = 'idle'
    this.touch()
  }

  /**
   * 切换错误行页码（夹取到有效范围）。
   *
   * @param page 目标页码。
   */
  setErrorPage(page: number): void {
    this.errorPage = page
    this.touch()
  }

  /**
   * 提交导入（执行处理函数未注入即占位不动作）。
   *
   * @returns 导入结果；占位 / 未选文件 / 未就绪 / 进行中 / 取消时返回 `undefined`。
   */
  async submit(): Promise<ImportResult | undefined> {
    if (!this.canImport || this.file === undefined || this.fileError !== '') {
      return undefined
    }
    const handler = this.jobs.execute
    if (handler === undefined) {
      this.errorMessage = IMPORT_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    const signal = { aborted: false }
    this.#signal = signal
    this.phase = 'uploading'
    this.progress = 0
    this.errorMessage = ''
    this.errorPage = 1
    this.requestCount += 1
    this.touch()

    let raw: ImportResultInput | undefined
    const report = (percent: number): void => {
      this.progress = clampPercent(percent)
      if (this.progress >= 100) {
        this.phase = 'parsing'
      }
      this.touch()
    }
    const run = async (file: unknown, uploadReport: UploadProgressReporter): Promise<string> => {
      raw = await handler({
        biz: this.biz,
        file,
        idempotencyKey: this.idempotencyKey,
        signal,
        report: (percent) => {
          report(percent)
          uploadReport(percent)
        },
      })
      return ''
    }

    try {
      const engine = this.engine
      if (engine !== undefined) {
        engine.abort = () => {
          signal.aborted = true
        }
        engine.uploader = run
        const uploaded = await engine.upload(this.file)
        this.progress = engine.progress
        if (uploaded === undefined && engine.canceled) {
          this.phase = 'idle'
          this.progress = 0
          this.touch()
          return undefined
        }
      } else {
        await run(this.file, report)
      }
      if (signal.aborted) {
        this.phase = 'idle'
        this.progress = 0
        this.touch()
        return undefined
      }
      const result = normalizeImportResult(raw)
      this.result = result
      this.step = 'result'
      this.phase = 'done'
      this.progress = 100
      if (this.notice !== undefined) {
        this.notice.enqueue(
          resolveImportSummary(result) === 'warning'
            ? `导入完成：成功 ${result.successCount} 行，失败 ${result.failCount} 行`
            : '导入完成',
          resolveImportSummary(result) === 'warning' ? 'warning' : 'success',
        )
      }
      this.touch()
      return result
    } catch (error) {
      if (signal.aborted) {
        this.phase = 'idle'
        this.progress = 0
        this.touch()
        return undefined
      }
      this.phase = 'failed'
      this.errorMessage = error instanceof Error && error.message !== '' ? error.message : '导入失败'
      if (this.notice !== undefined) {
        this.notice.enqueue(this.errorMessage, 'error')
      }
      this.touch()
      return undefined
    }
  }

  /** 取消导入（中断在途请求并复位阶段与进度）。 */
  cancel(): void {
    if (this.#signal !== undefined) {
      this.#signal.aborted = true
    }
    this.engine?.cancel()
    if (this.busy) {
      this.phase = 'idle'
      this.progress = 0
      this.touch()
    }
  }

  /**
   * 重试上一次失败导入（**复用同一幂等键**）。
   *
   * @returns 导入结果；非失败态时返回 `undefined`。
   */
  async retry(): Promise<ImportResult | undefined> {
    if (this.phase !== 'failed') {
      return undefined
    }
    return this.submit()
  }

  /** 重新导入（回选文件步并整体重置，新一次导入）。 */
  reset(): void {
    this.file = undefined
    this.fileMeta = undefined
    this.fileError = ''
    this.idempotencyKey = ''
    this.result = undefined
    this.errorMessage = ''
    this.errorPage = 1
    this.progress = 0
    this.phase = 'idle'
    this.step = 'select'
    this.#signal = undefined
    this.touch()
  }

  /**
   * 下载导入模板。
   *
   * @returns 下载结果；未就绪 / 未注入下载通路时返回 `undefined`。
   */
  async downloadTemplate(): Promise<DownloadResult | undefined> {
    const filename = templateFileName(this.bizName === '' ? this.biz : this.bizName)
    return this.runDownload({ kind: 'template', filename, params: this.templateParams })
  }

  /**
   * 下载错误明细（由后端按首次结果生成 xlsx）。
   *
   * @returns 下载结果；未就绪 / 未注入下载通路时返回 `undefined`。
   */
  async downloadErrors(): Promise<DownloadResult | undefined> {
    const filename = errorReportFileName(this.bizName === '' ? this.biz : this.bizName, new Date())
    return this.runDownload({ kind: 'errors', filename })
  }

  /**
   * 是否具备某权限码（权限上下文未注入或权限码为空时视为有权）。
   *
   * @param perm 权限码。
   * @returns 是否具备。
   */
  isAllowed(perm: string): boolean {
    if (perm === '' || this.access === undefined) {
      return true
    }
    return this.access.has(perm)
  }

  /**
   * 执行下载（注入处理函数优先取址；未注入经下载基类；皆无则占位不动作）。
   *
   * @param input 下载请求参数。
   */
  private async runDownload(input: ImportDownloadInput): Promise<DownloadResult | undefined> {
    if (!this.ready) {
      return undefined
    }
    const download = this.download
    const handler = input.kind === 'template' ? this.jobs.downloadTemplate : this.jobs.downloadErrors
    if (download === undefined && handler === undefined) {
      this.errorMessage = IMPORT_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    const request =
      handler === undefined
        ? { biz: this.biz, kind: input.kind, filename: input.filename }
        : await handler({
            biz: this.biz,
            kind: input.kind,
            params: input.params,
            idempotencyKey: input.kind === 'errors' ? this.idempotencyKey : undefined,
            filename: input.filename,
          })
    if (request === undefined) {
      this.errorMessage = IMPORT_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    if (download === undefined) {
      return { url: request.url ?? '', filename: request.filename ?? input.filename }
    }
    return download.download({ ...request, filename: request.filename ?? input.filename })
  }

  /** 通知变更（已释放时跳过）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/**
 * 进度夹取（0 ~ 100 整数；非法值回落 0）。
 *
 * @param percent 原始进度。
 * @returns 夹取后的进度。
 */
function clampPercent(percent: number): number {
  if (!Number.isFinite(percent)) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round(percent)))
}
