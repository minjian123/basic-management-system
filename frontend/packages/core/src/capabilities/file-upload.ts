/**
 * 文件上传族组件基类 `BaseFileUpload`：文件列表 / 类型与大小数量校验 / 多选上限 / 多图排序 /
 * 进度与任务快照 / 只读回显与失效占位 / 预览与下载（组合上传引擎、预签名与下载触发）。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseValue → BaseField → BaseInput → BaseFileUpload → 具体件`。
 * 数据通路经注入式 `UploadTransportAdapter` 与组合的 `BaseUploadEngine`（未注入即占位零请求）；
 * 受控值为文件标识（单值 / 数组），在途上传以本地占位引用展示、不进入受控值；
 * 核心不触 DOM、不请求、不切片（浏览器能力归各端 `utils/`）。
 */

import {
  FILE_EMPTY_TEXT,
  FILE_EMPTY_VALUE,
  FILE_LIMIT_DEFAULT,
  FILE_LIMIT_TEXT_PREFIX,
  FILE_MAX_SIZE,
  FILE_PLACEHOLDER_TEXT,
  FILE_WHOLE_MAX_SIZE,
  IMAGE_COMPRESS_MAX_EDGE,
  IMAGE_COMPRESS_MIN_SIZE,
  IMAGE_COMPRESS_QUALITY,
  IMAGE_CROP_ASPECT,
  applyFileSelection,
  checkFileMeta,
  checkImageDimension,
  fileListSummary,
  fileRefLabel,
  findFileRef,
  isFileRefInvalid,
  isLocalFileRef,
  localFileRefId,
  mergeFileRefs,
  moveFileRef,
  normalizeFileRefs,
  normalizeFileValue,
  removeFileRef,
  resolveFileErrorText,
  type FileCheckResult,
  type FileKind,
  type FileMeta,
  type FileRef,
  type ImageCheckOptions,
  type ImageCropShape,
  type UploadTaskSnapshot,
} from '../domain/file'
import { BaseInput } from './input'
import type { BaseFileDownload } from './file-download'
import type { BasePresignedUrl } from './presigned-url'
import type { BaseUploadEngine } from './upload-engine'
import type { UploadTransportAdapter } from './upload-transport'

/** 文件族装配选项（合并式；缺省项不改）。 */
export interface FileUploadOptions {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 文件形态。 */
  kind?: FileKind
  /** 是否多选。 */
  multiple?: boolean
  /** 数量上限（0 不限）。 */
  limit?: number
  /** 接受类型（扩展名 / MIME，逗号分隔）。 */
  accept?: string
  /** 单文件大小上限（字节）。 */
  maxSize?: number
  /** 整包阈值（字节）。 */
  wholeMaxSize?: number
  /** 分片大小（字节）。 */
  partSize?: number
  /** 分片并发。 */
  concurrency?: number
  /** 秒传开关。 */
  autoDedup?: boolean
  /** 图片压缩开关。 */
  compress?: boolean
  /** 图片裁剪开关。 */
  crop?: boolean
  /** 裁剪形态。 */
  cropShape?: ImageCropShape
  /** 裁剪比例。 */
  cropAspect?: number
  /** 图片尺寸与比例校验。 */
  imageOptions?: ImageCheckOptions
  /** 多文件排序开关。 */
  draggable?: boolean
  /** 只读回显。 */
  readonlyView?: boolean
  /** 上传通路。 */
  transport?: UploadTransportAdapter
  /** 上传引擎（缺省由投影内建）。 */
  engine?: BaseUploadEngine
  /** 预签名能力。 */
  presigned?: BasePresignedUrl
  /** 下载触发能力。 */
  download?: BaseFileDownload
}

/** 选择结果（件层提示用）。 */
export interface FileAcceptResult {
  /** 成功入队的引用（含本地占位）。 */
  added: FileRef[]
  /** 被拒条目。 */
  rejected: { meta: FileMeta; code: number; message: string }[]
}

