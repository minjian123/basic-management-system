/**
 * 上传引擎能力基类：分片 / 秒传 / 断点续传 / 进度回传 / 取消中断 / 并发控制 / 失败重试。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseUploadEngine → 文件上传族`。
 * 上传通路经注入式 `UploadTransportAdapter`（未注入即占位零请求）；预签名经注入的 `BasePresignedUrl`；
 * 核心不触 DOM、不请求、不切片（切片与浏览器能力归通路实现 / 各端 `utils/`）。
 *
 * **既有路径保持**：`uploader` / `upload` / `abort` / `cancel` / `progress` / `chunkSize` / `maxSize`
 * 逐字兼容（`08_05` 导入流复用：进度回传、取消不视为失败、进度复位）。
 */

import {
  FILE_MAX_SIZE,
  FILE_PART_CONCURRENCY,
  FILE_PART_SIZE,
  FILE_PLACEHOLDER_TEXT,
  FILE_RETRY_MAX,
  FILE_TASK_CONCURRENCY,
  FILE_WHOLE_MAX_SIZE,
  decideUploadMode,
  isFileErrorCode,
  mergePartProgress,
  missingParts,
  normalizeDedupRef,
  normalizeStoredFile,
  normalizeUploadSession,
  planParts,
  resolveFileErrorText,
  retryDelayMs,
  type FileMeta,
  type FileRef,
  type UploadPartPlan,
  type UploadTaskSnapshot,
} from '../domain/file'
import { BasePlaceholderState } from './placeholder-state'
import type { BasePresignedUrl } from './presigned-url'
import type { UploadTransportAdapter } from './upload-transport'

/** 上传进度回传（0 ~ 100）。 */
export type UploadProgressReporter = (percent: number) => void

/** 上传器（宿主注入；返回对象键；`report` 回传可量化进度）。 */
export type Uploader<TFile> = (file: TFile, report: UploadProgressReporter) => Promise<string>

/** 引擎任务入参。 */
export interface UploadEnqueueInput<TFile = unknown> {
  /** 文件对象（透传通路）。 */
  file: TFile
  /** 文件元信息（校验与编排输入）。 */
  meta: FileMeta
  /** 目标对象键（缺省由通路实现生成）。 */
  key?: string
}

/** 引擎配置入参。 */
export interface UploadEngineConfig {
  /** 分片大小（字节）。 */
  chunkSize?: number
  /** 整包阈值（字节）。 */
  wholeMaxSize?: number
  /** 单文件上限（字节）。 */
  maxFileSize?: number
  /** 分片大小（字节，别名）。 */
  partSize?: number
  /** 分片并发。 */
  concurrency?: number
  /** 多文件并发。 */
  fileConcurrency?: number
  /** 分片重试上限。 */
  retryMax?: number
  /** 秒传开关。 */
  autoDedup?: boolean
}

/** 引擎内部任务（快照 + 运行态）。 */
interface EngineTask<TFile> {
  /** 任务标识。 */
  id: string
  /** 文件对象。 */
  file: TFile
  /** 文件元信息。 */
  meta: FileMeta
  /** 目标对象键（可选）。 */
  key: string | undefined
  /** 任务快照（对外）。 */
  snapshot: UploadTaskSnapshot
  /** 中断信号。 */
  signal: { aborted: boolean }
  /** 当前会话（断点续传复用）。 */
  session: { uploadId: string; partSize: number; totalParts: number } | undefined
  /** 已传分片序号。 */
  uploadedParts: number[]
  /** 已传字节数。 */
  doneBytes: number
}

/**
 * 进度夹取（0 ~ 100 整数；非法值回落 0）。
 *
 * @param percent 原始进度。
 * @returns 夹取后的进度。
 */
function clampProgress(percent: number): number {
  if (!Number.isFinite(percent)) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round(percent)))
}

/**
 * 延时等待（重试退避）。
 *
 * @param ms 毫秒。
 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

/**
 * 读取哈希结果（兼容裸串 / `{ sha256 }`）。
 *
 * @param raw 原始结果。
 * @returns SHA-256；不可用返回 `undefined`。
 */
