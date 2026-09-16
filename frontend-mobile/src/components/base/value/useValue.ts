/**
 * 受控值片段（`value`）：输入与展示共用的值语义，是字段链的基座（承前启后）。
 *
 * 契约见《组件设计 · 受控值片段》：值归一（`normalize`）、格式化调度（`format`）、
 * 三态（未设置 / 已清空 / 有值）、`change` 上报。片段不含具体控件与校验触发。
 */

import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 受控值片段参数 */
export interface UseValueOptions<T = unknown> {
  modelValue?: MaybeRefOrGetter<T>
  /** 已清空的显式值（三态模式下与「未设置」区分） */
  emptyValue?: T
  /** 展示格式化（缺省 `String(value)`） */
  formatter?: (value: T) => string
  /** 三态模式：区分「未设置（`undefined`）」与「已清空（`emptyValue`）」 */
  threeState?: MaybeRefOrGetter<boolean>
  /** 值变更上报（宿主据此写回 `v-model`） */
  onChange?: (value: T | undefined) => void
}

/** 受控值片段返回值 */
export interface UseValueReturn<T = unknown> {
  readonly value: T | undefined
  /** 未设置（`undefined` / `null` / 空串归一后为空） */
  readonly isUnset: boolean
  /** 已清空（三态模式下等于 `emptyValue`） */
  readonly isCleared: boolean
  /** 展示文本（经 `format`） */
  readonly display: string
  readonly threeState: boolean
  /** 值归一：空值 → `undefined`；其余原样（可被子类片段覆盖语义） */
  normalize: (value: unknown) => T | undefined
  /** 格式化：`formatter` 优先，空值 → `emptyValue` / 空串 */
  format: (value?: T) => string
  /** 设置值（归一 + 判等后回调 `onChange`；无变化不回调） */
  setValue: (value: unknown) => void
  /** 清空（三态 → `emptyValue`；否则 `undefined`） */
  clear: () => void
  /** 语义判等（归一后比较） */
  isEqual: (a: unknown, b: unknown) => boolean
}

/**
 * 获取受控值能力。
 *
 * 用法：`const model = useValue<string>({ modelValue, onChange: (v) => emit('update:modelValue', v) })`。
 */
export function useValue<T = unknown>(options: UseValueOptions<T> = {}): UseValueReturn<T> {
  declareFragment('value')

  const threeState = computed(() => Boolean(toValue(options.threeState)))

  const normalize = (input: unknown): T | undefined => {
    if (input === undefined || input === null || input === '') {
      return undefined
    }
    return input as T
  }

  const value = computed(() => normalize(toValue(options.modelValue)))
  const isUnset = computed(() => value.value === undefined)
  const isCleared = computed(
    () => threeState.value && !isUnset.value && options.emptyValue !== undefined && value.value === options.emptyValue,
  )

  const format = (input?: T): string => {
    const target = input === undefined ? value.value : normalize(input)
    if (target === undefined) {
      return options.emptyValue === undefined ? '' : String(options.emptyValue)
    }
    return options.formatter ? options.formatter(target) : String(target)
  }

  const isEqual = (a: unknown, b: unknown): boolean => normalize(a) === normalize(b)

  const setValue = (input: unknown): void => {
    const next = normalize(input)
    if (next === value.value) {
      return
    }
    options.onChange?.(next)
  }

  const clear = (): void => {
    const next = threeState.value ? options.emptyValue : undefined
    if (next === value.value) {
      return
    }
    options.onChange?.(next)
  }

  return {
    get value() {
      return value.value
    },
    get isUnset() {
      return isUnset.value
    },
    get isCleared() {
      return isCleared.value
    },
    get display() {
      return format()
    },
    get threeState() {
      return threeState.value
    },
    normalize,
    format,
    setValue,
    clear,
    isEqual,
  }
}