/** 文件上传族组件基类（抽象）。 */
export abstract class BaseFileUpload extends BaseInput<string | string[]> {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'file-upload'
  /** 依赖登记。 */
  override readonly depends = ['input', 'upload-engine', 'presigned-url', 'file-download']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 文件形态。 */
  kind: FileKind = 'file'
  /** 是否多选。 */
  multiple = true
  /** 数量上限（0 不限）。 */
  limit: number = FILE_LIMIT_DEFAULT
  /** 接受类型（扩展名 / MIME，逗号分隔）。 */
  accept = ''
  /** 单文件大小上限（字节）。 */
  maxSize: number = FILE_MAX_SIZE
  /** 整包阈值（字节）。 */
  wholeMaxSize: number = FILE_WHOLE_MAX_SIZE
  /** 图片压缩开关。 */
  compress = true
  /** 图片裁剪开关。 */
  crop = false
  /** 裁剪形态。 */
  cropShape: ImageCropShape = 'rect'
  /** 裁剪比例。 */
  cropAspect: number = IMAGE_CROP_ASPECT
  /** 图片压缩最大边长（像素）。 */
  compressMaxEdge: number = IMAGE_COMPRESS_MAX_EDGE
  /** 图片压缩质量。 */
  compressQuality: number = IMAGE_COMPRESS_QUALITY
  /** 图片压缩触发体积（字节）。 */
  compressMinSize: number = IMAGE_COMPRESS_MIN_SIZE
  /** 图片尺寸与比例校验。 */
  imageOptions: ImageCheckOptions | undefined
  /** 多文件排序开关。 */
  draggable = false
  /** 只读回显。 */
  readonlyView = false
  /** 已选 / 已回显文件（常驻；在途上传为本地占位引用）。 */
  readonly refs: FileRef[] = []
  /** 上传任务快照（引擎任务面）。 */
  readonly tasks: UploadTaskSnapshot[] = []
  /** 多选超限标记。 */
  limitExceeded = false
  /** 校验 / 上传失败文案。 */
  fileError = ''
  /** 错误码。 */
  errorCode: number | undefined
  /** 错误文案。 */
  errorMessage = ''
  /** 上传通路（注入式；未注入即占位零请求）。 */
  transport: UploadTransportAdapter | undefined
  /** 上传引擎（组合）。 */
  engine: BaseUploadEngine | undefined
  /** 预签名能力（组合引用）。 */
  presigned: BasePresignedUrl | undefined
  /** 下载触发能力（组合引用）。 */
  download: BaseFileDownload | undefined
  /** 本地引用序号。 */
  private seq = 0
  /** 已解析文件标识（防重复批量请求）。 */
  private readonly resolved = new Set<string>()
  /** 任务 → 本地引用映射（完成后替换为服务端标识）。 */
  private readonly taskRefs = new Map<string, string>()
  /** 引擎生命周期取消函数。 */
  private offEngine: (() => void) | undefined

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 生效禁用（件级禁用 ∨ 占位）。 */
  get effectiveDisabled(): boolean {
    return this.disabled || !this.ready
  }

  /** 是否有在途任务。 */
  get busy(): boolean {
    return this.tasks.some((task) => task.phase === 'pending' || task.phase === 'hashing' || task.phase === 'uploading' || task.phase === 'merging')
  }

  /** 聚合进度（0 ~ 100）。 */
  get totalPercent(): number {
    return this.engine?.totalPercent ?? 0
  }

  /** 是否可上传（就绪 ∧ 引擎可上传）。 */
  get canUpload(): boolean {
    return this.ready && this.engine !== undefined && this.engine.canUpload
  }

  /** 是否还可新增（数量未达上限）。 */
  get canAddMore(): boolean {
    return this.limit <= 0 || this.refs.length < this.limit
  }

  /** 受控标识列表（不含本地占位）。 */
  get selectedIds(): string[] {
    return this.refs.filter((ref) => !isLocalFileRef(ref)).map((ref) => ref.id)
  }

  /** 失效引用。 */
  get invalidRefs(): FileRef[] {
    return this.refs.filter((ref) => isFileRefInvalid(ref))
  }

  /** 是否空态。 */
  get empty(): boolean {
    return this.refs.length === 0 && !this.busy
  }

  /** 数量上限提示文案（0 不限返回空串）。 */
  get limitText(): string {
    if (this.limit <= 0) {
      return ''
    }
    return `${FILE_LIMIT_TEXT_PREFIX} ${this.limit} 个`
  }

