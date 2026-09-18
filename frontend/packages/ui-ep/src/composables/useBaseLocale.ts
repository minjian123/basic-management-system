/** 语言上下文投影：把核心语言上下文能力基类 `BaseLocale` 投影为组合式（locale / 时区 / 格式上下文）。 */

import { BaseLocale, type LocaleFormatContext } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体语言上下文件（可实例化）。 */
class LocaleState extends BaseLocale {}

/** 选项。 */
export interface UseBaseLocaleOptions {
  /** 初始语言。 */
  locale?: string
  /** 初始时区。 */
  timezone?: string
}

/** `useBaseLocale` 返回面。 */
export interface UseBaseLocaleResult {
  /** 当前语言（响应式）。 */
  locale: Ref<string>
  /** 当前时区（响应式）。 */
  timezone: Ref<string>
  /** 格式上下文（响应式）。 */
  formatContext: Ref<LocaleFormatContext>
  /** 切换语言。 */
  setLocale: (locale: string) => void
  /** 切换时区。 */
  setTimezone: (timezone: string) => void
}

/**
 * 使用语言上下文投影。
 *
 * @param options 选项。
 * @returns 语言上下文响应式面。
 */
export function useBaseLocale(options: UseBaseLocaleOptions = {}): UseBaseLocaleResult {
  const state = new LocaleState()
  if (options.locale !== undefined) {
    state.locale = options.locale
  }
  if (options.timezone !== undefined) {
    state.timezone = options.timezone
  }

  const locale = ref(state.locale)
  const timezone = ref(state.timezone)
  const formatContext = ref<LocaleFormatContext>(state.formatContext)
  const sync = (): void => {
    locale.value = state.locale
    timezone.value = state.timezone
    formatContext.value = state.formatContext
  }
  const off = state.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    locale,
    timezone,
    formatContext,
    setLocale: (value) => {
      state.setLocale(value)
      sync()
    },
    setTimezone: (value) => {
      state.setTimezone(value)
      sync()
    },
  }
}