function readSha256(raw: unknown): string | undefined {
  if (typeof raw === 'string' && raw !== '') {
    return raw
  }
  if (raw !== null && typeof raw === 'object') {
    const value = (raw as Record<string, unknown>).sha256
    if (typeof value === 'string' && value !== '') {
      return value
    }
  }
  return undefined
}

/**
 * 读取已传分片（兼容数组 / `{ parts }` / `{ uploaded_parts }`）。
 *
 * @param raw 原始结果。
 * @param fallback 回落值。
 * @returns 已传分片序号。
 */
function readUploadedParts(raw: unknown, fallback: readonly number[]): number[] {
  const list = Array.isArray(raw)
    ? raw
    : raw !== null && typeof raw === 'object'
      ? ((raw as Record<string, unknown>).parts ?? (raw as Record<string, unknown>).uploaded_parts ?? (raw as Record<string, unknown>).uploadedParts)
      : undefined
  if (!Array.isArray(list)) {
    return [...fallback]
  }
  const parts: number[] = []
  for (const entry of list) {
    const value = entry !== null && typeof entry === 'object' ? (entry as Record<string, unknown>).part_no ?? (entry as Record<string, unknown>).partNo : entry
    const partNo = Number(value)
    if (Number.isFinite(partNo) && partNo >= 1 && !parts.includes(partNo)) {
      parts.push(partNo)
    }
  }
  return parts
}

/**
 * 读取错误码（兼容 `code` / `errorCode`）。
 *
 * @param error 原始错误。
 * @returns 错误码或 `undefined`。
 */
function readErrorCode(error: unknown): number | undefined {
  if (error !== null && typeof error === 'object') {
    const raw = error as { code?: unknown; errorCode?: unknown }
    const code = typeof raw.code === 'number' ? raw.code : raw.errorCode
    if (typeof code === 'number' && Number.isFinite(code)) {
      return code
    }
  }
  return undefined
}