  /** 空态文案。 */
  get emptyText(): string {
    return FILE_EMPTY_TEXT
  }

  /**
   * 合并式装配（缺省项不改）。
   *
   * @param options 装配选项。
   */
  setOptions(options: FileUploadOptions): void {
    if (options.ready !== undefined) {
      this.setReady(options.ready)
    }
    if (options.kind !== undefined) {
      this.kind = options.kind
    }
    if (options.multiple !== undefined) {
      this.setMultiple(options.multiple)
    }
    if (options.limit !== undefined) {
      this.setLimit(options.limit)
    }
    if (options.accept !== undefined) {
      this.accept = options.accept
    }
    if (options.maxSize !== undefined) {
      this.maxSize = options.maxSize
    }
    if (options.wholeMaxSize !== undefined) {
      this.wholeMaxSize = options.wholeMaxSize
    }
    if (options.compress !== undefined) {
      this.compress = options.compress
    }
    if (options.crop !== undefined) {
      this.crop = options.crop
    }
    if (options.cropShape !== undefined) {
      this.cropShape = options.cropShape
    }
    if (options.cropAspect !== undefined) {
      this.cropAspect = options.cropAspect
    }
    if (options.imageOptions !== undefined) {
      this.imageOptions = options.imageOptions
    }
    if (options.draggable !== undefined) {
      this.draggable = options.draggable
    }
    if (options.readonlyView !== undefined) {
      this.readonlyView = options.readonlyView
    }
    if (options.engine !== undefined) {
      this.setEngine(options.engine)
    }
    if (options.transport !== undefined) {
      this.setTransport(options.transport)
    }
    if (options.presigned !== undefined) {
      this.setPresigned(options.presigned)
    }
    if (options.download !== undefined) {
      this.setDownload(options.download)
    }
    const config = {
      ...(options.partSize !== undefined ? { partSize: options.partSize } : {}),
      ...(options.concurrency !== undefined ? { concurrency: options.concurrency } : {}),
      ...(options.autoDedup !== undefined ? { autoDedup: options.autoDedup } : {}),
      ...(options.wholeMaxSize !== undefined ? { wholeMaxSize: options.wholeMaxSize } : {}),
      ...(options.maxSize !== undefined ? { maxFileSize: options.maxSize } : {}),
    }
    if (Object.keys(config).length > 0) {
      this.engine?.setConfig(config)
    }
    this.emitUpdate()
  }

  /**
   * 切换就绪态（同步引擎占位语义）。
   *
   * @param value 是否就绪。
   */
  override setReady(value: boolean): void {
    super.setReady(value)
    this.engine?.setReady(value)
  }

  /**
   * 注入 / 移除上传通路。
   *
   * @param transport 通路适配器；`undefined` 表示移除。
   */
  setTransport(transport: UploadTransportAdapter | undefined): void {
    this.transport = transport
    this.engine?.setTransport(transport)
    this.emitUpdate()
  }

  /**
   * 注入 / 替换上传引擎（订阅其任务面）。
   *
   * @param engine 引擎实例；`undefined` 表示移除。
   */
  setEngine(engine: BaseUploadEngine | undefined): void {
    this.offEngine?.()
    this.offEngine = undefined
    this.engine = engine
    if (engine !== undefined) {
      this.offEngine = engine.onLifecycle((event) => {
        if (event === 'update') {
          this.syncTasks()
        }
      })
    }
    this.syncTasks()
    this.emitUpdate()
  }

  /**
   * 注入 / 移除预签名能力。
   *
   * @param presigned 预签名实例；`undefined` 表示移除。
   */
  setPresigned(presigned: BasePresignedUrl | undefined): void {
    this.presigned = presigned
    this.emitUpdate()
  }

  /**
   * 注入 / 移除下载触发能力。
   *
   * @param download 下载触发实例；`undefined` 表示移除。
   */
  setDownload(download: BaseFileDownload | undefined): void {
    this.download = download
    this.emitUpdate()
  }

  /**
   * 设置多选（受控值按新口径归一）。
   *
   * @param value 是否多选。
   */
  setMultiple(value: boolean): void {
    this.multiple = value
    const ids = normalizeFileValue(this.value, value)
    super.setValue(value ? (ids.length > 0 ? ids : undefined) : ids[0])
    this.syncRefsFromValue()
    this.emitUpdate()
  }

