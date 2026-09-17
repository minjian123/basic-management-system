/**
 * 上传引擎片段（`upload-engine`）：分片、秒传、断点续传、进度与取消。
 *
 * 契约见《组件设计 · 上传引擎片段》：`upload` / `pause` / `resume` / `cancel` / `retry` +
 * 进度与已上传 / 失败清单（文件上传、富文本插图、头像、导入共用）。
 * **组合依赖**：`presigned-url`（预签名直传）。**占位先行**：未注入 `uploader`（对象存储未接入）时
 * `upload` 直接进入 `placeholder` 态（**不发请求**），消费方按 `isPlaceholder` 隐藏入口或提示暂不可用。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import type { UsePresignedUrlReturn } from '../presigned-url/usePresignedUrl'

/** 上传项状态 */
export type UploadItemStatus = 'pending' | 'uploading' | 'paused' | 'success' | 'failed' | 'cancelled' | 'placeholder'

/** 上传项 */
export interface UploadItem {
  /** 本地唯一标识 */
  uid: string
  name: string
  size: number
  status: UploadItemStatus
  /** 进度（0 ~ 100） */
  progress: number
  /** 服务端返回的文件标识 */
  fileId?: string
  url?: string
  error?: string
}

/** 上传器（对象存储接入后注入；返回 fileId 与访问地址） */
export type Uploader = (item: UploadItem, controller: AbortController) => Promise<{ fileId: string; url?: string }>

/** 上传引擎片段参数 */
export interface UseUploadEngineOptions {
  accept?: MaybeRefOrGetter<string | undefined>
  /** 单文件大小上限（字节） */
  maxSize?: MaybeRefOrGetter<number | undefined>
  multiple?: MaybeRefOrGetter<boolean>
  /** 数量上限 */
  limit?: MaybeRefOrGetter<number | undefined>
  /** 分片大小（字节；后端对象存储接入后生效） */
  chunkSize?: MaybeRefOrGetter<number | undefined>
  /** 并发数（默认 3） */
  concurrency?: MaybeRefOrGetter<number | undefined>
  /** 是否直传（预签名直传对象存储；否则经后端中转） */
  direct?: MaybeRefOrGetter<boolean>
  /** 上传器（缺省即占位） */
  uploader?: Uploader
  /** 预签名片段（直传时由 `uploader` 内部取签名；本片段只约定注入点与依赖登记） */
  presigner?: Pick<UsePresignedUrlReturn, 'get'>
  onSuccess?: (item: UploadItem) => void
  onFailed?: (item: UploadItem) => void
}

/** 上传引擎片段返回值 */
export interface UseUploadEngineReturn {
  readonly items: UploadItem[]
  readonly uploaded: UploadItem[]
  readonly failed: UploadItem[]
  readonly isPlaceholder: boolean
  readonly uploading: boolean
  /** 上传（做大小 / 类型 / 数量前置校验，失败项不进入队列） */
  upload: (files: Array<{ name: string; size: number }>) => Promise<UploadItem[]>
  pause: (uid: string) => void
  resume: (uid: string) => Promise<void>
  cancel: (uid: string) => void
  retry: (uid: string) => Promise<void>
  clear: () => void
}

let uidSeed = 0
/** 生成上传项标识（保持稳定可读） */
function nextUid(): string {
  uidSeed += 1
  return `upload-${uidSeed}`
}

/**
 * 获取上传引擎能力。
 *
 * 用法：`const upload = useUploadEngine({ accept, maxSize, uploader })`；
 * 对象存储未就绪时省略 `uploader` 即得占位行为（队列项标记为 `placeholder`，不发请求）。
 */
