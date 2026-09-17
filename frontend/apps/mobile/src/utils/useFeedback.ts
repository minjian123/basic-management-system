/**
 * 反馈状态机（`useFeedback`）：空 / 错 / 载态的统一编排与重试。
 *
 * 契约见《组件设计 · 异常与空状态》§7：`loading → ready / empty / error`；`retry` 回 `loading` 重试；
 * 空判定（缺省数组空 / `null` / 空对象）可覆盖（区分「有筛选无结果」）；错误文案缺省取
 * `ApiError.userMessage`（请求层 `error.{code}` 映射），**不暴露堆栈**。
 *
 * 内部复用 `useRequest`（竞态 / 取消 / loading），不重复实现。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'

import { ApiError, errorMessage } from '@/api/error'

import { useRequest } from './useRequest'

/** 反馈状态 */
export type FeedbackState = 'loading' | 'empty' | 'error' | 'ready'

/** 归一化错误（供界面呈现） */
export interface FeedbackError {
  code?: number
  message: string
}

/** `useFeedback` 参数 */
export interface UseFeedbackOptions<T> {
  /** 数据加载器（经请求封装） */
  loader: () => Promise<T>
  /** 挂载即加载（缺省 false） */
  immediate?: boolean
  /** 空判定（缺省：数组 / `null` / 空对象视为空） */
  isEmpty?: (data: T) => boolean
  /** 错误文案覆盖（缺省 `ApiError.userMessage` / `error.{code}` 映射） */
  errorText?: (error: unknown) => string
  /** 重试文案（供界面） */
  retryText?: string
  /** 错误回调（供页面提示） */
  onError?: (error: unknown) => void
}

/** `useFeedback` 返回值 */
export interface UseFeedbackReturn<T> {
  state: Ref<FeedbackState>
  data: Ref<T | null>
  error: Ref<FeedbackError | null>
  loading: ComputedRef<boolean>
  load: () => Promise<void>
  retry: () => Promise<void>
}

/** 缺省空判定：`[]` / `null` / `{}` 视为空 */
function defaultIsEmpty(data: unknown): boolean {
  if (data === null || data === undefined) {
    return true
  }
  if (Array.isArray(data)) {
    return data.length === 0
  }
  if (typeof data === 'object') {
    return Object.keys(data as Record<string, unknown>).length === 0
  }
  return false
}

/** 错误归一（`ApiError` 带码；其余取 message，不暴露堆栈） */
function normalizeError(error: unknown, errorText?: (error: unknown) => string): FeedbackError {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      message: errorText?.(error) ?? (error.userMessage || errorMessage(error.code)),
    }
  }
  const fallback = error instanceof Error ? error.message : String(error)
  return { message: errorText?.(error) ?? fallback }
}

/**
 * 获取反馈状态机能力。
 *
 * 用法：页面据 `state` 渲染 `SkeletonBlock` / `EmptyState` / `ErrorPage`（区块级用 `EmptyState` + 重试按钮）。
 */
export function useFeedback<T>(options: UseFeedbackOptions<T>): UseFeedbackReturn<T> {
  const request = useRequest<T>(() => options.loader())
  const state = ref<FeedbackState>('loading')
  const error = ref<FeedbackError | null>(null)

  async function load(): Promise<void> {
    state.value = 'loading'
    error.value = null
    const result = await request.run()
    if (request.error.value !== null) {
      error.value = normalizeError(request.error.value, options.errorText)
      state.value = 'error'
      options.onError?.(request.error.value)
      return
    }
    // 注意：`result === null` 可能为「合法空数据」（取消场景由 useRequest 内部重发覆盖），不单独短路
    const empty = options.isEmpty ? options.isEmpty(result as T) : defaultIsEmpty(result)
    state.value = empty ? 'empty' : 'ready'
  }

  const loading = computed(() => state.value === 'loading')

  if (options.immediate === true) {
    void load()
  }

  return {
    state,
    data: request.data,
    error,
    loading,
    load,
    retry: load,
  }
}