/** 上传引擎能力基类（抽象）。 */
export abstract class BaseUploadEngine<TFile = unknown> extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'upload-engine'
  /** 依赖能力键（占位语义 + 预签名）。 */
  override readonly depends = ['placeholder-state', 'presigned-url']
  /** 分片大小（字节；既有字段，保留兼容）。 */
  chunkSize = 5 * 1024 * 1024
  /** 单文件大小上限（字节；既有字段，0 表示不限）。 */
  maxSize = 0
  /** 上传进度（0 ~ 100；既有字段，单文件路径）。 */
  progress = 0
  /** 上传器（未注入则占位不请求；既有字段）。 */
  uploader: Uploader<TFile> | undefined
  /** 中断钩子（宿主注入；`cancel()` 时调用，用于中断在途请求）。 */
  abort: (() => void) | undefined
  /** 数据通路是否就绪（占位语义，缺省未就绪）。 */
  ready = false
  /** 整包阈值（字节，超限转分片）。 */
  wholeMaxSize: number = FILE_WHOLE_MAX_SIZE
  /** 单文件上限（字节，0 表示不限）。 */
  maxFileSize: number = FILE_MAX_SIZE
  /** 缺省分片大小（字节，会话返回 `part_size` 覆盖）。 */
  partSize: number = FILE_PART_SIZE
  /** 分片并发数。 */
  concurrency: number = FILE_PART_CONCURRENCY
  /** 多文件并发数。 */
  fileConcurrency: number = FILE_TASK_CONCURRENCY
  /** 分片失败重试上限。 */
  retryMax: number = FILE_RETRY_MAX
  /** 秒传开关（关闭即跳过哈希与判定）。 */
  autoDedup = true
  /** 上传通路（注入式；未注入即占位零请求）。 */
  transport: UploadTransportAdapter | undefined
  /** 预签名能力（注入引用）。 */
  presigned: BasePresignedUrl | undefined
  /** 错误码（任务外错误，如未就绪）。 */
  errorCode: number | undefined
  /** 错误文案（任务外错误）。 */
  errorMessage = ''
  /** 任务快照（队列 / 在途 / 完成；与内部任务同引用）。 */
  readonly tasks: UploadTaskSnapshot[] = []
  /** 是否已被取消（既有单文件路径在途状态）。 */
  private canceledFlag = false
  /** 任务表。 */
  private readonly queue = new Map<string, EngineTask<TFile>>()
  /** 任务序号。 */
  private seq = 0

  /** 是否处于已取消状态（在途请求已请求中断）。 */
  get canceled(): boolean {
    return this.canceledFlag
  }

  /** 是否有在途任务。 */
  get busy(): boolean {
    return this.tasks.some((task) => task.phase === 'pending' || task.phase === 'hashing' || task.phase === 'uploading' || task.phase === 'merging')
  }

  /** 是否可上传（就绪 ∧ 通路注入）。 */
  get canUpload(): boolean {
    return this.ready && this.transport !== undefined
  }

  /** 多任务聚合进度（按体积加权；无任务为 0）。 */
  get totalPercent(): number {
    let total = 0
    let done = 0
    for (const task of this.tasks) {
      total += task.size
      done += (task.size * task.percent) / 100
    }
    if (total <= 0) {
      return 0
    }
    return Math.min(100, Math.max(0, Math.round((done / total) * 100)))
  }

  /** 已完成任务数。 */
  get doneCount(): number {
    return this.tasks.filter((task) => task.phase === 'done').length
  }

  /** 失败任务数。 */
  get failedCount(): number {
    return this.tasks.filter((task) => task.phase === 'failed').length
  }

  /**
   * 注入 / 移除上传通路（移除即回落占位零请求）。
   *
   * @param transport 通路适配器；`undefined` 表示移除。
   */
  setTransport(transport: UploadTransportAdapter | undefined): void {
    this.transport = transport
    this.touch()
  }

  /**
   * 注入 / 移除预签名能力。
   *
   * @param presigned 预签名实例；`undefined` 表示移除。
   */
  setPresigned(presigned: BasePresignedUrl | undefined): void {
    this.presigned = presigned
    this.touch()
  }

  /**
   * 配置引擎（缺省项不改）。
   *
   * @param input 配置入参。
   */
  setConfig(input: UploadEngineConfig): void {
    if (input.chunkSize !== undefined) {
      this.chunkSize = input.chunkSize
    }
    if (input.wholeMaxSize !== undefined) {
      this.wholeMaxSize = input.wholeMaxSize
    }
    if (input.maxFileSize !== undefined) {
      this.maxFileSize = input.maxFileSize
    }
    if (input.partSize !== undefined) {
      this.partSize = input.partSize
    }
    if (input.concurrency !== undefined) {
      this.concurrency = Math.max(1, Math.floor(input.concurrency))
    }
    if (input.fileConcurrency !== undefined) {
      this.fileConcurrency = Math.max(1, Math.floor(input.fileConcurrency))
    }
    if (input.retryMax !== undefined) {
      this.retryMax = Math.max(0, Math.floor(input.retryMax))
    }
    if (input.autoDedup !== undefined) {
      this.autoDedup = input.autoDedup
    }
    this.touch()
  }

  /**
   * 上传文件（既有单文件路径；未注入上传器则占位返回 `undefined`）。
   *
   * 进度经 `report` 回传并夹取到 0 ~ 100；失败向上抛错（**保留当前进度**，不置满）；
   * 取消后以 `undefined` 结束且不再更新进度。
   *
   * @param file 文件。
   * @returns 对象键；取消或占位时返回 `undefined`。
   */
  async upload(file: TFile): Promise<string | undefined> {
    if (this.uploader === undefined) {
      return undefined
    }
    this.canceledFlag = false
    this.progress = 0
    this.touch()
    const key = await this.uploader(file, (percent) => {
      if (this.canceledFlag) {
        return
      }
      this.progress = clampProgress(percent)
      this.touch()
    })
    if (this.canceledFlag) {
      return undefined
    }
    this.progress = 100
    this.touch()
    return key
  }

  /**
   * 入队上传任务（占位 / 未就绪返回 `undefined` 且零请求）。
   *
   * @param input 任务入参。
   * @returns 任务标识；占位 / 非法时返回 `undefined`。
   */
  enqueue(input: UploadEnqueueInput<TFile>): string | undefined {
    if (!this.canUpload) {
      this.errorCode = undefined
      this.errorMessage = FILE_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    if (!Number.isFinite(input.meta.size) || input.meta.size <= 0) {
      this.errorCode = 50102
      this.errorMessage = resolveFileErrorText(50102)
      this.touch()
      return undefined
    }
    if (this.maxFileSize > 0 && input.meta.size > this.maxFileSize) {
      this.errorCode = 50102
      this.errorMessage = resolveFileErrorText(50102)
      this.touch()
      return undefined
    }
    this.seq += 1
    const id = `upload-${this.seq}`
    const snapshot: UploadTaskSnapshot = {
      id,
      name: input.meta.name,
      size: input.meta.size,
      phase: 'pending',
      percent: 0,
      errorMessage: '',
      attempts: 0,
    }
    this.queue.set(id, {
      id,
      file: input.file,
      meta: { ...input.meta },
      key: input.key,
      snapshot,
      signal: { aborted: false },
      session: undefined,
      uploadedParts: [],
      doneBytes: 0,
    })
    this.tasks.push(snapshot)
    this.errorCode = undefined
    this.errorMessage = ''
    this.touch()
    return id
  }

  /**
   * 启动任务（缺省启动全部待启动任务；多文件并发受控）。
   *
   * @param taskId 任务标识（可选）。
   */
  async start(taskId?: string): Promise<void> {
    if (taskId !== undefined) {
      const task = this.queue.get(taskId)
      if (task === undefined || task.snapshot.phase !== 'pending') {
        return
      }
      await this.runTask(task, false)
      return
    }
    const pending = [...this.queue.values()].filter((task) => task.snapshot.phase === 'pending')
    if (pending.length === 0) {
      return
    }
    const limit = Math.max(1, Math.min(this.fileConcurrency, pending.length))
    let cursor = 0
    const worker = async (): Promise<void> => {
      while (cursor < pending.length) {
        const task = pending[cursor] as EngineTask<TFile>
        cursor += 1
        if (task.snapshot.phase !== 'pending') {
          continue
        }
        await this.runTask(task, false)
      }
    }
    await Promise.all(Array.from({ length: limit }, () => worker()))
  }

  /**
   * 重试失败任务（断点续传：已传分片不重传）。
   *
   * @param taskId 任务标识。
   */
  async retry(taskId: string): Promise<void> {
    const task = this.queue.get(taskId)
    if (task === undefined || task.snapshot.phase !== 'failed') {
      return
    }
    task.snapshot.phase = 'pending'
    task.snapshot.percent = 0
    task.snapshot.errorCode = undefined
    task.snapshot.errorMessage = ''
    this.touch()
    await this.runTask(task, true)
  }

  /**
   * 取消上传（无参 = 既有单文件语义 + 取消全部任务；带参取消单任务）。
   *
   * @param taskId 任务标识（可选）。
   */
  cancel(taskId?: string): void {
    if (taskId === undefined) {
      this.canceledFlag = true
      this.abort?.()
      this.progress = 0
      for (const task of this.queue.values()) {
        this.cancelTask(task)
      }
      this.touch()
      return
    }
    const task = this.queue.get(taskId)
    if (task !== undefined) {
      this.cancelTask(task)
    }
  }

  /**
   * 移除任务（在途任务先取消）。
   *
   * @param taskId 任务标识。
   */
  remove(taskId: string): void {
    const task = this.queue.get(taskId)
    if (task === undefined) {
      return
    }
    this.cancelTask(task)
    this.queue.delete(taskId)
    const index = this.tasks.indexOf(task.snapshot)
    if (index >= 0) {
      this.tasks.splice(index, 1)
    }
    this.touch()
  }

  /**
   * 取任务快照。
   *
   * @param taskId 任务标识。
   * @returns 任务快照；未命中 `undefined`。
   */
  taskOf(taskId: string): UploadTaskSnapshot | undefined {
    return this.queue.get(taskId)?.snapshot
  }

  /** 重置（取消在途并清空任务与错误；保留配置与注入）。 */
  reset(): void {
    this.cancel()
    this.queue.clear()
    this.tasks.splice(0, this.tasks.length)
    this.errorCode = undefined
    this.errorMessage = ''
    this.progress = 0
    this.canceledFlag = false
    this.touch()
  }

  /** 释放（取消在途任务后释放基类资源）。 */
  override dispose(): void {
    this.cancel()
    this.queue.clear()
    this.tasks.splice(0, this.tasks.length)
    super.dispose()
  }

  /**
   * 运行任务（整链路：秒传 → 整包 / 分片 → 合并）。
   *
   * @param task 内部任务。
   * @param resume 是否续传（复用会话与已传分片）。
   */
  private async runTask(task: EngineTask<TFile>, resume: boolean): Promise<void> {
    const snapshot = task.snapshot
    const transport = this.transport
    if (!this.canUpload || transport === undefined) {
      this.failTask(task, undefined, FILE_PLACEHOLDER_TEXT)
      return
    }
    try {
      if (task.signal.aborted) {
        this.cancelTask(task)
        return
      }
      let sha256: string | undefined
      if (!resume) {
        if (this.autoDedup && transport.check !== undefined) {
          snapshot.phase = 'hashing'
          snapshot.percent = 0
          this.touch()
          if (transport.hash !== undefined) {
            this.markLoaded()
            sha256 = readSha256(await transport.hash({ file: task.file, partSize: this.partSize, signal: task.signal }))
          }
          if (task.signal.aborted) {
            this.cancelTask(task)
            return
          }
          if (sha256 !== undefined) {
            this.markLoaded()
            const ref = normalizeDedupRef(await transport.check({ sha256, size: task.meta.size }))
            if (ref !== undefined) {
              snapshot.mode = 'whole'
              this.finishTask(task, ref)
              return
            }
          }
        }
        if (task.signal.aborted) {
          this.cancelTask(task)
          return
        }
        const mode = decideUploadMode(task.meta.size, this.wholeMaxSize)
        snapshot.mode = mode
        if (mode === 'whole' && transport.uploadWhole !== undefined) {
          snapshot.phase = 'uploading'
          this.markLoaded()
          const raw = await transport.uploadWhole({
            file: task.file,
            key: task.key,
            name: task.meta.name,
            size: task.meta.size,
            mime: task.meta.mime,
            sha256,
            report: (percent) => {
              if (task.signal.aborted) {
                return
              }
              snapshot.percent = clampProgress(percent)
              this.touch()
            },
            signal: task.signal,
          })
          if (task.signal.aborted) {
            this.cancelTask(task)
            return
          }
          const stored = normalizeStoredFile(raw)
          if (stored === undefined) {
            this.failTask(task, 50104, resolveFileErrorText(50104))
            return
          }
          this.finishTask(task, stored)
          return
        }
      }
      // 分片路径（含续传）
      const initiate = transport.initiate
      const uploadPart = transport.uploadPart
      const complete = transport.complete
      if (initiate === undefined || uploadPart === undefined || complete === undefined) {
        this.failTask(task, undefined, FILE_PLACEHOLDER_TEXT)
        return
      }
      let session = task.session
      if (session === undefined) {
        snapshot.phase = 'uploading'
        this.markLoaded()
        const raw = await initiate({
          key: task.key,
          name: task.meta.name,
          size: task.meta.size,
          mime: task.meta.mime,
          sha256,
          partSize: this.partSize,
        })
        const normalized = normalizeUploadSession(raw)
        if (normalized.uploadId === '') {
          this.failTask(task, 50104, resolveFileErrorText(50104))
          return
        }
        session = { uploadId: normalized.uploadId, partSize: normalized.partSize, totalParts: normalized.totalParts }
        task.session = session
        task.uploadedParts = [...normalized.uploadedParts]
      }
      if (transport.listParts !== undefined) {
        this.markLoaded()
        task.uploadedParts = readUploadedParts(await transport.listParts({ uploadId: session.uploadId }), task.uploadedParts)
      }
      const plans = planParts(task.meta.size, session.partSize)
      const totalParts = session.totalParts > 0 ? session.totalParts : plans.length
      const done = new Set(task.uploadedParts)
      task.doneBytes = plans.reduce((sum, part) => (done.has(part.partNo) ? sum + part.size : sum), 0)
      snapshot.percent = mergePartProgress(task.doneBytes, task.meta.size)
      snapshot.phase = 'uploading'
      this.touch()
      const todo = missingParts([...done], totalParts)
      let cursor = 0
      const worker = async (): Promise<void> => {
        while (cursor < todo.length) {
          const partNo = todo[cursor] as number
          cursor += 1
          if (task.signal.aborted) {
            return
          }
          const plan = plans[partNo - 1]
          if (plan === undefined) {
            continue
          }
          await this.runPart(task, session as { uploadId: string }, plan, done)
        }
      }
      await Promise.all(Array.from({ length: Math.max(1, Math.min(this.concurrency, todo.length)) }, () => worker()))
      if (task.signal.aborted) {
        this.cancelTask(task)
        return
      }
      snapshot.phase = 'merging'
      this.touch()
      this.markLoaded()
      const rawStored = await complete({ uploadId: session.uploadId })
      if (task.signal.aborted) {
        this.cancelTask(task)
        return
      }
      const stored = normalizeStoredFile(rawStored)
      if (stored === undefined) {
        this.failTask(task, 50104, resolveFileErrorText(50104))
        return
      }
      this.finishTask(task, stored)
    } catch (error) {
      if (task.signal.aborted) {
        this.cancelTask(task)
        return
      }
      const code = readErrorCode(error)
      this.reportError(error, { scope: 'BaseUploadEngine.runTask' })
      this.failTask(task, code, isFileErrorCode(code) ? resolveFileErrorText(code) : resolveFileErrorText(undefined))
    }
  }

  /**
   * 上传单个分片（含指数退避重试）。
   *
   * @param task 内部任务。
   * @param session 会话。
   * @param plan 分片计划。
   * @param done 已传分片集合（原地更新）。
   */
  private async runPart(task: EngineTask<TFile>, session: { uploadId: string }, plan: UploadPartPlan, done: Set<number>): Promise<void> {
    const transport = this.transport
    const uploadPart = transport?.uploadPart
    if (transport === undefined || uploadPart === undefined) {
      return
    }
    let attempt = 0
    for (;;) {
      if (task.signal.aborted) {
        return
      }
      attempt += 1
      task.snapshot.attempts += 1
      this.markLoaded()
      try {
        await uploadPart.call(transport, {
          uploadId: session.uploadId,
          partNo: plan.partNo,
          file: task.file,
          start: plan.start,
          end: plan.end,
          signal: task.signal,
        })
        if (task.signal.aborted) {
          return
        }
        if (!done.has(plan.partNo)) {
          done.add(plan.partNo)
          task.uploadedParts.push(plan.partNo)
          task.doneBytes += plan.size
        }
        task.snapshot.percent = mergePartProgress(task.doneBytes, task.meta.size)
        this.touch()
        return
      } catch (error) {
        if (task.signal.aborted) {
          return
        }
        if (attempt > this.retryMax) {
          throw error
        }
        await delay(retryDelayMs(attempt))
      }
    }
  }

  /**
   * 取消任务（置取消态、置信号、调通路取消、进度复位；不视为失败）。
   *
   * @param task 内部任务。
   */
  private cancelTask(task: EngineTask<TFile>): void {
    const phase = task.snapshot.phase
    if (phase === 'done' || phase === 'failed' || phase === 'canceled') {
      return
    }
    task.signal.aborted = true
    task.snapshot.phase = 'canceled'
    task.snapshot.percent = 0
    const abort = this.transport?.abort
    const session = task.session
    if (abort !== undefined && session !== undefined) {
      try {
        void abort.call(this.transport, { uploadId: session.uploadId })
      } catch {
        // 取消失败不阻断（会话清理由后端幂等兜底）
      }
    }
    this.touch()
  }

  /**
   * 完成任务。
   *
   * @param task 内部任务。
   * @param ref 文件引用。
   */
  private finishTask(task: EngineTask<TFile>, ref: FileRef): void {
    task.snapshot.phase = 'done'
    task.snapshot.percent = 100
    task.snapshot.fileId = ref.id
    task.snapshot.errorCode = undefined
    task.snapshot.errorMessage = ''
    this.touch()
  }

  /**
   * 失败任务。
   *
   * @param task 内部任务。
   * @param code 错误码（可选）。
   * @param message 错误文案。
   */
  private failTask(task: EngineTask<TFile>, code: number | undefined, message: string): void {
    task.snapshot.phase = 'failed'
    task.snapshot.errorCode = code
    task.snapshot.errorMessage = message
    this.errorCode = code
    this.errorMessage = message
    this.touch()
  }

  /** 通知变更（已释放时跳过）。 */
  private touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
