/**
 * 语言上下文片段（`locale`）：locale / 时区 / 格式上下文。
 *
 * 契约见《组件设计 · 语言上下文片段》：`locale` / `timezone` / `setLocale` / `setTimezone` /
 * `t` / `formatDate` / `formatNumber` + 切换与缓存；**收敛时区格式化**（全站日期 / 数字走本片段，
 * 避免各组件各自 `Intl` 与本地时区差异）。取词委托 vue-i18n（`i18n` 由宿主注入），
 * 未注入时回退 `Intl` 原生能力（不报错）。
 */

import { ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 日期展示粒度 */
export type DateFormatKind = 'date' | 'datetime' | 'time' | 'relative'

/** 数字展示粒度 */
export type NumberFormatKind = 'decimal' | 'percent' | 'currency' | 'integer'

/** i18n 适配（宿主把 vue-i18n 实例传入；缺省回退 Intl） */
export interface LocaleI18nAdapter {
  locale: string
  t: (key: string, params?: Record<string, unknown>) => string
}

/** 语言上下文片段参数 */
export interface UseLocaleOptions {
  /** 初始语言（默认 `zh-CN`） */
  locale?: MaybeRefOrGetter<string>
  /** 初始时区（默认浏览器时区） */
  timezone?: MaybeRefOrGetter<string>
  /** i18n 适配（缺省：`t` 回退 key 原文） */
  i18n?: LocaleI18nAdapter
  /** 切换通知（宿主据此持久化偏好） */
  onChange?: (payload: { locale: string; timezone: string }) => void
}

/** 语言上下文片段返回值 */
export interface UseLocaleReturn {
  readonly locale: string
  readonly timezone: string
  setLocale: (locale: string) => void
  setTimezone: (timezone: string) => void
  t: (key: string, params?: Record<string, unknown>) => string
  formatDate: (value: string | number | Date | undefined, kind?: DateFormatKind) => string
  formatNumber: (value: number | undefined, kind?: NumberFormatKind) => string
}

/** 默认时区（浏览器时区；非浏览器环境回落 UTC） */
function defaultTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/**
 * 获取语言上下文能力。
 *
 * 用法：`const locale = useLocale({ locale, timezone, i18n })`；组件一律经 `formatDate` / `formatNumber`
 * 输出，避免时区与格式分散。
 */
export function useLocale(options: UseLocaleOptions = {}): UseLocaleReturn {
  declareFragment('locale')

  const locale = ref(String(toValue(options.locale) ?? options.i18n?.locale ?? 'zh-CN'))
  const timezone = ref(String(toValue(options.timezone) ?? defaultTimezone()))

  const emitChange = (): void => {
    options.onChange?.({ locale: locale.value, timezone: timezone.value })
  }

  const t = (key: string, params?: Record<string, unknown>): string => {
    if (options.i18n) {
      return options.i18n.t(key, params)
    }
    return key
  }

  const formatDate = (value: string | number | Date | undefined, kind: DateFormatKind = 'datetime'): string => {
    if (value === undefined || value === null || value === '') {
      return ''
    }
    const date = value instanceof Date ? value : new Date(value)
    if (Number.isNaN(date.getTime())) {
      return ''
    }
    if (kind === 'relative') {
      const diff = Date.now() - date.getTime()
      const minutes = Math.round(diff / 60000)
      if (Math.abs(minutes) < 1) {
        return t('common.justNow')
      }
      const suffix = minutes < 0 ? '后' : '前'
      if (Math.abs(minutes) < 60) {
        return `${Math.abs(minutes)} 分钟${suffix}`
      }
      const hours = Math.round(Math.abs(minutes) / 60)
      if (hours < 24) {
        return `${hours} 小时${suffix}`
      }
      return `${Math.round(hours / 24)} 天${suffix}`
    }
    const formatOptions: Intl.DateTimeFormatOptions =
      kind === 'date'
        ? { year: 'numeric', month: '2-digit', day: '2-digit' }
        : kind === 'time'
          ? { hour: '2-digit', minute: '2-digit' }
          : { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
    return new Intl.DateTimeFormat(locale.value, { ...formatOptions, timeZone: timezone.value }).format(date)
  }

  const formatNumber = (value: number | undefined, kind: NumberFormatKind = 'decimal'): string => {
    if (value === undefined || value === null || Number.isNaN(value)) {
      return ''
    }
    const formatOptions: Intl.NumberFormatOptions =
      kind === 'percent'
        ? { style: 'percent', minimumFractionDigits: 1 }
        : kind === 'integer'
          ? { maximumFractionDigits: 0 }
          : kind === 'currency'
            ? { style: 'currency', currency: 'CNY' }
            : { minimumFractionDigits: 0, maximumFractionDigits: 2 }
    return new Intl.NumberFormat(locale.value, formatOptions).format(value)
  }

  return {
    get locale() {
      return locale.value
    },
    get timezone() {
      return timezone.value
    },
    setLocale: (next) => {
      locale.value = next
      emitChange()
    },
    setTimezone: (next) => {
      timezone.value = next
      emitChange()
    },
    t,
    formatDate,
    formatNumber,
  }
}
