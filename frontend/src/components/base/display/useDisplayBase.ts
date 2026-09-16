/**
 * 展示域组合式（`useDisplayBase`）：展示域基类的组合轨。
 *
 * 契约见《组件设计 · 展示域基类》：组合 `useValue`（值语义 / 格式化调度）+ `useDisplayControl`
 * （空值占位 / 省略与 tooltip / 密度 / 点击取值），统一只读回显与复制。
 * 依赖方向：片段 + Vue；不依赖 UI 库（tooltip / 复制按钮由子类与具体组件增强）。
 */

import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { resolveFormatter as resolveNamedFormatter } from '../formatters'
import { useDisplayControl } from '../display-control/useDisplayControl'
import { useValue } from '../value/useValue'

/** 展示域组合式参数 */
export interface UseDisplayBaseOptions {
  value?: MaybeRefOrGetter<unknown>
  /** 格式化器：函数直接调度；名称为名义格式化器（格式化工具 `02_06` 接入前回退 `String`，占位口径） */
  formatter?: MaybeRefOrGetter<string | ((value: unknown) => string) | undefined>
  emptyText?: MaybeRefOrGetter<string>
  density?: MaybeRefOrGetter<string | undefined>
  copyable?: MaybeRefOrGetter<boolean>
  ellipsis?: MaybeRefOrGetter<boolean | number>
  tooltip?: MaybeRefOrGetter<boolean | 'overflow'>
  /** 脱敏标记（为真时禁复制，防明文泄露；脱敏文本由字段链 `mask` 生成） */
  masked?: MaybeRefOrGetter<boolean>
  /** 可点击取值（缺省：提供 `onClickValue` 即视为可点击） */
  clickable?: MaybeRefOrGetter<boolean>
  /** 名义格式化器的 locale 基准（缺省取格式化工具默认值） */
  locale?: MaybeRefOrGetter<string | undefined>
  /** 名义格式化器的时区基准（缺省取格式化工具默认值） */
  timezone?: MaybeRefOrGetter<string | undefined>
  onClickValue?: (value: unknown) => void
  onCopy?: (value: unknown) => void
}

/** 展示域组合式返回值 */
export interface UseDisplayBaseReturn {
  /** 显示文本（省略后；空值 → `emptyText`） */
  readonly displayText: string
  /** 完整格式化文本（空值为空串） */
  readonly fullText: string
  /** tooltip 文本（省略或 tooltip 开启时） */
  readonly tooltipText: string
  readonly isEmpty: boolean
  readonly isEllipsis: boolean
  readonly isClickable: boolean
  readonly density: string | undefined
  readonly canCopy: boolean
  /** 点击（可点击才触发回调，返回是否触发） */
  onClick: () => boolean
  /** 复制格式化文本（不可复制 / 剪贴板不可用返回 `false`，不抛错） */
  copy: () => Promise<boolean>
}

/**
 * 获取展示域能力。
 *
 * 用法：`const display = useDisplayBase({ value, formatter: 'amount', copyable: true })`。
 */
export function useDisplayBase(options: UseDisplayBaseOptions = {}): UseDisplayBaseReturn {
  const resolveFormatter = (): ((value: unknown) => string) | undefined => {
    const setting = options.formatter
    if (setting === undefined) {
      return undefined
    }
    if (typeof setting === 'function') {
      // 裸函数按格式化函数处理；需响应式切换时传 ref / computed（其值为函数或名义名称）
      return setting as (value: unknown) => string
    }
    const resolved = toValue(setting)
    if (typeof resolved === 'function') {
      return resolved
    }
    // 名义格式化器：片段层注册表（内置 amount / date / boolean 等；未注册回退 String）
    if (typeof resolved === 'string' && resolved) {
      const named = resolveNamedFormatter(resolved)
      if (named) {
        return (value: unknown) =>
          named(value, { locale: toValue(options.locale), timezone: toValue(options.timezone) })
      }
    }
    return undefined
  }

  const format = (value: unknown): string => {
    const formatter = resolveFormatter()
    if (formatter) {
      return formatter(value)
    }
    return String(value)
  }

  const valueFragment = useValue<unknown>({
    ...(options.value !== undefined ? { modelValue: options.value } : {}),
    formatter: format,
  })

  const display = useDisplayControl({
    ...(options.value !== undefined ? { value: options.value } : {}),
    formatter: format,
    ...(options.emptyText !== undefined ? { emptyText: options.emptyText } : {}),
    ...(options.ellipsis !== undefined ? { ellipsis: options.ellipsis } : {}),
    tooltip: computed(() => toValue(options.tooltip) !== false),
    clickable: computed(() =>
      options.clickable !== undefined ? Boolean(toValue(options.clickable)) : options.onClickValue !== undefined,
    ),
    ...(options.onClickValue ? { onClickValue: options.onClickValue } : {}),
  })

  const isEmpty = computed(() => valueFragment.isUnset)
  const fullText = computed(() => (isEmpty.value ? '' : valueFragment.display))
  const canCopy = computed(
    () =>
      Boolean(toValue(options.copyable)) &&
      toValue(options.masked) !== true &&
      !isEmpty.value &&
      fullText.value.length > 0,
  )

  const copy = async (): Promise<boolean> => {
    if (!canCopy.value) {
      return false
    }
    const text = fullText.value
    try {
      const clipboard = typeof navigator === 'undefined' ? undefined : navigator.clipboard
      if (!clipboard || typeof clipboard.writeText !== 'function') {
        return false
      }
      await clipboard.writeText(text)
      options.onCopy?.(text)
      return true
    } catch {
      return false
    }
  }

  return {
    get displayText() {
      return display.displayText
    },
    get fullText() {
      return fullText.value
    },
    get tooltipText() {
      return display.tooltipText
    },
    get isEmpty() {
      return isEmpty.value
    },
    get isEllipsis() {
      return display.isEllipsis
    },
    get isClickable() {
      return display.isClickable
    },
    get density() {
      return toValue(options.density)
    },
    get canCopy() {
      return canCopy.value
    },
    onClick: () => display.onClick(),
    copy,
  }
}