export function useUploadEngine(options: UseUploadEngineOptions = {}): UseUploadEngineReturn {
  const capability = declareFragment('upload-engine')

  const items = ref<UploadItem[]>([])
  const controllers = new Map<string, AbortController>()
  const isPlaceholder = computed(() => options.uploader === undefined)
  const uploading = computed(() => items.value.some((item) => item.status === 'uploading'))

  const patch = (uid: string, changes: Partial<UploadItem>): void => {
    items.value = items.value.map((item) => (item.uid === uid ? { ...item, ...changes } : item))
  }

  const validate = (file: { name: string; size: number }): string | undefined => {
    const accept = toValue(options.accept)
    if (accept) {
      const patterns = accept
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean)
      const matched = patterns.some((pattern) =>
        pattern.startsWith('.')
          ? file.name.toLowerCase().endsWith(pattern.toLowerCase())
          : file.name.includes(pattern.replace('*', '')),
      )
      if (!matched) {
        return `不支持的文件类型（允许：${accept}）`
      }
    }
    const maxSize = toValue(options.maxSize)
    if (maxSize !== undefined && file.size > maxSize) {
      return `文件超过大小上限（${Math.round(maxSize / 1024 / 1024)}MB）`
    }
    return undefined
  }

  const run = async (item: UploadItem): Promise<UploadItem> => {
    if (!options.uploader) {
      patch(item.uid, { status: 'placeholder', error: '对象存储未接入（占位）' })
      capability.log('debug', 'upload-engine 占位：上传器未接入，不发请求')
      // 返回队列中的最新项（而非入参副本），调用方据此读取占位状态
      return items.value.find((entry) => entry.uid === item.uid) ?? item
    }
    const controller = new AbortController()
    controllers.set(item.uid, controller)
    patch(item.uid, { status: 'uploading', progress: 10 })
    try {
      const result = await options.uploader({ ...item, status: 'uploading' }, controller)
      patch(item.uid, {
        status: 'success',
        progress: 100,
        fileId: result.fileId,
        ...(result.url ? { url: result.url } : {}),
      })
      const done = items.value.find((entry) => entry.uid === item.uid)
      if (done) {
        options.onSuccess?.(done)
      }
      return done ?? item
    } catch (error) {
      const cancelled = controller.signal.aborted
      patch(item.uid, {
        status: cancelled ? 'cancelled' : 'failed',
        error: cancelled ? '已取消' : '上传失败',
      })
      if (!cancelled) {
        capability.reportError(error, { scope: 'upload-engine.upload', name: item.name })
        const failed = items.value.find((entry) => entry.uid === item.uid)
        if (failed) {
          options.onFailed?.(failed)
        }
      }
      return items.value.find((entry) => entry.uid === item.uid) ?? item
    } finally {
      controllers.delete(item.uid)
    }
  }

  return {
    get items() {
      return items.value
    },
    get uploaded() {
      return items.value.filter((item) => item.status === 'success')
    },
    get failed() {
      return items.value.filter((item) => item.status === 'failed')
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get uploading() {
      return uploading.value
    },
    upload: async (files) => {
      const limit = toValue(options.limit)
      const multiple = toValue(options.multiple) ?? false
      const candidates = multiple ? files : files.slice(0, 1)
      const accepted: UploadItem[] = []
      for (const file of candidates) {
        const error = validate(file)
        if (error) {
          capability.log('warn', `upload-engine 拒绝文件：${file.name}（${error}）`)
          continue
        }
        if (limit !== undefined && accepted.length >= limit) {
          break
        }
        accepted.push({
          uid: nextUid(),
          name: file.name,
          size: file.size,
          status: 'pending',
          progress: 0,
        })
      }
      items.value = [...items.value, ...accepted]
      const results: UploadItem[] = []
      for (const item of accepted) {
        results.push(await run(item))
      }
      return results
    },
    pause: (uid) => {
      const controller = controllers.get(uid)
      if (controller) {
        controller.abort()
        patch(uid, { status: 'paused' })
      }
    },
    resume: async (uid) => {
      const item = items.value.find((entry) => entry.uid === uid)
      if (!item || item.status === 'success') {
        return
      }
      await run(item)
    },
    cancel: (uid) => {
      controllers.get(uid)?.abort()
      patch(uid, { status: 'cancelled', progress: 0 })
    },
    retry: async (uid) => {
      const item = items.value.find((entry) => entry.uid === uid)
      if (!item) {
        return
      }
      patch(uid, { status: 'pending', progress: 0, error: undefined })
      await run({ ...item, status: 'pending' })
    },
    clear: () => {
      items.value = []
    },
  }
}