  /**
   * 设置数量上限（非法回落 0 不限）。
   *
   * @param limit 上限。
   */
  setLimit(limit: number): void {
    this.limit = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : 0
    this.emitUpdate()
  }

  /**
   * 设置受控值（外部 / 受控绑定；归一为标识列表并同步引用占位）。
   *
   * @param value 受控值。
   */
  override setValue(value: string | string[] | undefined): void {
    const ids = normalizeFileValue(value, this.multiple)
    super.setValue(ids.length === 0 ? undefined : this.multiple ? ids : (ids[0] as string))
    this.syncRefsFromValue()
    this.emitUpdate()
  }

  /**
   * 接受文件（校验 → 上限截断 → 入队上传；未就绪 / 未注入通路零请求）。
   *
   * @param inputs 文件与元信息。
   * @returns 入队与被拒结果。
   */
  acceptFiles(inputs: readonly { file: unknown; meta: FileMeta }[]): FileAcceptResult {
    const rejected: { meta: FileMeta; code: number; message: string }[] = []
    const accepted: { file: unknown; meta: FileMeta; ref: FileRef }[] = []
    for (const input of inputs) {
      const check = this.checkMeta(input.meta)
      if (!check.valid) {
        rejected.push({ meta: input.meta, code: check.code ?? 50104, message: check.message })
        continue
      }
      this.seq += 1
      accepted.push({
        file: input.file,
        meta: input.meta,
        ref: {
          id: localFileRefId(this.seq),
          name: input.meta.name,
          size: input.meta.size,
          mime: input.meta.mime,
          ...(input.meta.dimension !== undefined ? { dimension: input.meta.dimension } : {}),
        },
      })
    }
    const selection = this.multiple
      ? applyFileSelection(this.refs, accepted.map((entry) => entry.ref), this.limit)
      : { refs: accepted.slice(-1).map((entry) => entry.ref), exceeded: accepted.length > 1 }
    const keptIds = new Set(selection.refs.map((ref) => ref.id))
    const kept = accepted.filter((entry) => keptIds.has(entry.ref.id))
    const dropped = accepted.filter((entry) => !keptIds.has(entry.ref.id))
    for (const entry of dropped) {
      rejected.push({ meta: entry.meta, code: 50103, message: resolveFileErrorText(50103) })
    }
    this.replaceRefs(selection.refs)
    this.limitExceeded = selection.exceeded || dropped.length > 0
    const added: FileRef[] = []
    let fallbackMessage = ''
    let fallbackCode: number | undefined
    for (const entry of kept) {
      const taskId = this.engine?.enqueue({ file: entry.file, meta: entry.meta })
      if (taskId === undefined) {
        this.replaceRefs(removeFileRef(this.refs, entry.ref.id))
        fallbackMessage = this.engine?.errorMessage || FILE_PLACEHOLDER_TEXT
        fallbackCode = this.engine?.errorCode
        continue
      }
      this.taskRefs.set(taskId, entry.ref.id)
      added.push(entry.ref)
    }
    if (rejected.length > 0) {
      this.fileError = rejected[0]?.message ?? ''
      this.errorCode = rejected[0]?.code
    } else if (added.length > 0) {
      this.fileError = ''
      this.errorCode = undefined
    } else {
      this.fileError = fallbackMessage
      this.errorCode = fallbackCode
    }
    if (added.length > 0) {
      void this.engine?.start()
    }
    this.syncValue()
    this.emitUpdate()
    return { added, rejected }
  }

  /**
   * 重试失败任务（断点续传）。
   *
   * @param taskId 任务标识。
   */
  async retryTask(taskId: string): Promise<void> {
    await this.engine?.retry(taskId)
    this.syncTasks()
  }

  /**
   * 取消任务（移除对应本地占位引用）。
   *
   * @param taskId 任务标识。
   */
  cancelTask(taskId: string): void {
    this.engine?.cancel(taskId)
    const localId = this.taskRefs.get(taskId)
    if (localId !== undefined) {
      this.taskRefs.delete(taskId)
      this.replaceRefs(removeFileRef(this.refs, localId))
    }
    this.syncValue()
    this.emitUpdate()
  }

