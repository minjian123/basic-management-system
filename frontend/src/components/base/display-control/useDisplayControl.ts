/**
 * 展示形态片段（`display-control`）：只读展示组件的公共形态。
 *
 * 契约见《组件设计 · 展示形态片段》：密度、令牌、空值占位、省略与 tooltip、可点击取值。
 * 片段只给「显示什么文本、是否省略、能否点击」，视觉与排版由组件与设计令牌决定。
 */

import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 展示形态片段参数 */
export interface UseDisplayControlOptions {
  value?: MaybeRefOrGetter<unknown>
  /** 空值占位文案（缺省用根系的 i18n 公共占位） */
  emptyText?: MaybeRefOrGetter<string>
  /** 省略：`true` 或最大字符数；仅影响文本层显示 */
  ellipsis?: MaybeRefOrGetter<boolean | number>
  /** 省略时是否补齐 tooltip 全文 */
  tooltip?: MaybeRefOrGetter<boolean>
  clickable?: MaybeRefOrGetter<boolean>
  /** 密度档位（由组件根传入，供缓存区 / 表格密集显示） */
  density?: MaybeRefOrGetter<string>
  /** 自定义文本化（默认 `String(value)`） */
  formatter?: (value: unknown) => string
  /** 点击取值回调 */
  onClickValue?: (value: unknown) => void
}

/** 展示形态片段返回值 */
export interface UseDisplayControlReturn {
  readonly isEmpty: boolean
  /** 显示文本（空值 → `emptyText`） */
  readonly displayText: string
  /** 完整文本（tooltip 用；未省略且未开 tooltip 时为空串） */
  readonly tooltipText: string
  readonly isEllipsis: boolean
  readonly isClickable: boolean
  readonly density: string | undefined
  /** 点击：可点击时触发回调，返回是否触发 */
  onClick: () => boolean
}

/** 空值判定（`undefined` / `null` / 空串视为空） */
export function isUnset(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

/**
 * 获取展示形态能力。
 *
 * 用法：`const display = useDisplayControl({ value, ellipsis: 20, onClickValue })`。
 */
export function useDisplayControl(options: UseDisplayControlOptions = {}): UseDisplayControlReturn {
  const capability = declareFragment('display-control')

  const value = computed(() => toValue(options.value))
  const isEmpty = computed(() => isUnset(value.value))
  const density = computed(() => toValue(options.density))
  const isClickable = computed(() => Boolean(toValue(options.clickable)) && !isEmpty.value)

  /** 空值兜底文案：优先 i18n `common.empty`，缺词回落破折号 */
  const defaultEmptyText = computed(() => {
    const key = 'common.empty'
    const translated = capability.t(key)
    return translated === key ? '—' : translated
  })

  const fullText = computed(() => {
    if (isEmpty.value) {
      return String(toValue(options.emptyText) ?? defaultEmptyText.value)
    }
    return options.formatter ? options.formatter(value.value) : String(value.value)
  })

  const ellipsisLimit = computed(() => {
    const setting = toValue(options.ellipsis)
    if (setting === true) {
      return 32
    }
    return typeof setting === 'number' && setting > 0 ? setting : 0
  })
  const isEllipsis = computed(() => ellipsisLimit.value > 0 && fullText.value.length > ellipsisLimit.value)

  const displayText = computed(() =>
    isEllipsis.value ? `${fullText.value.slice(0, ellipsisLimit.value)}…` : fullText.value,
  )

  const tooltipText = computed(() => {
    if (!isEllipsis.value && !toValue(options.tooltip)) {
      return ''
    }
    return isEllipsis.value ? fullText.value : ''
  })

  const onClick = (): boolean => {
    if (!isClickable.value) {
      return false
    }
    options.onClickValue?.(value.value)
    return true
  }

  return {
    get isEmpty() {
      return isEmpty.value
    },
    get displayText() {
      return displayText.value
    },
    get tooltipText() {
      return tooltipText.value
    },
    get isEllipsis() {
      return isEllipsis.value
    },
    get isClickable() {
      return isClickable.value
    },
    get density() {
      return density.value
    },
    onClick,
  }
}
