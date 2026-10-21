/**
 * 选项集解析注入（选项集字段专用；工具层，非基类投影）。
 *
 * 选项集随表单元数据下发、运行期只读、**零请求**：字段件只收 `optionSetKey`，选项由本注入式解析器提供
 * （`FormRendererBody` 按 `plan.optionSets` 装配；宿主页面可自行 `provideOptionSetResolver`）。
 * 未注入解析器 / 未下发快照 / 未命中标识 → 空集，件层按空态降级，不报错、不请求。
 *
 * 与字典件**完全独立**：字典走 `DictSelectField` + 取数缓存，选项集不取数、不缓存、不比对版本。
 */

import type { OptionSetItem, OptionSetSnapshot } from '@bms/core'
import { buildOptionSetIndex, optionLabelOf, optionLabelsOf, resolveOptionSetItems } from '@bms/core'
import type { ComputedRef, InjectionKey } from 'vue'
import { computed, inject, provide } from 'vue'

/** 选项集解析器契约（已知标识返回解析后条目；未登记返回 `undefined`）。 */
export interface OptionSetResolver {
  /** 解析选项集。 */
  resolve(optionSetKey: string): readonly OptionSetItem[] | undefined
}

/** 解析器注入令牌。 */
export const OPTION_SET_RESOLVER: InjectionKey<OptionSetResolver> = Symbol('bms-option-set-resolver')

/** 开发态标记（构建期取 `import.meta.env.DEV`；生产构建为假，缺项告警静默）。 */
let optionSetDevMode: boolean | undefined = (import.meta as { env: { DEV?: boolean } }).env.DEV

/**
 * 是否开发态（缺项告警开关）。
 */
export function isOptionSetDevMode(): boolean {
  return optionSetDevMode === true
}

/**
 * 设置开发态标记（测试与宿主装配用）。
 *
 * @param value 是否开发态。
 */
export function setOptionSetDevMode(value: boolean): void {
  optionSetDevMode = value
}

/**
 * 由快照集造解析器（按需取值：支持响应式快照，查表 O(1) 级）。
 *
 * @param sets 快照集取值函数（返回元数据下发的 `optionSets`）。
 */
export function createOptionSetResolver(sets: () => readonly OptionSetSnapshot[] | undefined): OptionSetResolver {
  return {
    resolve: (optionSetKey) => buildOptionSetIndex(sets())[optionSetKey],
  }
}

/**
 * 装配选项集解析器（上层调用；渲染器内建，宿主页面按需）。
 *
 * @param resolver 解析器。
 */
export function provideOptionSetResolver(resolver: OptionSetResolver): void {
  provide(OPTION_SET_RESOLVER, resolver)
}

/** 选项集投影输入。 */
export interface UseOptionSetInput {
  /** 选项集标识（取值函数；空串 / 未设置即空态）。 */
  optionSetKey: () => string | undefined
  /** i18n 翻译（取值函数；未注入即回退 `label`）。 */
  translate?: () => ((labelKey: string) => string | undefined) | undefined
}

/** 选项集投影结果。 */
export interface UseOptionSetResult {
  /** 解析后条目（空态为空数组）。 */
  items: ComputedRef<OptionSetItem[]>
  /** 是否空态（无 key / 无解析器 / 解析为空）。 */
  empty: ComputedRef<boolean>
  /** 取单一值展示文本（未命中 `undefined`）。 */
  labelOf: (value: unknown) => string | undefined
  /** 多选回显（按选项集顺序、顿号分隔、缺项回退原值）。 */
  labelsOf: (values: readonly unknown[]) => string
}

/**
 * 选项集投影（件层消费）：按注入的解析器解析 `optionSetKey`，并套用 i18n 翻译。
 *
 * @param input 输入（标识与翻译取值函数）。
 */
export function useOptionSet(input: UseOptionSetInput): UseOptionSetResult {
  const resolver = inject(OPTION_SET_RESOLVER, undefined)
  const items = computed<OptionSetItem[]>(() => {
    const key = input.optionSetKey()
    const raw = key === undefined || key === '' ? undefined : resolver?.resolve(key)
    const translate = input.translate?.()
    return resolveOptionSetItems(raw, translate === undefined ? {} : { translate })
  })
  return {
    items,
    empty: computed(() => items.value.length === 0),
    labelOf: (value) => optionLabelOf(items.value, value),
    labelsOf: (values) => optionLabelsOf(items.value, values),
  }
}