  /**
   * 移除文件（在途任务一并取消；同步受控值）。
   *
   * @param id 文件标识。
   */
  remove(id: string): void {
    for (const [taskId, localId] of [...this.taskRefs.entries()]) {
      if (localId === id) {
        this.engine?.cancel(taskId)
        this.taskRefs.delete(taskId)
      }
    }
    this.replaceRefs(removeFileRef(this.refs, id))
    this.limitExceeded = false
    this.syncValue()
    this.emitUpdate()
  }

  /** 清空文件（在途任务一并取消）。 */
  clearFiles(): void {
    this.engine?.cancel()
    this.taskRefs.clear()
    this.replaceRefs([])
    this.limitExceeded = false
    this.fileError = ''
    this.errorCode = undefined
    this.syncValue()
    this.emitUpdate()
  }

  /**
   * 移动文件（多图排序；同步受控值顺序）。
   *
   * @param from 原索引。
   * @param to 目标索引。
   */
  moveFile(from: number, to: number): void {
    this.replaceRefs(moveFileRef(this.refs, from, to))
    this.syncValue()
    this.emitUpdate()
  }

  /**
   * 批量回显（未解析标识一次批量取元数据；未命中置失效；已解析不重复请求）。
   *
   * @param ids 待回显标识（缺省取受控值）。
   */
  async resolveFiles(ids?: readonly string[]): Promise<void> {
    const targets = normalizeFileValue(ids ?? this.value, true)
    if (!this.ready || targets.length === 0) {
      return
    }
    const missing = targets.filter((id) => !this.resolved.has(id))
    if (missing.length === 0) {
      return
    }
    const loader = this.transport?.resolveFiles
    if (loader === undefined || this.transport === undefined) {
      for (const id of missing) {
        this.resolved.add(id)
      }
      return
    }
    this.markLoaded()
    try {
      const raw = await loader.call(this.transport, { ids: missing })
      const resolved = normalizeFileRefs(raw)
      const hit = new Set(resolved.map((ref) => ref.id))
      const placeholders: FileRef[] = missing
        .filter((id) => !hit.has(id))
        .map((id) => ({ id, name: id, exists: false }))
      this.replaceRefs(mergeFileRefs(this.refs, [...resolved, ...placeholders]))
      for (const id of missing) {
        this.resolved.add(id)
      }
      this.errorCode = undefined
      this.errorMessage = ''
    } catch (error) {
      const code = readErrorCode(error)
      this.errorCode = code
      this.errorMessage = resolveFileErrorText(code)
      this.reportError(error, { scope: 'BaseFileUpload.resolveFiles' })
    }
    this.emitUpdate()
  }

  /**
   * 取引用。
   *
   * @param id 文件标识。
   * @returns 引用；未命中 `undefined`。
   */
  fileOf(id: string): FileRef | undefined {
    return findFileRef(this.refs, id)
  }

  /**
   * 并入引用元数据（回显名 / 大小 / 地址；不改变受控值顺序）。
   *
   * @param refs 引用列表。
   */
  mergeRefs(refs: readonly FileRef[]): void {
    this.replaceRefs(mergeFileRefs(this.refs, refs.filter((ref) => !isLocalFileRef(ref))))
    this.emitUpdate()
  }

  /**
   * 取引用对应任务标识（在途上传）。
   *
   * @param id 文件标识（本地占位）。
   * @returns 任务标识；无在途任务返回 `undefined`。
   */
  taskIdOfFile(id: string): string | undefined {
    for (const [taskId, localId] of this.taskRefs) {
      if (localId === id) {
        return taskId
      }
    }
    return undefined
  }

  /**
   * 取引用对应任务快照。
   *
   * @param id 文件标识（本地占位）。
   * @returns 任务快照；无在途任务返回 `undefined`。
   */
  taskOfFile(id: string): UploadTaskSnapshot | undefined {
    const taskId = this.taskIdOfFile(id)
    return taskId === undefined ? undefined : this.engine?.taskOf(taskId)
  }

