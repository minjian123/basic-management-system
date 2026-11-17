/**
 * 帮助上下文投影：把核心 `BaseHelpContext` 投影为响应式面。
 *
 * 页面 / 顶栏 / 帮助入口只消费本投影；取数与状态机归核心能力（未注入 / 未就绪即零请求）。
 */

import {
  BaseHelpContext,
  type HelpArticle,
  type HelpContextFetcher,
  type HelpContextInput,
  type HelpResult,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体帮助上下文（可实例化）。 */
class HelpContextState extends BaseHelpContext {}

/** `useBaseHelpContext` 选项。 */
export interface UseBaseHelpContextOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 取数器（未注入即抛 `19001`）。 */
  fetcher?: HelpContextFetcher
  /** 初始上下文。 */
  context?: HelpContextInput
}

/** `useBaseHelpContext` 返回面。 */
export interface UseBaseHelpContextResult {
  /** 最近一次解析结果。 */
  result: Ref<HelpResult | undefined>
  /** 数据状态（`loading` / `ready` / `empty` / `error`）。 */
  state: Ref<string>
  /** 是否命中文章。 */
  matched: ComputedRef<boolean>
  /** 是否登记锚点。 */
  anchorFound: ComputedRef<boolean>
  /** 命中文章。 */
  article: ComputedRef<HelpArticle | undefined>
  /** 错误文案。 */
  errorMessage: Ref<string>
  /** 请求计数。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入取数器。 */
  setFetcher: (fetcher: HelpContextFetcher | undefined) => void
  /** 设置上下文。 */
  setContext: (context: HelpContextInput) => void
  /** 解析（同上下文缓存；`force` 强制重取）。 */
  resolve: (force?: boolean) => Promise<HelpResult | undefined>
  /** 重试。 */
  retry: () => Promise<HelpResult | undefined>
  /** 重置。 */
  reset: () => void
}

/**
 * 使用帮助上下文投影。
 *
 * @param options 选项。
 * @returns 响应式面与命令。
 */
export function useBaseHelpContext(options: UseBaseHelpContextOptions = {}): UseBaseHelpContextResult {
  const help = new HelpContextState()
  if (options.context !== undefined) {
    help.setContext(options.context)
  }
  help.setFetcher(options.fetcher)
  help.setReady(options.ready ?? false)

  const result = ref<HelpResult | undefined>(help.result)
  const state = ref<string>(help.state)
  const errorMessage = ref<string>(help.errorMessage)
  const requestCount = ref<number>(help.requestCount)

  const sync = (): void => {
    result.value = help.result
    state.value = help.state
    errorMessage.value = help.errorMessage
    requestCount.value = help.requestCount
  }
  help.onLifecycle(sync)
  onScopeDispose(() => help.dispose())

  const matched = computed(() => result.value?.matched === true)
  const anchorFound = computed(() => result.value?.anchorFound === true)
  const article = computed(() => result.value?.article)

  return {
    result,
    state,
    matched,
    anchorFound,
    article,
    errorMessage,
    requestCount,
    setReady: (value) => {
      help.setReady(value)
      sync()
    },
    setFetcher: (fetcher) => {
      help.setFetcher(fetcher)
      sync()
    },
    setContext: (context) => {
      help.setContext(context)
      sync()
    },
    resolve: async (force = false) => {
      const next = await help.resolve(force)
      sync()
      return next
    },
    retry: async () => {
      const next = await help.retry()
      sync()
      return next
    },
    reset: () => {
      help.reset()
      sync()
    },
  }
}
