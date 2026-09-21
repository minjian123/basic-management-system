/** 上传引擎投影：把核心上传引擎能力基类 `BaseUploadEngine` 投影为组合式（进度 / 任务 / 通路 / 分片）。 */

import {
  BasePresignedUrl,
  BaseUploadEngine,
  type FileMeta,
  type UploadEngineConfig,
  type UploadTaskSnapshot,
  type UploadTransportAdapter,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体上传引擎（可实例化）。 */
class UploadEngine<TFile> extends BaseUploadEngine<TFile> {}

/** 选项。 */
export interface UseBaseUploadEngineOptions {
  /** 分片大小（字节）。 */
  chunkSize?: number
  /** 单文件大小上限（字节；0 表示不限）。 */
  maxSize?: number
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 上传通路（未注入即占位零请求）。 */
  transport?: UploadTransportAdapter
  /** 预签名能力（组合引用）。 */
  presigned?: BasePresignedUrl
  /** 引擎配置（整包阈值 / 分片 / 并发 / 重试 / 秒传）。 */
  config?: UploadEngineConfig
}

/** `useBaseUploadEngine` 返回面。 */
export interface UseBaseUploadEngineResult<TFile = unknown> {
  /** 上传引擎基类实例。 */
  engine: BaseUploadEngine<TFile>
  /** 上传进度（0 ~ 100，既有单文件路径；响应式）。 */
  progress: Ref<number>
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（响应式）。 */
  degraded: Ref<boolean>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 任务快照（响应式）。 */
  tasks: Ref<UploadTaskSnapshot[]>
  /** 是否在途（响应式）。 */
  busy: ComputedRef<boolean>
  /** 聚合进度（响应式）。 */
  totalPercent: Ref<number>
  /** 是否可上传（响应式）。 */
  canUpload: ComputedRef<boolean>
  /** 设置就绪态。 */
  setReady: (value: boolean) => void
  /** 注入 / 移除通路。 */
  setTransport: (transport: UploadTransportAdapter | undefined) => void
  /** 注入 / 移除预签名。 */
  setPresigned: (presigned: BasePresignedUrl | undefined) => void
  /** 配置引擎。 */
  setConfig: (input: UploadEngineConfig) => void
  /** 入队任务（占位 / 未就绪返回 `undefined`）。 */
  enqueue: (input: { file: TFile; meta: FileMeta; key?: string }) => string | undefined
  /** 启动任务。 */
  start: (taskId?: string) => Promise<void>
  /** 重试任务。 */
  retry: (taskId: string) => Promise<void>
  /** 取消任务（无参取消全部并复位单文件进度）。 */
  cancelTask: (taskId?: string) => void
  /** 移除任务。 */
  remove: (taskId: string) => void
  /** 取任务快照。 */
  taskOf: (taskId: string) => UploadTaskSnapshot | undefined
  /** 上传文件（既有单文件路径；未注入上传器则占位返回 `undefined`）。 */
  upload: (file: TFile) => Promise<string | undefined>
  /** 取消上传（复位进度）。 */
  cancel: () => void
}

/**
 * 使用上传引擎投影。
 *
 * @param options 选项。
 * @returns 上传引擎基类实例与响应式面。
 */
export function useBaseUploadEngine<TFile = unknown>(
  options: UseBaseUploadEngineOptions = {},
): UseBaseUploadEngineResult<TFile> {
  const engine = new UploadEngine<TFile>()
  if (options.chunkSize !== undefined) {
    engine.chunkSize = options.chunkSize
  }
  if (options.maxSize !== undefined) {
    engine.maxSize = options.maxSize
  }
  if (options.config !== undefined) {
    engine.setConfig(options.config)
  }
  if (options.ready !== undefined) {
    engine.setReady(options.ready)
  }
  if (options.transport !== undefined) {
    engine.setTransport(options.transport)
  }
  if (options.presigned !== undefined) {
    engine.setPresigned(options.presigned)
  }

  const progress = ref(engine.progress)
  const ready = ref(engine.ready)
  const degraded = ref(engine.degraded)
  const requestCount = ref(engine.requestCount)
  const tasks = ref<UploadTaskSnapshot[]>([...engine.tasks])
  const totalPercent = ref(engine.totalPercent)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    progress.value = engine.progress
    ready.value = engine.ready
    degraded.value = engine.degraded
    requestCount.value = engine.requestCount
    tasks.value = [...engine.tasks]
    totalPercent.value = engine.totalPercent
  }

  const off = engine.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    engine.dispose()
  })

  const busy = computed(() => tasks.value.some((task) => task.phase === 'pending' || task.phase === 'hashing' || task.phase === 'uploading' || task.phase === 'merging'))
  const canUpload = computed(() => ready.value && engine.transport !== undefined)

  return {
    engine,
    progress,
    ready,
    degraded,
    requestCount,
    tasks,
    busy,
    totalPercent,
    canUpload,
    setReady: (value) => engine.setReady(value),
    setTransport: (transport) => engine.setTransport(transport),
    setPresigned: (presigned) => engine.setPresigned(presigned),
    setConfig: (input) => engine.setConfig(input),
    enqueue: (input) => engine.enqueue(input),
    start: (taskId) => engine.start(taskId),
    retry: (taskId) => engine.retry(taskId),
    cancelTask: (taskId) => engine.cancel(taskId),
    remove: (taskId) => engine.remove(taskId),
    taskOf: (taskId) => engine.taskOf(taskId),
    upload: async (file) => {
      const key = await engine.upload(file)
      sync()
      return key
    },
    cancel: () => {
      engine.cancel()
      sync()
    },
  }
}