  /**
   * 展示文案（失效标记；名称缺失回退标识）。
   *
   * @param id 文件标识。
   * @returns 展示文案。
   */
  labelOf(id: string): string {
    const ref = this.fileOf(id)
    if (ref === undefined) {
      return id
    }
    return fileRefLabel(ref)
  }

  /** 列表摘要（「、」连接；空值「—」）。 */
  summary(): string {
    return this.refs.length === 0 ? FILE_EMPTY_VALUE : fileListSummary(this.refs)
  }

  /**
   * 取预览地址（经预签名按标识取址；未注入回退已有 `url`，零请求）。
   *
   * @param id 文件标识。
   * @returns 预览地址；不可用返回 `undefined`。
   */
  async previewUrlOf(id: string): Promise<string | undefined> {
    if (this.presigned !== undefined) {
      const url = await this.presigned.get(id, { purpose: 'get' })
      if (url !== undefined) {
        return url
      }
    }
    return this.fileOf(id)?.url
  }

  /**
   * 下载文件（经下载触发能力；未注入即不动作）。
   *
   * @param id 文件标识。
   * @returns 下载结果；不可用返回 `undefined`。
   */
  async downloadFile(id: string): Promise<unknown> {
    const ref = this.fileOf(id)
    if (this.download === undefined || ref === undefined) {
      return undefined
    }
    return this.download.download({ url: ref.url, filename: ref.name })
  }

  /** 失效已解析缓存（下次回显重新请求）。 */
  invalidate(): void {
    this.resolved.clear()
    this.presigned?.clear()
    this.emitUpdate()
  }

  /** 由引用派生受控值并上报（本地占位不入值）。 */
  syncValue(): void {
    const ids = this.selectedIds
    if (ids.length === 0) {
      super.setValue(undefined)
      return
    }
    super.setValue(this.multiple ? ids : (ids[0] as string))
  }

  /** 引擎任务并入引用（完成替换本地占位；失败保留供重试）。 */
  syncTasks(): void {
    const engine = this.engine
    if (engine === undefined) {
      return
    }
    this.tasks.splice(0, this.tasks.length, ...engine.tasks)
    let changed = false
    for (const task of this.tasks) {
      const localId = this.taskRefs.get(task.id)
      if (localId === undefined) {
        continue
      }
      if (task.phase === 'done' && task.fileId !== undefined) {
        const index = this.refs.findIndex((ref) => ref.id === localId)
        if (index >= 0) {
          const previous = this.refs[index] as FileRef
          this.refs.splice(index, 1, { ...previous, id: task.fileId, exists: true })
          changed = true
        }
        this.taskRefs.delete(task.id)
      }
    }
    if (changed) {
      this.syncValue()
    }
    this.emitUpdate()
  }

  /**
   * 校验元信息（类型 / 大小 / 空文件 / 图片尺寸与比例）。
   *
   * @param meta 文件元信息。
   * @returns 校验结果。
   */
  private checkMeta(meta: FileMeta): FileCheckResult {
    const check = checkFileMeta(meta, { accept: this.accept, maxSize: this.maxSize, kind: this.kind })
    if (!check.valid) {
      return check
    }
    if (this.kind === 'image' && this.imageOptions !== undefined) {
      return checkImageDimension(meta.dimension, this.imageOptions)
    }
    return check
  }

  /** 按受控值重建引用（保留在途本地占位；已解析元数据沿用）。 */
  private syncRefsFromValue(): void {
    const ids = normalizeFileValue(this.value, this.multiple)
    const pending = this.refs.filter((ref) => isLocalFileRef(ref))
    const known = new Map(this.refs.filter((ref) => !isLocalFileRef(ref)).map((ref) => [ref.id, ref]))
    const next: FileRef[] = ids.map((id) => known.get(id) ?? { id, name: id })
    this.replaceRefs([...next, ...pending])
  }

  /**
   * 替换引用列表（原地更新，保持数组引用稳定）。
   *
   * @param next 新列表。
   */
  private replaceRefs(next: readonly FileRef[]): void {
    this.refs.splice(0, this.refs.length, ...next)
  }

  /** 通知变更（已释放时跳过）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /** 释放（解绑引擎订阅后释放基类资源）。 */
  override dispose(): void {
    this.offEngine?.()
    this.offEngine = undefined
    super.dispose()
  }
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
