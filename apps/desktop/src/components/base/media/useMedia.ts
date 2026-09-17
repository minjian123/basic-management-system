/**
 * 媒体片段（`media`）：图片 / 音视频 / 文件预览的加载状态机与地址重取。
 *
 * 契约见《组件设计 · 媒体片段》：`src` / `ratio` / `lazy` / `fit` / `fallback` / `retryOnExpired` +
 * 加载状态机（`idle` → `loading` → `success` / `error` / `expired`）与 URL 重取。
 * **组合依赖**：`presigned-url`（预签名过期时重取地址）。**占位先行**：未注入 `presigner` 时
 * 过期重取直接回落 `fallback`，不发请求。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import type { UsePresignedUrlReturn } from '../presigned-url/usePresignedUrl'

/** 媒体加载状态 */
export type MediaState = 'idle' | 'loading' | 'success' | 'error' | 'expired'

/** 媒体片段参数 */
export interface UseMediaOptions {
  /** 媒体地址（可为 fileId 或直链） */
  src?: MaybeRefOrGetter<string | undefined>
  /** 宽高比（如 `16/9`；供容器占位撑高，避免布局跳动） */
  ratio?: MaybeRefOrGetter<string | number | undefined>
  /** 懒加载（宿主把 `onVisible` 挂到 IntersectionObserver） */
  lazy?: MaybeRefOrGetter<boolean>
  /** 填充方式（`cover` / `contain`） */
  fit?: MaybeRefOrGetter<'cover' | 'contain' | undefined>
  /** 失败 / 过期时的回退地址 */
  fallback?: MaybeRefOrGetter<string>
  /** 预签名过期是否自动重取 */
  retryOnExpired?: MaybeRefOrGetter<boolean>
  /** 预签名片段（重取入口；缺省即占位） */
  presigner?: Pick<UsePresignedUrlReturn, 'refresh'>
  /** 是否用 fileId 走预签名（默认 false：`src` 即直链） */
  fileId?: MaybeRefOrGetter<string | undefined>
  onLoad?: () => void
  onError?: (state: MediaState) => void
}

/** 媒体片段返回值 */
export interface UseMediaReturn {
  readonly state: MediaState
  readonly isLoading: boolean
  readonly isPlaceholder: boolean
  /** 是否懒加载（宿主据此决定是否等进入视口再调 `onVisible`） */
  readonly lazy: boolean
  readonly displaySrc: string
  readonly ratioStyle: Record<string, string>
  readonly fitStyle: Record<string, string>
  /** 进入视口（懒加载触发加载） */
  onVisible: () => Promise<void>
  /** 加载成功 */
  onLoad: () => void
  /** 加载失败（按需自动重取一次） */
  onError: () => Promise<void>
  /** 手工重试 */
  retry: () => Promise<void>
}

/**
 * 获取媒体能力。
 *
 * 用法：`const media = useMedia({ src, fileId, presigner, ratio: '16/9' })`；
 * 模板里 `:src="media.displaySrc"` + `@load="media.onLoad"` + `@error="media.onError"`。
 */
export function useMedia(options: UseMediaOptions = {}): UseMediaReturn {
  const capability = declareFragment('media')

  const state = ref<MediaState>('idle')
  const resolvedUrl = ref('')
  const retried = ref(false)
  const isPlaceholder = computed(() => options.presigner === undefined && options.fileId !== undefined)

  const fallback = computed(() => String(toValue(options.fallback) ?? ''))

  const displaySrc = computed(() => resolvedUrl.value || String(toValue(options.src) ?? '') || fallback.value)

  const load = async (): Promise<void> => {
    const fileId = toValue(options.fileId)
    if (fileId !== undefined && options.presigner) {
      state.value = 'loading'
      try {
        resolvedUrl.value = await options.presigner.refresh(fileId)
        state.value = 'success'
        return
      } catch (error) {
        capability.reportError(error, { scope: 'media.load', fileId })
        state.value = 'error'
        options.onError?.('error')
        return
      }
    }
    if (fileId !== undefined && !options.presigner) {
      capability.log('debug', 'media 占位：预签名未接入，使用回退地址')
      resolvedUrl.value = fallback.value
      state.value = 'success'
      return
    }
    state.value = 'loading'
  }

  const handleError = async (): Promise<void> => {
    const shouldRetry = (toValue(options.retryOnExpired) ?? true) && !retried.value
    if (shouldRetry) {
      retried.value = true
      state.value = 'expired'
      await load()
      return
    }
    state.value = 'error'
    resolvedUrl.value = fallback.value
    options.onError?.('error')
  }

  return {
    get state() {
      return state.value
    },
    get isLoading() {
      return state.value === 'loading'
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get lazy() {
      return Boolean(toValue(options.lazy))
    },
    get displaySrc() {
      return displaySrc.value
    },
    get ratioStyle() {
      const ratio = toValue(options.ratio)
      const style: Record<string, string> = {}
      if (ratio !== undefined) {
        style.aspectRatio = String(ratio)
      }
      return style
    },
    get fitStyle() {
      const fit = toValue(options.fit)
      const style: Record<string, string> = {}
      if (fit !== undefined) {
        style.objectFit = fit
      }
      return style
    },
    onVisible: async () => {
      if (state.value === 'success') {
        return
      }
      await load()
    },
    onLoad: () => {
      state.value = 'success'
      options.onLoad?.()
    },
    onError: handleError,
    retry: async () => {
      retried.value = false
      resolvedUrl.value = ''
      await load()
    },
  }
}
