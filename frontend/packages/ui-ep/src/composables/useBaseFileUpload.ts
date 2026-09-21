/** 文件上传族投影：把核心组件基类 `BaseFileUpload` 与上传引擎 / 预签名投影为组合式（列表 / 校验 / 上传 / 回显 / 预览下载）。 */

import {
  BaseFileUpload,
  BasePresignedUrl,
  type FileAcceptResult,
  type FileKind,
  type FileMeta,
  type FileRef,
  type FileUploadOptions,
  type ImageCheckOptions,
  type ImageCropShape,
  type UploadTaskSnapshot,
  type UploadTransportAdapter,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

import { useBaseUploadEngine, type UseBaseUploadEngineResult } from './useBaseUploadEngine'

/** 具体文件上传族（可实例化）。 */
class FileUploadState extends BaseFileUpload {}

/** 具体预签名（可实例化）。 */
class PresignedState extends BasePresignedUrl {}

/** 字段值类型（单标识 / 标识数组）。 */
export type FileUploadValue = string | string[]

/** `useBaseFileUpload` 选项。 */
export interface UseBaseFileUploadOptions {
  /** 数据通路是否就绪（缺省 false）。 */
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
  /** 初始值。 */
  value?: FileUploadValue
  /** 上传通路（未注入即占位零请求）。 */
  transport?: UploadTransportAdapter
  /** 预签名能力（缺省内建并由通路装配取址器）。 */
  presigned?: BasePresignedUrl
  /** 件级禁用。 */
  disabled?: boolean
}

/** `useBaseFileUpload` 返回面（与核心方法一一对应的响应式面）。 */
export interface UseBaseFileUploadResult {
  /** 文件上传族实例。 */
  upload: BaseFileUpload
  /** 上传引擎投影（任务与进度面）。 */
  engine: UseBaseUploadEngineResult
  /** 是否就绪。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态。 */
  degraded: Ref<boolean>
  /** 生效禁用（件级禁用 ∨ 占位）。 */
  disabled: ComputedRef<boolean>
  /** 请求计数（占位态保持 0）。 */
  requestCount: Ref<number>
  /** 受控值。 */
  value: Ref<string | string[] | undefined>
  /** 引用列表。 */
  refs: Ref<FileRef[]>
  /** 受控标识（不含本地占位）。 */
  selectedIds: ComputedRef<string[]>
  /** 任务快照。 */
  tasks: Ref<UploadTaskSnapshot[]>
  /** 是否在途。 */
  busy: ComputedRef<boolean>
  /** 聚合进度。 */
  totalPercent: Ref<number>
  /** 是否空态。 */
  empty: ComputedRef<boolean>
  /** 多选超限标记。 */
  limitExceeded: Ref<boolean>
  /** 校验 / 上传失败文案。 */
  fileError: Ref<string>
  /** 是否错误态。 */
  error: ComputedRef<boolean>
  /** 错误码。 */
  errorCode: Ref<number | undefined>
  /** 错误文案。 */
  errorMessage: Ref<string>
  /** 错误文案（同 `errorMessage`）。 */
  errorText: ComputedRef<string>
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 装配选项（合并式）。 */
  setOptions(options: FileUploadOptions): void
  /** 注入 / 移除通路。 */
  setTransport(transport: UploadTransportAdapter | undefined): void
  /** 设置受控值。 */
  setValue(value: FileUploadValue | undefined): void
  /** 同步受控值并触发批量回显（件层 `modelValue` 监听用）。 */
  syncValue(value: FileUploadValue | undefined): void
  /** 接受文件（校验 → 上限截断 → 入队上传）。 */
  acceptFiles(inputs: readonly { file: unknown; meta: FileMeta }[]): FileAcceptResult
  /** 重试任务。 */
  retryTask(taskId: string): Promise<void>
  /** 取消任务。 */
  cancelTask(taskId: string): void
  /** 移除文件。 */
  remove(id: string): void
  /** 清空文件。 */
  clearFiles(): void
  /** 多图排序。 */
  moveFile(from: number, to: number): void
  /** 批量回显。 */
  resolveFiles(ids?: readonly string[]): Promise<void>
  /** 预览地址（经预签名）。 */
  previewUrlOf(id: string): Promise<string | undefined>
  /** 下载文件（经下载触发）。 */
  downloadFile(id: string): Promise<unknown>
  /** 展示文案（失效标记）。 */
  labelOf(id: string): string
  /** 并入引用元数据（回显名 / 大小 / 地址）。 */
  mergeRefs(refs: readonly FileRef[]): void
  /** 取引用对应任务快照（在途上传）。 */
  taskOfFile(id: string): UploadTaskSnapshot | undefined
  /** 列表摘要。 */
  summary(): string
  /** 订阅值变更。 */
  onValueChange(listener: (value: string | string[] | undefined) => void): () => void
}

/**
 * 使用文件上传族投影。
 *
 * @param options 选项。
 * @returns 文件族实例与响应式面。
 */
export function useBaseFileUpload(options: UseBaseFileUploadOptions = {}): UseBaseFileUploadResult {
  const upload = new FileUploadState()
  const presigned = options.presigned ?? new PresignedState()
  const localDisabled = ref(options.disabled ?? false)
  const engine = useBaseUploadEngine({
    ...(options.transport === undefined ? {} : { transport: options.transport }),
    presigned,
    ...(options.partSize === undefined ? {} : { chunkSize: options.partSize }),
    config: {
      ...(options.partSize === undefined ? {} : { partSize: options.partSize }),
      ...(options.wholeMaxSize === undefined ? {} : { wholeMaxSize: options.wholeMaxSize }),
      ...(options.maxSize === undefined ? {} : { maxFileSize: options.maxSize }),
      ...(options.concurrency === undefined ? {} : { concurrency: options.concurrency }),
      ...(options.autoDedup === undefined ? {} : { autoDedup: options.autoDedup }),
    },
  })

  // 预签名取址器：经通路预签名接口（未覆写时不请求，回落已有地址）
  if (options.presigned === undefined && options.transport?.presign !== undefined) {
    presigned.fetcher = async (input) => {
      const raw = (await options.transport?.presign?.({
        fileId: input?.key ?? '',
        purpose: 'preview',
      })) as { url?: unknown; expires_in?: unknown } | undefined
      const url = typeof raw?.url === 'string' ? raw.url : ''
      const expiresIn = typeof raw?.expires_in === 'number' ? raw.expires_in : 3600
      return { url, expiresAt: url === '' ? 0 : Date.now() + expiresIn * 1000 }
    }
  }

  upload.setEngine(engine.engine)
  upload.setPresigned(presigned)
  upload.setOptions({
    ready: options.ready ?? false,
    ...(options.kind === undefined ? {} : { kind: options.kind }),
    ...(options.multiple === undefined ? {} : { multiple: options.multiple }),
    ...(options.limit === undefined ? {} : { limit: options.limit }),
    ...(options.accept === undefined ? {} : { accept: options.accept }),
    ...(options.maxSize === undefined ? {} : { maxSize: options.maxSize }),
    ...(options.wholeMaxSize === undefined ? {} : { wholeMaxSize: options.wholeMaxSize }),
    ...(options.compress === undefined ? {} : { compress: options.compress }),
    ...(options.crop === undefined ? {} : { crop: options.crop }),
    ...(options.cropShape === undefined ? {} : { cropShape: options.cropShape }),
    ...(options.cropAspect === undefined ? {} : { cropAspect: options.cropAspect }),
    ...(options.imageOptions === undefined ? {} : { imageOptions: options.imageOptions }),
    ...(options.draggable === undefined ? {} : { draggable: options.draggable }),
    ...(options.readonlyView === undefined ? {} : { readonlyView: options.readonlyView }),
  })
  if (options.transport !== undefined) {
    upload.setTransport(options.transport)
  }
  if (options.value !== undefined) {
    upload.setValue(options.value)
  }

  const ready = ref(upload.ready)
  const degraded = ref(upload.degraded)
  const requestCount = ref(upload.requestCount)
  const value = ref(upload.value)
  const refs = ref<FileRef[]>([...upload.refs])
  const limitExceeded = ref(upload.limitExceeded)
  const fileError = ref(upload.fileError)
  const errorCode = ref(upload.errorCode)
  const errorMessage = ref(upload.errorMessage)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    ready.value = upload.ready
    degraded.value = upload.degraded
    requestCount.value = upload.requestCount
    value.value = upload.value
    refs.value = [...upload.refs]
    limitExceeded.value = upload.limitExceeded
    fileError.value = upload.fileError
    errorCode.value = upload.errorCode
    errorMessage.value = upload.errorMessage
  }

  const off = upload.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offValue = upload.onChange(() => sync())
  onScopeDispose(() => {
    off()
    offValue()
    upload.dispose()
  })

  const disabled = computed(() => localDisabled.value || !ready.value)
  const selectedIds = computed(() => upload.selectedIds)
  const empty = computed(() => refs.value.length === 0 && !engine.busy.value)
  const error = computed(() => errorCode.value !== undefined)
  const errorText = computed(() => errorMessage.value)

  return {
    upload,
    engine,
    ready,
    degraded,
    disabled,
    requestCount,
    value,
    refs,
    selectedIds,
    tasks: engine.tasks,
    busy: engine.busy,
    totalPercent: engine.totalPercent,
    empty,
    limitExceeded,
    fileError,
    error,
    errorCode,
    errorMessage,
    errorText,
    setReady: (next) => upload.setReady(next),
    setOptions: (next) => upload.setOptions(next),
    setTransport: (next) => upload.setTransport(next),
    setValue: (next) => upload.setValue(next),
    syncValue: (next) => {
      upload.setValue(next)
      sync()
      if (upload.selectedIds.length > 0) {
        void upload.resolveFiles()
      }
    },
    acceptFiles: (inputs) => upload.acceptFiles(inputs),
    retryTask: (taskId) => upload.retryTask(taskId),
    cancelTask: (taskId) => upload.cancelTask(taskId),
    remove: (id) => upload.remove(id),
    clearFiles: () => upload.clearFiles(),
    moveFile: (from, to) => upload.moveFile(from, to),
    resolveFiles: (ids) => upload.resolveFiles(ids),
    previewUrlOf: (id) => upload.previewUrlOf(id),
    downloadFile: (id) => upload.downloadFile(id),
    labelOf: (id) => upload.labelOf(id),
    mergeRefs: (next) => upload.mergeRefs(next),
    taskOfFile: (id) => upload.taskOfFile(id),
    summary: () => upload.summary(),
    onValueChange: (listener) => upload.onChange(listener),
  }
}
