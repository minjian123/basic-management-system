/**
 * 预签名片段（`presigned-url`）：文件访问地址的获取、失效重取与降级下载。
 *
 * 契约见《组件设计 · 预签名片段》：`get` / `refresh` / `download` / `invalidate` + TTL 缓存与提前刷新。
 * **占位先行**：未注入 `signer`（对象存储未接入）时返回 `fallback` 地址（默认空串）并标记
 * `isPlaceholder`，**不发请求、不报错**；媒体 / 上传 / 导出等消费方按占位态降级。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 预签名结果 */
export interface PresignedResult {
  /** 访问地址（占位态为 `fallback`） */
  url: string
  /** 过期时间戳（毫秒；占位态为 `undefined`） */
  expiresAt?: number
}

/** 预签名片段参数 */
export interface UsePresignedUrlOptions {
  /** 签名器（缺省即占位：不发请求，返回 `fallback`） */
  signer?: (fileId: string, opts: { method: string; expiresIn: number }) => Promise<PresignedResult>
  /** 请求方法口径（`get` 预览 / `put` 直传） */
  method?: MaybeRefOrGetter<'get' | 'put'>
  /** 有效期（秒；缺省 300） */
  expiresIn?: MaybeRefOrGetter<number>
  /** 提前刷新窗口（秒；缺省 30） */
  refreshAhead?: MaybeRefOrGetter<number>
  /** 占位 / 失败时的降级地址 */
  fallback?: MaybeRefOrGetter<string>
}

/** 预签名片段返回值 */
export interface UsePresignedUrlReturn {
  readonly urls: Record<string, string>
  readonly isPlaceholder: boolean
  /** 取地址（命中缓存且未进入刷新窗口时直接返回） */
  get: (fileId: string, opts?: { method?: 'get' | 'put'; force?: boolean }) => Promise<string>
  /** 强制重取（失效 / 过期时使用） */
  refresh: (fileId: string) => Promise<string>
  /** 下载地址（与预览同源，占位态回落 `fallback`） */
  download: (fileId: string) => Promise<string>
  /** 失效缓存（单文件或全部） */
  invalidate: (fileId?: string) => void
}

interface CacheEntry {
  result: PresignedResult
  method: string
}

/**
 * 获取预签名能力。
 *
 * 用法：`const presigner = usePresignedUrl({ signer })`；未接入对象存储时省略 `signer` 即得占位行为。
 */
export function usePresignedUrl(options: UsePresignedUrlOptions = {}): UsePresignedUrlReturn {
  const capability = declareFragment('presigned-url')

  const cache = ref<Record<string, CacheEntry>>({})
  const isPlaceholder = computed(() => options.signer === undefined)
  const fallback = computed(() => String(toValue(options.fallback) ?? ''))

  const isFresh = (entry: CacheEntry): boolean => {
    if (entry.result.expiresAt === undefined) {
      return false
    }
    const ahead = Number(toValue(options.refreshAhead) ?? 30) * 1000
    return entry.result.expiresAt - ahead > Date.now()
  }

  const get = async (fileId: string, opts: { method?: 'get' | 'put'; force?: boolean } = {}): Promise<string> => {
    const method = opts.method ?? toValue(options.method) ?? 'get'
    const cached = cache.value[fileId]
    if (!opts.force && cached && cached.method === method && isFresh(cached)) {
      return cached.result.url
    }
    if (!options.signer) {
      capability.log('debug', 'presigned-url 占位：对象存储未接入，返回降级地址')
      return fallback.value
    }
    const result = await options.signer(fileId, { method, expiresIn: Number(toValue(options.expiresIn) ?? 300) })
    cache.value = { ...cache.value, [fileId]: { result, method } }
    return result.url
  }

  return {
    get urls() {
      return Object.fromEntries(Object.entries(cache.value).map(([key, entry]) => [key, entry.result.url]))
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get,
    refresh: (fileId) => get(fileId, { force: true }),
    download: (fileId) => get(fileId),
    invalidate: (fileId) => {
      if (fileId === undefined) {
        cache.value = {}
        return
      }
      const next = { ...cache.value }
      delete next[fileId]
      cache.value = next
    },
  }
}
